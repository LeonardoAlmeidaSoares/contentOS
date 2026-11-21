# YouTube — configuração e operação (Missão 2)

Fluxo: produção concluída → **Aprovações** (aprovar / solicitar alterações / rejeitar) → **Publicar como privado** (revisão de metadados + confirmação explícita).
Aprovar nunca publica. Só `privacy=private`; sem público, sem agendamento.

## Google Cloud (ação do PO; o ContentOS não cria nada lá)
1. console.cloud.google.com → criar projeto (ex.: "ContentOS"). **Não ative faturamento** (não é necessário).
2. APIs e serviços → Biblioteca → ativar **YouTube Data API v3**.
3. Tela de consentimento OAuth → tipo *Externo* → status *Testing* → adicionar sua conta Google em **Usuários de teste** →
   escopos: `.../auth/youtube.upload` e `.../auth/youtube.readonly` (mínimos: enviar vídeos + identificar o canal).
4. Credenciais → Criar credenciais → ID do cliente OAuth → tipo **App para computador** (Desktop). Copie ID e segredo.
5. No `.env`: `YOUTUBE_CLIENT_ID=…` e `YOUTUBE_CLIENT_SECRET=…`; `docker compose up -d`.

## Por que o fluxo "copiar e colar a URL"
O Google não aceita IP de rede local (192.168.x.x) nem HTTP como redirecionamento de clientes web. Clientes *Desktop* aceitam loopback
(`http://127.0.0.1:8302/`). Como o navegador do PO não roda no servidor, nada escuta nessa porta: após autorizar, o navegador mostra um erro de
conexão e o PO cola a URL da barra de endereços no Studio (state + PKCE S256 validados, uso único, 15 min). Sem domínio, sem HTTPS, sem expor o servidor.

## Limites conhecidos
- Em modo *Testing*, o refresh token expira em ~7 dias (reconectar em Configurações). Publicar o app exige verificação do Google.
- Projetos de API não auditados enviam vídeos restritos a privados — compatível com esta missão.
- Cota padrão 10.000 unidades/dia; `videos.insert` custa 1.600 (≈6 envios/dia).
- Envio retomável (8 MiB por bloco). Falha de rede sem confirmação → estado "incerto" e **nenhum reenvio automático**; "Verificar envio" consulta a sessão antes de enviar qualquer byte.
