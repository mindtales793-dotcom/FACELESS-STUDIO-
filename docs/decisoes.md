# Decisões e Suposições — Faceless Cloud Studio

Este arquivo registra suposições tomadas ao implementar a especificação (seção 0) sobre o repositório existente `fcs`.

## Stack assumida (confirmada ao ler o repositório)
- Backend: FastAPI (`main.py`, `store.py`, `flow.py`, `groq_transcribe.py`, `providers.py`, `scenes.py`, `render.py`, `styles.py`, `keys_mgr.py`, `narration.py`, `capcut.py`, `youtube_mgr.py`, `storyblocks_mgr.py`).
- Frontend: HTML/JS/CSS vanilla em `templates/index.html`, `static/app.js`, `static/styles.css`.
- Render: FFmpeg via `render.py` + filtros ASS em `styles.py`.
- Estado: JSON por projeto em `data/<id>/project.json` via `store.py` (`read_state`/`write_state`/`patch_state`).
- Chaves: `.env` + tela de Chaves de API (`keys_mgr.py`), nunca logadas.

## Suposições (registro)
1. **Provider interfaces**: serão criadas em `providers_base.py` como classes abstratas simples (não usaremos ABC pesado, apenas classes base com métodos esperados). Implementações concretas herdam e podem ser trocadas sem mudar o pipeline.
2. **Job queue**: fila simples em memória + persistência em `data/jobs/` com retry e backoff exponencial. Não usaremos Redis/Celery para manter a stack leve.
3. **Provedores de mídia**: Wikimedia Commons, NASA, NARA, Openverse, Pexels, Pixabay e YouTube (CC) serão integrados atrás de `MediaProvider`. YouTube só retorna `videoLicense=creativeCommon` por padrão; download de arquivo fica atrás de `MediaFetcher` (implementação concreta a ser decidida pelo dono — não contornamos proteções/ToS).
4. **Modelos de IA**: ficam em configuração (`FLOW_IMAGE_MODEL`, `FLOW_VIDEO_MODEL`, `GEMINI_API_KEY`, etc.), nunca fixos no código.
5. **SRT opcional**: uso do SRT no Flow Blocos é opt-in (`use_srt`). Não forçamos SRT onde o usuário quer só texto.
6. **Letterbox**: desativado por padrão em todos os templates (vídeo em tela cheia conforme resolução).
7. **Remotion/HeyGen/Nano Banana/GPT Image**: modelos e IDs vêm de variáveis de ambiente; integração assíncrona e tolerante a falhas.
8. **Custos/ledger**: gravado em `data/costs/` como JSON por chamada, usado na aba Gastos.
9. **Créditos**: `creditos.txt` gerado no final do render com metadados de licença/autor de cada asset.

## Decisões de projeto
- Nenhuma funcionalidade existente foi removida; apenas acrescentei.
- Erro em etapa opcional (avatar, trilha, thumbnail) não derruba o projeto.
- Retry com backoff exponencial em chamadas externas.
