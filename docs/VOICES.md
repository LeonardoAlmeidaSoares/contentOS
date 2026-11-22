# Laboratório de Vozes (Missão 3A)

Tela: **/vozes** (menu "Laboratório de Vozes"). API aditiva em `/api/voices/*`; código em `backend/app/voices/`.

## Provedores
| Id | Tipo | Vozes pt-BR | Controles | Custo | Requisitos |
|---|---|---|---|---|---|
| `piper` | local | faber, cadu, jeff (medium) | velocidade | 0 | binário `piper` + modelos em `/opt/piper` (fallback do sistema) |
| `kokoro` | local | pf_dora (F), pm_alex (M), pm_santa (M) | velocidade | 0 | `kokoro-onnx` + `/opt/kokoro/kokoro-v1.0.int8.onnx` (~92 MB) + `voices-v1.0.bin` (~28 MB) |
| `gemini` | nuvem | 107 vozes pt-BR nativas da biblioteca estendida (`GET /v1beta/voices`, com gênero/tom/persona) | estilo em texto (`speech_metadata.style`); **sem velocidade** | camada gratuita US$ 0; pago: ver tabela abaixo | `GEMINI_API_KEY` (projeto sem faturamento) |
| `espeak` | local | pt-br | velocidade, tom | 0 | `espeak-ng` (último recurso; robótico) |

Gemini TTS — `POST /v1beta/models/{model}:generateContent`, `responseModalities:["AUDIO"]`, `speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName`;
resposta `inlineData` (WAV 24 kHz mono). Modelos existentes na chave (conferido em 2026-11-21): `gemini-3.8-flash-lite-tts` (usado),
`gemini-3.8-flash-tts`, `gemini-3.1-flash-tts-preview`, `gemini-2.5-*-preview-tts`. Preços (pág. de preços, resumo): 3.8 flash-lite
US$ 0,50/1M tokens de texto e US$ 6/1M de áudio até 31/12/2026 (dobra em 2027); áudio = 25 tokens/s. Chamadas passam pelo
`AIGateway` (capacidade `speech`, escopo `lab` nas amostras): estimativa, reserva, ledger e idempotência.

## Correção de 2026-11-21 (feedback do PO: "vozes iguais, sotaque americano")
1. **Bug de armazenamento (meu):** `storage_key` usava `s.id` antes do flush → todas as amostras gravadas em `voices/samples/None.wav`; o
   laboratório tocava sempre o último áudio gerado. Corrigido (id explícito) + teste de regressão. Os vídeos do pipeline não foram afetados.
2. **Vozes en-US:** as 30 vozes da doc (Kore, Charon…) são `en-US`/"General American"; sem `languageCode` liam português com timbre americano.
   Agora: catálogo só com vozes `pt-BR` e `speechConfig.languageCode=pt-BR` em toda chamada.
3. Piper (`pt_BR`, espeak `pt-br`) e Kokoro (`lang=pt-br`, fonetização verificada: palatalização "dʒy/tʃy") estavam configurados corretamente.

## Identidade vocal da fábrica
`config.voice` (aditivo): `provider`, `voice_id`, `language`, `speed`, `pitch`, `style`, `instructions`, `params`, `fallback`.
Fábricas antigas (sem `provider`) continuam com Piper (voz padrão) → eSpeak se faltar, como antes. `PUT /api/voices/factories/{id}` salva.
`POST /api/voices/interpret` converte o pedido em linguagem natural numa sugestão **validada contra o catálogo real**; o que nenhum
provedor controla volta em `unsupported` (a UI avisa) e controles inexistentes são descartados.

## Pipeline
- Indisponibilidade do provedor (sem chave, modelo ausente) → fallback Piper (se `fallback=true`), com aviso no log e `fallback` na saída da etapa e no `metadados.json`.
- Falha em execução (limite de taxa, erro do provedor, áudio inválido) → a etapa **falha** (retry só se transitória); nunca conclui sem áudio. Retry de cenas já geradas no Gemini é reaproveitado (sem nova cobrança).
- Duração das legendas vem da duração real de cada WAV; o `export` valida vídeo × narração (±3%).

## Limitações
- Qualidade percebida (naturalidade, pronúncia, entonação) só pode ser julgada de ouvido: compare no laboratório.
- Gemini na camada gratuita tem limites de taxa não publicados; vídeos longos (dezenas de cenas) podem exigir retries.
- Kokoro é treinado principalmente em inglês; Gemini detecta o idioma sozinho (sem seletor de pt-BR vs pt-PT).
