# Cycle Time Analysis — Guia de Deploy

Mesmo padrão do CAPI (`CT0DEVTEFSRV01`, `10.21.157.22`).

```
Usuário (browser)
   │
   ▼
https://ct0devtefsrv01.br.bosch.com/CycleTimeAnalysis      ← Frontend (IIS, 443)
   │  (fetch/XHR com o ID do usuário na URL)
   ▼
https://ct0devtefsrv01.br.bosch.com:48001                   ← Backend (cycletime_api.exe)
   │
   ▼
data\users\u_<id>\project.json + videos\                     ← arquivos (sem banco)
```

> ⚠️ Confirme que a porta **48001** está livre/liberada no firewall (o CAPI usa 48000).
> Se mudar a porta, ajuste também `frontend/.env.production` e refaça o build.

## 1. Pastas no servidor

| O quê | Caminho |
|---|---|
| Frontend | `D:\inetpub\Bosch\AplicationHTTPS\CycleTimeAnalysis\` (conteúdo de `dist\` + `web.config`) |
| Backend | `D:\inetpub\Bosch\WebCoreAPIHTTPS\CycleTimeAnalysis\` (conteúdo de `dist\cycletime_api\`) |
| Certificados | `cert.pem` e `key.pem` ao lado do `.exe` (os mesmos do CAPI servem — mesmo host) |
| Dados | `data\` ao lado do `.exe` (criada automaticamente, **não é sobrescrita** nos deploys) |

## 2. Workspaces por ID

- Cada navegador gera um ID (UUID) no primeiro acesso e o guarda no `localStorage`.
- Tudo é gravado em `data\users\u_<id>\` — um usuário nunca vê o que é de outro.
- Para abrir o mesmo workspace em outro PC: **Config → Meu ID → Copiar**, e no outro
  navegador **Config → Usar outro ID**.
- Não há senha: quem souber o ID acessa o workspace. Para rede interna é suficiente;
  para algo mais restrito, o próximo passo seria autenticação (Windows Auth).

## 3. Limites

| Limite | Padrão | Como mudar |
|---|---|---|
| Duração do vídeo | **10 min** | `--max-video-seconds 600` + `VITE_MAX_VIDEO_SECONDS` no front |
| Tamanho do arquivo | 2048 MB | `--max-video-mb 2048` |
| Pré-processamentos simultâneos | 2 (os outros esperam na fila) | `--max-concurrent-preprocess 2` |

O front recusa vídeos longos antes de enviar; o backend valida de novo (e devolve 413 com a mensagem).

## 4. Build

**Frontend** (PC de desenvolvimento):
```powershell
cd frontend
cat .env.production     # confira VITE_API_BASE_URL e VITE_MAX_VIDEO_SECONDS
npm install
npm run build
# copiar o conteúdo de dist\ + deploy\web.config para a pasta do frontend no servidor
```

**Backend** (PC de desenvolvimento, venv do backend ativo):
```powershell
pyinstaller cycletime_api.spec --noconfirm --clean
# copiar a pasta dist\cycletime_api\ inteira (exe + _internal + python_worker) para o servidor
```

## 5. Iniciar o backend

Manual (teste):
```powershell
cd D:\inetpub\Bosch\WebCoreAPIHTTPS\CycleTimeAnalysis
.\cycletime_api.exe --host 0.0.0.0 --port 48001 `
  --ssl-certfile cert.pem --ssl-keyfile key.pem `
  --cors-origins https://ct0devtefsrv01.br.bosch.com `
  --log-file logs\api.log
```

Como serviço: um `.exe` de console **não** é um serviço Windows nativo (`New-Service`
direto costuma falhar com erro 1053). Use o **NSSM** (como o `.spec` já prevê) — confirme
como o `capi_api.exe` roda hoje no servidor e repita o mesmo método.

## 6. Verificação

- `https://ct0devtefsrv01.br.bosch.com:48001/health` → `{"status":"ok"}`
- `https://ct0devtefsrv01.br.bosch.com/CycleTimeAnalysis` → abre o app
- Config → deve mostrar **Meu ID** e "Vídeo: máx. 10 min"
- Carregar um vídeo > 10 min → deve aparecer a mensagem de limite

## 7. Troubleshooting

| Sintoma | Causa provável |
|---|---|
| "Failed to fetch" na 1ª vez | Aceitar o certificado em `https://...:48001/health` (uma vez por browser) |
| "Failed to fetch" sempre | Backend parado, porta bloqueada, ou `--cors-origins` diferente da URL do front |
| Vídeo recusado (413) | Passou de 10 min ou do limite de MB |
| Pré-processamento demora | Fila: só N vídeos são processados ao mesmo tempo |
| Disco enchendo | Vídeos ficam em `data\users\*\videos\` — limpe workspaces antigos periodicamente |
