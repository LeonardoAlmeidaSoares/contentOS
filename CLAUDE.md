# ContentOS — diretrizes de arquitetura e desenvolvimento

Fábrica automatizada de conteúdo digital (não uma ferramenta de assistência). Uso interno Kahi. Sem dependência do MasterShield.

## Arquitetura
- Monólito modular (FastAPI) + workers Celery. Sem microsserviços, sem Kubernetes.
- Stack: Python 3.12, FastAPI, SQLAlchemy 2 (síncrono) + Alembic, PostgreSQL 16, Redis 7, Celery 5.4, MinIO, React + TS + Tailwind 3 (Vite), Docker Compose.
- Pin importante: `celery 5.4` + `kombu 5.4.2` + `redis-py 5.2.1` (kombu ≥5.5 exige redis-py ≥6).
- Domínios em `backend/app/`: `core` (config, db, storage), `runs` (execuções, etapas, artefatos, executor, tasks), `pipelines` (uma linha de produção por módulo), `health`.
  Domínios futuros (providers, analytics, agendamento, custos) só são criados quando houver o primeiro caso de uso real.
- Pipelines: registrados em `pipelines/registry.py` (`register(Pipeline(...))`; importar o módulo em `load_all`). Etapa = `fn(StepContext) -> StepResult(output, cost, files)`; **a etapa não acessa banco e só lê storage via `ctx.read` (artefatos de etapas anteriores)** — o executor persiste saída, custo e arquivos (uploads idempotentes), garantindo que retry/retomada não dupliquem efeitos nem custos.
- Executor (`runs/executor.py`): claim atômico (`queued|retrying` → `running`), pula etapas `succeeded`, checa cancelamento e orçamento antes de cada etapa, retry com backoff devolvendo o delay (a task reenfileira com `countdown`). Regras de negócio em `runs/service.py`; agendador em `runs/tasks.tick` (Celery beat).
- Exclusividade: índice único parcial `uq_runs_one_active_per_line`; novos fluxos de criação de run devem passar por `service.start_run`.
- Custos em USD (Numeric); linha tem `cost_limit_run` e `cost_limit_month` (null = sem limite).
- Providers (`app/providers`): adaptadores HTTP independentes em `adapters/` (sem SDKs de fornecedor) + `gateway.py`. **Pipelines só usam `ctx.ai`** (AIGateway): estimativa → reserva (advisory lock, ledger `ai_usage`) → chamada → conciliação; idempotência por chave (`ctx.ai_key(...)`); incerto nunca repete; custo desconhecido só com `allow_unknown_cost` (nunca em pipelines automáticos). Orçamentos: provedor/mês, linha/execução, linha/mês, Laboratório/mês. Gasto da run = `service.run_spent` (etapas concluídas + ledger das demais).
- Laboratório (`app/lab`): cada resultado = uma `Run` (trigger `lab`, pipeline interno `lab`, sem linha) → reaproveita fila, retry e logs. Nunca invente endpoints/preços de provedores: consulte a documentação oficial e registre em `docs/PROVIDERS.md`.
- Studio (`app/studio`, `app/media`, `pipelines/video.py`): fábrica de vídeo = `ProductionLine` com pipeline `video_youtube`, identidade em `config` (`FactoryConfig`, validada; usuário nunca edita JSON). Assistente conversacional via Gemini (`generateContent`, chave só em `GEMINI_API_KEY`, custo 0 no free tier, pelo gateway). Imagens: Wikimedia/Pexels (licença registrada); voz: Piper/eSpeak locais; montagem: FFmpeg.
- Publicação (`app/publishing`, `docs/YOUTUBE.md`): revisão humana (`video_reviews`) → envio privado ao YouTube (`youtube_publications`, índice único parcial = um envio vivo por run). Tokens OAuth só criptografados; nunca logar URLs/tokens (loggers httpx silenciados). Nada publica sem aprovação + confirmação explícita; só `private`.
- Segurança: `core/auth.py` (middleware: tudo em `/api` exige sessão/Bearer, exceto health e login), `core/crypto.py` (Fernet). Nunca logar corpos/headers de provedores; erros passam por `scrub`.
- Artefatos: bytes no MinIO, metadados no Postgres, download via API (MinIO não é exposto).

## Regras
- Isolamento: infra própria no compose (`name: contentos`); não usar Redis/MinIO/MySQL compartilhados da Kahi nem portas deles. Portas: web 8300, api 8301.
- Mudanças de schema só via Alembic (migration nova em `backend/alembic/versions`).
- Toda etapa de pipeline deve funcionar offline/sem custo em testes (providers fake).
- Frontend: não exibir funcionalidade fictícia; áreas sem backend usam `<Unavailable>`.
- Testes: pytest (SQLite + storage fake) para lógica; Playwright só para fluxos essenciais.
- Não implementar mecanismos para contornar restrições de plataformas externas. Sem publicação real sem aprovação do PO.
