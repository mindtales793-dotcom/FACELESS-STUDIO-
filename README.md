# Faceless Cloud Studio v4 · robô de vídeo

Painel web (FastAPI + FFmpeg) que transforma **narração + legendas (.SRT)** em vídeo faceless pronto, mostrando cada etapa que o robô executa.

## O que tem de novo na v4
- **Robô com processo visível**: 10 etapas (receber, ler legendas, buscar mídia, revisar, baixar, montar clipes, unir, mixar áudio, exportar, CapCut), progresso total, tempo por etapa e registro ao vivo. Dá para cancelar.
- **Fontes de mídia selecionáveis**: Pexels, Pixabay, Coverr (vídeos); Pexels, Pixabay, Unsplash, Openverse, Wikimedia Commons (fotos). Wikimedia e Openverse funcionam sem chave. Preferência vídeo/foto/misto, opções por fonte, idioma da busca e palavras extras.
- **14 templates de estilo** (Documentário, História em sépia, Noir, Mistério, Economia, Viral, Shorts, Notícia, Neon, VHS, Minimalista e os 3 baseados nos modelos Remotion: Documentário escuro, Documentário bíblico, Etiqueta de papel e apontamento) com prévia real. Cada um define cor, vinheta, grão, faixas de cinema, movimento, transição, legenda (frase ou palavra a palavra), formato e áudio. Tudo pode ser ajustado depois.
- **Destaques na tela** (aba Estilo): cartões de versículo (detecta citações como "1 Reis 11:4" na legenda), etiquetas de papel com linha tracejada apontando para a imagem (palavra-chave de cada cena) e barra de tópico no canto. Podem ser ligados em qualquer template. As posições das etiquetas são automáticas, em 4 pontos que se alternam.
- **Música de fundo**: biblioteca de trilhas, volume da música e da narração, redução automática da música quando a voz fala (ducking), fades, loop, normalização e prévia de 20 s do mix.
- **Importar no CapCut**: gera um pacote de rascunho (cenas, narração, música, legendas) com instalador.
- **Google Flow (IA)**: em cada cena, "Gerar com IA" cria uma imagem (Nano Banana) ou clipe (Veo). Veja abaixo.
- **Servidor MCP** (`mcp_server.py`) para usar a geração do Flow e consultar projetos pelo Claude.

## Rodar
**Windows (mais fácil):** instale o Python 3.11+ (marque "Add to PATH") e o FFmpeg (`winget install Gyan.FFmpeg`), extraia o zip e dê dois cliques em `INICIAR_WINDOWS.bat`. O navegador abre em http://localhost:3000.

**Manual:**
```bash
pip install -r requirements.txt     # precisa de FFmpeg instalado (com libass para legendas)
cp .env.example .env                # edite o .env com suas chaves (ou use Secrets do Replit)
python -m uvicorn main:app --port 3000
```
Docker: `docker build -t fcs . && docker run -p 3000:3000 --env-file .env -v $PWD/data:/app/data fcs`.
Defina `APP_PASSWORD` se publicar na internet. Use `DATA_DIR` em disco persistente.

## Remotion real (renderização de cenas animadas)

O render de cenas usa o Remotion de verdade (React + Chromium), não um fundo estático gerado pelo FFmpeg.

**Windows**
1. Instale Node.js 20 LTS ou superior.
2. Na pasta principal do projeto, execute `INSTALAR_REMOTION_WINDOWS.bat` uma vez. O script instala as dependências e prepara o Chromium.
3. Inicie o Faceless Studio normalmente com `INICIAR_WINDOWS.bat`.
4. Na aba de estilos de vídeo, selecione um estilo, escreva o texto da cena e clique em **Renderizar Cena Remotion**.

**Linux/macOS**
```bash
cd remotion
npm install
npx remotion browser ensure
cd ..
python -m uvicorn main:app --port 3000
```

O render padrão da interface é 720p para reduzir o uso de memória e CPU. A API aceita até Full HD dentro do limite de resolução. A primeira renderização demora mais porque precisa montar o bundle do Remotion; as seguintes reutilizam o cache de cenas idênticas.

Se o Chromium não iniciar, confirme que o navegador do Remotion foi instalado e que o Node.js está no PATH. A variável opcional `REMOTION_CHROMIUM_EXECUTABLE_PATH` permite informar o caminho de um Chromium/Chrome compatível.

## Fluxo
1. **Arquivos**: narração (MP3/WAV/M4A) e SRT. Sem narração? Gere pela Fish Audio na própria aba.
2. **Mídia, Estilo, Áudio, Saída**: escolha fontes, template, música e formato (16:9, 9:16, 1:1; 720p/1080p).
3. O robô busca e pré-escolhe a mídia. Revise as cenas (trocar opção, buscar de novo, enviar arquivo seu, gerar com IA). Com **piloto automático** ele monta direto.
4. Baixe o MP4 e, se quiser, o pacote do CapCut.

