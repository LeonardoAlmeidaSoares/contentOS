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
- Interface (homologação, LAN): http://192.168.18.2:8300 (IP definido em `WEB_BIND_IP` no `.env`; sem autenticação — nunca expor à internet)
- API / docs OpenAPI: http://localhost:8301/docs
- Healthchecks: `/health` (liveness) e `/health/ready` (postgres, redis, minio)

Postgres, Redis e MinIO são instâncias próprias do projeto (não publicadas no host), com volumes `contentos_*`.
Para parar: `docker compose down` (acrescente `-v` para apagar os dados).

## Testes
```bash
docker compose run --rm --no-deps api python -m pytest -q   # backend
cd e2e && npm install && npx playwright install chromium && BASE_URL=http://192.168.18.2:8300 npx playwright test   # E2E (stack no ar; BASE_URL = WEB_BIND_IP:WEB_PORT)
```

## Motor de produção (Fase 1)
- **Linhas de produção** (menu Linhas de Produção): nome, pipeline, config JSON, frequência (minutos), limites de custo
  (por execução e mensal), retry (tentativas + backoff exponencial), ativar/desativar, executar agora, editar.
- **Execuções**: etapas sequenciais com entrada/saída/custo persistidos; retry automático; **Retomar** continua da etapa
  que falhou sem repetir as concluídas; **Cancelar** é seguro (a etapa em curso termina, a próxima não inicia).
- **Duplicidade**: índice único no banco permite só uma execução ativa por linha.
- **Agendamento**: serviço `beat` verifica a cada 30 s as linhas ativas vencidas. Execuções `running` sem heartbeat há 15 min são marcadas como falhas (retomáveis).
- **Orçamento**: antes de cada etapa, bloqueia se o limite da execução ou do mês foi atingido (custos não são desfeitos; ajuste o limite e retome).
- Pipeline `demo` (sem custo real) aceita `items`, `step_delay`, `cost_per_step`, `fail_step`, `fail_attempts` para validar o motor.

**MinIO:** a imagem está fixada por digest (RELEASE.2025-09-07T16-13-09Z) porque o MinIO não publica mais tags em registros públicos.
Backup local (não versionado) em `.cache/minio-image.tar`; restaurar com `docker load -i .cache/minio-image.tar`.

## Estrutura
```
backend/app/{core,runs,pipelines,health}   frontend/src   e2e/   docker-compose.yml
```
