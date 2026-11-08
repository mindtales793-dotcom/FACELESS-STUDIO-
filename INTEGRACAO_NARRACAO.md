# 🎙️ Integração — Motor de Narração DarkCut (Node.js) + Faceless Cloud Studio (Python)

Este guia explica como integrar o pacote `darkcut-narration-integration` (Node.js/Express)
ao seu app Faceless Cloud Studio (Python/FastAPI), rodando na porta 3114.

## Arquivos criados

| Arquivo | Função |
|---------|--------|
| `server-narration.js` | Servidor Node.js com o router de narração (porta 3115) |
| `.env.narration` | Variáveis de ambiente do servidor Node.js |
| `narration_proxy.py` | Proxy Python que encaminha para o Node.js |
| `main.py` (editado) | Rotas de proxy `/api/narrations-proxy/*` |
| `INTEGRACAO_NARRACAO.md` | Este guia |

---

## 1. Instalar dependências do Node.js

No diretório `fcs/` (raiz do app):

```bash
cd "C:\Users\Lucas\Downloads\faceless_cloud_studio_v4 (1)\fcs"
npm init -y
npm install express dotenv
```

> O pacote `darkcut-narration-integration` já contém `src/narration-engine.js` e `src/narration-router.js`.
> Você precisará copiar a pasta `src/` do pacote para o seu app, ou ajustar o caminho no `server-narration.js`.

### Copiar os arquivos src do darkcut

```bash
# Exemplo: copiar src do pacote para o app
xcopy /E /I "C:\Users\Lucas\Downloads\darkcut-narration-integration\darkcut-narration-integration\src" "C:\Users\Lucas\Downloads\faceless_cloud_studio_v4 (1)\fcs\src\narration"
```

Após a cópia, a estrutura ficará:

```
fcs/
├── src/
│   └── narration/
│       ├── narration-engine.js
│       └── narration-router.js
├── server-narration.js        ← NOVO
├── narration_proxy.py         ← NOVO
├── .env.narration             ← NOVO
├── main.py                    ← EDITADO (rotas de proxy)
└── .env                       ← existente (APP_PASSWORD=12345678)
```

---

## 2. Configurar variáveis de ambiente

### .env (Python — já existe)
```env
APP_PASSWORD=12345678
```

### .env.narration (Node.js — novo)
Copie `.env.narration` para `.env` e configure:

```env
FISH_API_KEY=COLOQUE_SUA_CHAVE_AQUI
FISH_MODEL=s2.1-pro-free
NARRATION_CONCURRENCY=3
NARRATION_CHUNK_CHARS=450
NARRATION_CACHE_DIR=./data/narration-cache
NARRATION_OUTPUT_DIR=./data/narrations
PORT=3115
```

---

## 3. Iniciar os servidores

Você precisará de **dois terminais**:

### Terminal 1 — Python (porta 3114)

```powershell
cd "C:\Users\Lucas\Downloads\faceless_cloud_studio_v4 (1)\fcs"
Remove-Item Env:APP_PASSWORD -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 3114
```

### Terminal 2 — Node.js (porta 3115)

```powershell
cd "C:\Users\Lucas\Downloads\faceless_cloud_studio_v4 (1)\fcs"
copy .env.narration .env
node server-narration.js
```

---

## 4. Endpoints disponíveis

### Python (porta 3114) — Motor Python original
```
POST  /api/narrations                    # Criar narração (Python)
GET   /api/narrations/{id}               # Status
GET   /api/narrations/{id}/blocks        # Blocos
POST  /api/narrations/{id}/pause         # Pausar
POST  /api/narrations/{id}/resume        # Retomar
POST  /api/narrations/{id}/cancel        # Cancelar
POST  /api/narrations/{id}/redo          # Refazer
GET   /api/narrations/{id}/download      # Baixar MP3
GET   /api/narrations/{id}/subtitles     # Baixar SRT
```

### Python (porta 3114) — Proxy para Node.js (NOVO)
```
POST  /api/narrations-proxy              # Criar via Node.js
GET   /api/narrations-proxy/{id}         # Status via Node.js
DELETE /api/narrations-proxy/{id}        # Cancelar via Node.js
GET   /api/narrations-proxy/{id}/download # Baixar via Node.js
GET   /api/narrations-proxy/health       # Saúde do Node.js
```