## Fila de montagem e lote
As montagens entram numa **fila global** e rodam uma por vez (`MAX_CONCURRENT_RENDERS`, padrão 1), para não travar o computador. Quem espera fica em "Montagem na fila" e pode ser cancelado. O piloto automático usa a mesma fila.
- `POST /api/projects/render-batch` enfileira vários projetos de uma vez (sem corpo = todos os que estão prontos para montar; ou `{"ids": [...]}`) e devolve o que entrou e o que foi ignorado, com o motivo.
- `GET /api/render-queue` mostra o que está montando e o que espera.
- Se o servidor cair ou for reiniciado no meio de uma busca ou montagem, ao subir de novo o projeto volta a "pronto" com suas escolhas mantidas (antes ficava preso em "montando").

## Google Flow e MCP: como funciona de verdade
O Google Flow **não tem API pública**. Existem MCPs da comunidade que automatizam o site do Flow dentro de um Chrome logado; são frágeis e podem violar os termos do serviço, por isso não os embutimos.
Aqui usamos os **mesmos modelos pela Gemini API** (`GEMINI_API_KEY`): Nano Banana (imagem) e Veo (vídeo, `FLOW_VIDEO_MODEL`). Consequências: o Veo é **cobrado por segundo** na sua chave, e os clipes **não aparecem no seu projeto do Flow**.

`mcp_server.py` expõe como MCP: `flow_status`, `flow_generate_image`, `flow_generate_video`, `list_studio_projects`, `studio_project_status`. Exemplo (Claude Desktop / Claude Code):
```json
{"mcpServers": {"faceless-studio": {"command": "python", "args": ["/caminho/mcp_server.py"],
  "env": {"GEMINI_API_KEY": "...", "DATA_DIR": "/caminho/data"}}}}
```

## Importar no CapCut
Baixe o zip → extraia → feche o CapCut → rode `INSTALAR_NO_CAPCUT.bat` (precisa de Python no Windows) → abra o CapCut. O instalador faz backup do `root_meta_info.json`.
**Limites:** feito para o CapCut desktop 8.x e **não foi testado no CapCut real** (o formato muda entre versões). Cor do template, vinheta, transições, ducking e os destaques na tela (cartões, etiquetas) ficam só no MP4. Se não abrir, use `legendas.srt` e a pasta Resources manualmente.

## Licenças e limites
Cada mídia mostra autor, origem e licença (há lista de créditos no projeto pronto). Confira antes de monetizar. Pixabay (cache 24 h), Unsplash (rastreio de download) e Coverr (crédito) têm regras próprias, já respeitadas. Fontes: Poppins, Anton, Bebas Neue, Archivo Black, DM Serif Display, Cinzel, EB Garamond (OFL, em `static/fonts`).
Render em 1080p é pesado em servidores com pouca CPU; valide em 720p.

## Google Flow e MCP: como funciona de verdade
O Google Flow **não tem API pública**. Existem MCPs da comunidade que automatizam o site do Flow dentro de um Chrome logado; são frágeis e podem violar os termos do serviço, por isso não os embutimos.
Aqui usamos os **mesmos modelos pela Gemini API** (`GEMINI_API_KEY`): Nano Banana (imagem) e Veo (vídeo, `FLOW_VIDEO_MODEL`). Consequências: o Veo é **cobrado por segundo** na sua chave, e os clipes **não aparecem no seu projeto do Flow**.

`mcp_server.py` expõe como MCP: `flow_status`, `flow_generate_image`, `flow_generate_video`, `list_studio_projects`, `studio_project_status`. Exemplo (Claude Desktop / Claude Code):
```json
{"mcpServers": {"faceless-studio": {"command": "python", "args": ["/caminho/mcp_server.py"],
  "env": {"GEMINI_API_KEY": "...", "DATA_DIR": "/caminho/data"}}}}
```

## Importar no CapCut
Baixe o zip → extraia → feche o CapCut → rode `INSTALAR_NO_CAPCUT.bat` (precisa de Python no Windows) → abra o CapCut. O instalador faz backup do `root_meta_info.json`.
**Limites:** feito para o CapCut desktop 8.x e **não foi testado no CapCut real** (o formato muda entre versões). Cor do template, vinheta, transições, ducking e os destaques na tela (cartões, etiquetas) ficam só no MP4. Se não abrir, use `legendas.srt` e a pasta Resources manualmente.

## Licenças e limites
Cada mídia mostra autor, origem e licença (há lista de créditos no projeto pronto). Confira antes de monetizar. Pixabay (cache 24 h), Unsplash (rastreio de download) e Coverr (crédito) têm regras próprias, já respeitadas. Fontes: Poppins, Anton, Bebas Neue, Archivo Black, DM Serif Display, Cinzel, EB Garamond (OFL, em `static/fonts`).
Render em 1080p é pesado em servidores com pouca CPU; valide em 720p.
