# Provedores de IA — integração e viabilidade

Consultado nas documentações oficiais em 2026-11-15. Preços semeados são **editáveis** em Provedores → modelos;
modelo sem preço configurado exige autorização explícita para executar. Confira os preços na sua conta antes de gastar.

| Provedor | Capacidades implementadas | Endpoints (docs oficiais) | Custo efetivo |
|---|---|---|---|
| OpenAI | texto, imagem (+ referências via `/images/edits`) | `POST /v1/responses`, `/v1/images/generations`, `/v1/images/edits`, teste: `GET /v1/models` | calculado dos tokens de `usage` (imagem); texto idem se `usage` vier |
| Recraft | imagem | `POST external.api.recraft.ai/v1/images/generations`, teste: `GET /users/me` (saldo) | campo `credits` da resposta (US$1 = 1000 unidades) |
| Google Gemini | texto, imagem (+ referências inline) | `POST /v1beta/interactions` (header `Api-Revision: 2026-05-20`), teste: `GET /v1beta/models` | sem campos de uso documentados → custo = estimativa |
| Ollama | texto (local) | `POST /api/generate`, `GET /api/tags` | zero |
| Simulado | texto, imagem | — | fictício, só para testes/validação |

Pontos não verificados na documentação (tratados de forma conservadora):
- Gemini `models.list` (teste de conexão) não consta na doc atual; se falhar, o teste mostra o erro real.
- Gemini: campos de `usage` e o limite de `max_output_tokens` sobre tokens de "thinking" não documentados → estimativa usa o teto de saída.
- Gemini: o formato de imagem usa `image/jpeg` (exemplo da doc); ajustável em `config.mime_type`.
- Recraft: ids `recraftv3`/`recraftv4_1`/`recraftv4_1_flash_v2` seguem a nomenclatura da doc/tabela de preços; confirme na sua conta.
- OpenAI: os preços por imagem vêm da tabela "histórica" da doc (1024², 1024×1536, 1536×1024; qualidade low/medium/high). Modelos mais novos (`gpt-image-2.5-*`, etc.) não têm preço publicado → sem preço, exigem autorização.
- `gpt-image-1` foi desligado pela OpenAI em 2026-10-23 (não semeado).

## Avaliação de viabilidade (não implementados)
- **xAI** — viável. `POST https://api.x.ai/v1/images/generations` e `/images/edits`, modelo `grok-imagine-image-2.0`, Bearer; até 10 imagens
  por requisição; edição com até 5 imagens. Preço por imagem fixo, **não publicado na página consultada** → precisa ser confirmado antes de integrar.
  Formato de resposta varia por SDK; validar o JSON bruto. Esforço estimado: 1 adaptador (~80 linhas).
- **Capafy / Color Koala** — **não viável hoje**. Não há API pública documentada: o site descreve um marketplace de agentes
  (cobrança por hora/assinatura/skill) acessado por login e uma "skill" para clientes de agentes; Color Koala não aparece na documentação pública.
  Reavaliar se a Capafy publicar API/chaves, ou solicitar acesso ao PO.

## Como adicionar um provedor
1. `backend/app/providers/adapters/<nome>.py` com uma subclasse de `Adapter` (`test`, `estimate`, `text`/`image`) e `known_models` (preços da doc).
2. Registrar em `adapters/__init__.py`; testar com `httpx.MockTransport` (ver `tests/test_providers.py`).
3. Pipelines **nunca** chamam adaptadores: usam `ctx.ai` (gateway), que aplica estimativa, reserva, idempotência e conciliação.

## Estúdio de vídeos (Missão 1)
- **Gemini (texto)**: `POST {base}/models/{model}:generateContent` (header `x-goog-api-key`), `responseMimeType=application/json`, uso em `usageMetadata`. Modelo padrão `gemini-3.1-flash-lite` (o `gemini-2.5-flash` retorna 404 "no longer available to new users"). Custo registrado como 0 — vale só para chave de projeto sem faturamento. Chave: `GEMINI_API_KEY`. Validado contra a API real em 2026-11-21.
- **Wikimedia Commons** (`commons.wikimedia.org/w/api.php`, sem chave): só licenças livres (PD/CC0/CC BY/CC BY-SA); atribuição em `metadados.json`.
- **Pexels** (opcional, `PEXELS_API_KEY`, gratuita).
- **Piper** (voz `pt_BR-faber-medium`, rhasspy/piper-voices) e **eSpeak NG**: locais, sem custo.
