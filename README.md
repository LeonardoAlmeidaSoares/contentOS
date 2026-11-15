# ContentOS

Plataforma de automação de linhas de produção de conteúdo digital. Projeto independente da Kahi (uso interno).
Estado atual: **fundação** — infraestrutura + fluxo técnico de demonstração. Nenhuma linha comercial implementada.

## Requisitos
Docker + Docker Compose. (Node 20+ apenas para rodar o E2E no host.)

## Executar
```bash
cp .env.example .env      # opcional; os defaults de dev funcionam
docker compose up -d --build
```
- Interface (homologação): http://localhost:8300
- API / docs OpenAPI: http://localhost:8301/docs
- Healthchecks: `/health` (liveness) e `/health/ready` (postgres, redis, minio)

Postgres, Redis e MinIO são instâncias próprias do projeto (não publicadas no host), com volumes `contentos_*`.
Para parar: `docker compose down` (acrescente `-v` para apagar os dados).

## Testes
```bash
docker compose run --rm --no-deps api python -m pytest -q   # backend
cd e2e && npm install && npx playwright install chromium && npx playwright test   # E2E (stack no ar)
```

## Fluxo de demonstração
Execuções → "Iniciar execução de demonstração": 3 etapas em background (Celery), progresso persistido no Postgres,
arquivo `demo-output.json` salvo no MinIO e disponível para download. Não usa APIs pagas.

## Estrutura
```
backend/app/{core,runs,pipelines,health}   frontend/src   e2e/   docker-compose.yml
```
