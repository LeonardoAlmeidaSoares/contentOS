# Instruções para agentes (ContentOS)

Leia `CLAUDE.md` antes de qualquer alteração. Resumo operacional:

1. Escopo: implemente somente a tarefa recebida; não crie abstrações ou documentação extra.
2. Subir ambiente: `docker compose up -d --build` (web 8300, api 8301).
3. Antes de entregar: `docker compose run --rm --no-deps api python -m pytest -q` e, se tocou UI/fluxo, `cd e2e && BASE_URL=http://192.168.18.2:8300 npx playwright test`.
4. Schema: sempre com migration Alembic. Novos pipelines: um módulo em `backend/app/pipelines/` + registro em `pipelines/registry.py` (ver CLAUDE.md).
5. Nunca tocar em serviços/containers fora do projeto `contentos` (MasterShield e demais) nem usar custos/APIs pagas sem autorização do PO.
6. Commits pequenos e descritivos; não commitar `.env`.

Papéis: PO decide negócio · ChatGPT planeja/prioriza · Claude Code arquitetura/dev sênior · Codex dev pleno · OpenCode dev júnior.