### Node.js (porta 3115) — Servidor direto
```
POST  /api/narration/generate            # Criar narração
GET   /api/narration/{id}                # Status
GET   /api/narration/{id}/events         # SSE (progresso em tempo real)
DELETE /api/narration/{id}               # Cancelar
GET   /api/narration/{id}/download       # Baixar MP3
GET   /api/narration/health              # Saúde
```

---

## 5. Exemplo de uso (via proxy Python)

```python
import httpx

base = "http://127.0.0.1:3114"

# 1. Criar narração via Node.js (proxy)
resp = httpx.post(f"{base}/api/narrations-proxy", json={
    "text": "Seu roteiro aqui...",
    "reference_id": "ID_DA_VOZ",
    "model": "s2.1-pro-free",
    "speed": 1.0,
    "stability": 0.5,
    "expressiveness": 0.5,
    "max_concurrent": 4
})
job = resp.json()
job_id = job["id"]

# 2. Acompanhar status
st = httpx.get(f"{base}/api/narrations-proxy/{job_id}").json()
print(st["status"])  # "queued" | "running" | "completed" | "failed"

# 3. Baixar áudio
audio = httpx.get(f"{base}/api/narrations-proxy/{job_id}/download")
open("narracao.mp3", "wb").write(audio.content)
```

---

## 6. Exemplo de uso (SSE — progresso em tempo real)

Via Node.js diretamente (porta 3115):

```javascript
const evtSource = new EventSource("http://127.0.0.1:3115/api/narration/{jobId}/events");
evtSource.onmessage = (e) => {
  const item = JSON.parse(e.data);
  if (item.type === "progress") {
    console.log(`${item.percentage}% — ${item.completed}/${item.total} blocos`);
  }
  if (item.type === "job-completed") {
    console.log("Concluído!", item.result);
  }
};
```

---

## 7. Script para iniciar ambos os servidores (opcional)

Crie `iniciar-tudo.ps1` na raiz do `fcs/`:

```powershell
# Iniciar Python (porta 3114) em background
Start-Process powershell -ArgumentList "-Command `"cd '.'; Remove-Item Env:APP_PASSWORD -ErrorAction SilentlyContinue; .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 3114`""

# Iniciar Node.js (porta 3115) em background
Start-Process powershell -ArgumentList "-Command `"cd '.'; node server-narration.js`""

Write-Host "Servidores iniciando... Aguarde alguns segundos."
Write-Host "Python:  http://127.0.0.1:3114"
Write-Host "Node.js: http://127.0.0.1:3115"
```

---

## 8. Observações importantes

| Item | Detalhe |
|------|---------|
| **Duas linguagens** | Python (FastAPI) na porta 3114 + Node.js (Express) na porta 3115 |
| **Senha** | O Python usa `APP_PASSWORD=12345678`. O Node.js não tem autenticação por padrão (adicione se necessário). |
| **FFmpeg** | Obrigatório no sistema para montar os áudios. |
| **Chave Fish Audio** | Configure em `.env.narration` (Node.js) ou `.env` (Python). |
| **Cache** | O Node.js armazena cache em `NARRATION_CACHE_DIR`. O Python tem seu próprio cache. |
| **Produção** | Para vários usuários, use fila persistente (Redis/BullMQ) e autenticação. |

---

## 9. Teste rápido

```bash
# Terminal 1: Python
cd fcs && .\.venv\Scripts\python.exe -m uvicorn main:app --port 3114

# Terminal 2: Node.js
cd fcs && node server-narration.js

# Teste o health do Node.js
curl http://127.0.0.1:3115/api/narration/health

# Teste o proxy do Python
curl http://127.0.0.1:3114/api/narrations-proxy/health
```

---

Pronto! O motor de narração está integrado ao seu app. Escolha se quer usar o motor Python (narration_engine.py) ou o Node.js (server-narration.js) — ambos funcionam em paralelo.
