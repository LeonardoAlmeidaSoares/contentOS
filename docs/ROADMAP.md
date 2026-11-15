# Roadmap

0. **Fundação (feito)** — infra, API, worker, MinIO, UI base, pipeline demo.
1. **Core de execução** — cadastro de linhas de produção, retry/backoff, pausa/retomada, agendamento (Celery beat), logs operacionais, registro de custos.
2. **Providers** — interfaces (LLM, imagem, áudio, vídeo, storage, publicação) com implementações fake + primeiro real, configuráveis por linha.
3. **Pipeline Colorir KDP** — pesquisa de nicho → tema → prompts → ilustrações → validação de qualidade → capa → diagramação (PDF) → metadados. Publicação apenas por meios permitidos pela Amazon (provavelmente semi-manual).
4. **Analytics** — custos, receita, rentabilidade por linha.
5. **Novas linhas** — Shorts YouTube, e-books, produtos digitais, redes sociais.
6. **Integração de backlog/distribuição de tarefas** entre agentes (experiência do MasterShield, sem dependência funcional).
