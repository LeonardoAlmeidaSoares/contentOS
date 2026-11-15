# ContentOS — diretrizes de arquitetura e desenvolvimento

Fábrica automatizada de conteúdo digital (não uma ferramenta de assistência). Uso interno Kahi. Sem dependência do MasterShield.

## Arquitetura
- Monólito modular (FastAPI) + workers Celery. Sem microsserviços, sem Kubernetes.
- Stack: Python 3.12, FastAPI, SQLAlchemy 2 (síncrono) + Alembic, PostgreSQL 16, Redis 7, Celery 5.4, MinIO, React + TS + Tailwind 3 (Vite), Docker Compose.
- Pin importante: `celery 5.4` + `kombu 5.4.2` + `redis-py 5.2.1` (kombu ≥5.5 exige redis-py ≥6).
- Domínios em `backend/app/`: `core` (config, db, storage), `runs` (execuções, etapas, artefatos, executor, tasks), `pipelines` (uma linha de produção por módulo), `health`.
  Domínios futuros (providers, analytics, agendamento, custos) só são criados quando houver o primeiro caso de uso real.
- Pipelines: registrados em `pipelines/registry.py` (`register(Pipeline(...))`; importar o módulo em `load_all`). Etapa = `fn(StepContext) -> StepResult(output, cost, files)`; **a etapa não acessa banco/storage** — o executor persiste saída, custo e arquivos (uploads idempotentes), garantindo que retry/retomada não dupliquem efeitos nem custos.
- Executor (`runs/executor.py`): claim atômico (`queued|retrying` → `running`), pula etapas `succeeded`, checa cancelamento e orçamento antes de cada etapa, retry com backoff devolvendo o delay (a task reenfileira com `countdown`). Regras de negócio em `runs/service.py`; agendador em `runs/tasks.tick` (Celery beat).
- Exclusividade: índice único parcial `uq_runs_one_active_per_line`; novos fluxos de criação de run devem passar por `service.start_run`.
- Custos em USD (Numeric); linha tem `cost_limit_run` e `cost_limit_month` (null = sem limite).
- Providers (futuro): fluxos nunca importam SDKs de fornecedores de IA diretamente; sempre via interface em `providers/`.
- Artefatos: bytes no MinIO, metadados no Postgres, download via API (MinIO não é exposto).

## Regras
- Isolamento: infra própria no compose (`name: contentos`); não usar Redis/MinIO/MySQL compartilhados da Kahi nem portas deles. Portas: web 8300, api 8301.
- Mudanças de schema só via Alembic (migration nova em `backend/alembic/versions`).
- Toda etapa de pipeline deve funcionar offline/sem custo em testes (providers fake).
- Frontend: não exibir funcionalidade fictícia; áreas sem backend usam `<Unavailable>`.
- Testes: pytest (SQLite + storage fake) para lógica; Playwright só para fluxos essenciais.
- Não implementar mecanismos para contornar restrições de plataformas externas. Sem publicação real sem aprovação do PO.
