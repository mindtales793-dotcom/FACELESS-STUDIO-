# Plano de Implementação — Faceless Cloud Studio

Stack mantida: FastAPI + vanilla JS + FFmpeg. Nada do existente é removido.

## Módulos e arquivos (ordem de criação)

### Phase 1 — Infraestrutura base (esta fase)
- `docs/decisoes.md` — suposições e decisões (criado)
- `providers_base.py` — interfaces abstratas: `MediaProvider`, `ImageGenProvider`, `VideoGenProvider`, `AvatarProvider`, `MediaFetcher`
- `job_queue.py` — fila assíncrona com retry + backoff exponencial, persistência em `data/jobs/`
- `cost_ledger.py` — ledger de custos por chamada (projeto, etapa, provedor, modelo, unidades, custo, timestamp)
- `project_config.py` — gerenciamento do JSON de configuração do projeto (seção 10 da especificação)
- `main.py` — rotas de infra: `/api/jobs`, `/api/costs`, `/api/config/{project_id}`

### Phase 2 — Módulo CENAS (filmagem real)
- `scene_planner.py` — LLM gera 2–4 consultas de busca por cena + descrição visual
- `media_providers.py` — implementações: Wikimedia, NASA, NARA, Openverse, Pexels, Pixabay, YouTube (CC)
- `media_fetcher.py` — interface para aquisição de arquivo (YouTube sem download automático)
- `main.py` — rotas de cenas: busca, prioridade, modo de busca, cena para_conferir

### Phase 3 — Cenas por IA + Motion Graphics
- `ia_scenes.py` — Nano Banana 2.1, GPT Image, Gemini Omni (modelo de vídeo em config)
- `remotion_renderer.py` — worker Remotion para animações (modos equilibrado/cheio/identidade)
- Estilos/subestilos com paleta e cor por projeto

### Phase 4 — Montagem e Acabamento
- Corte de silêncios (`silenceremove`), Ken Burns (`zoompan`), transições `xfade`, fades início/fim
- Modo montagem: `parar_se_faltar` vs `direto`
- Thumbnail (Nano Banana/GPT Image, texto por código)

### Phase 5 — Avatar + Trilha
- `avatar_provider.py` — HeyGen assíncrono, tolerante a falhas
- Trilha: upload, níveis (sutil/presente/marcante), ducking, loudnorm

### Phase 6 — Painel, Gastos e Créditos
- Tela de acompanhamento por projeto com status de cada etapa
- Aba Gastos: ledger de custos, totais por período, export CSV
- `creditos.txt` gerado ao final do render

## Critérios de aceitação por fase (resumo)
- Phase 1: jobs rodam, retry funciona, ledger grava, config JSON salva/lê.
- Phase 2: dado um SRT, toda cena recebe mídia ou fica `para_conferir`, licença registrada.
- Phase 3: personagem consistente em 5 cenas; Remotion gera animações distintas por modo.
- Phase 4: MP4 final com tempos sincronizados ao áudio cortado.
- Phase 5: falha do HeyGen não impede o vídeo; narração inteligível sobre música.
- Phase 6: painel mostra status, gastos exportáveis, créditos gerados.
