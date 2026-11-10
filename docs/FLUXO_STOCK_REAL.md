# Fluxo de vídeo faceless com mídia real

O modo padrão do FACELESS STUDIO passa a priorizar exclusivamente imagens e vídeos reais de bibliotecas stock. O modo fica em **Mídia → Somente bancos de mídia real**.

## Pipeline

1. **Áudio e SRT:** use o SRT sincronizado com a narração. Quando ele ainda não existe ou está estimado, gere novamente com Groq Whisper na aba Arquivos. A transcrição usa o áudio real e produz horários; não use o texto do roteiro como se fosse uma legenda sincronizada.
2. **Agrupamento semântico:** com `OPENROUTER_API_KEY` configurada, o OpenRouter agrupa cues consecutivos em cenas por ação/assunto. Ele só escolhe os pontos de corte: o texto e os timestamps originais do SRT são mantidos. Se a API falhar, o app usa o agrupamento temporal tradicional.
3. **Interpretação da cena:** o modelo de texto recebe a fala atual, o contexto do roteiro e os blocos vizinhos. Ele cria consultas concretas para o que deve aparecer na imagem, não apenas para o tema geral.
4. **Busca stock:** os provedores selecionados pesquisam fotos e vídeos. Novos projetos selecionam por padrão fontes stock disponíveis sem exigir YouTube. Bancos que exigem chave só entram automaticamente quando a chave está configurada.
5. **Verificação visual:** o modelo multimodal compara as miniaturas e os metadados com a fala exata. Resultados aprovados recebem uma nota; resultados incompatíveis são descartados. Se a verificação estiver indisponível, o cartão informa que a prévia ainda precisa ser conferida manualmente.
6. **Revisão:** confira a cena e sua mídia antes de renderizar. Uma miniatura não prova todo o conteúdo de um clipe; assista ao clipe antes de publicar.
7. **Render:** o app usa FFmpeg/Remotion para montar as cenas, sincronizar a narração e aplicar as legendas.

## Modelos OpenRouter

- `OPENROUTER_MODEL`: modelo textual que entende a fala e cria buscas.
- `OPENROUTER_VISION_MODEL`: modelo multimodal que precisa aceitar imagens e analisar miniaturas. O padrão sugerido é `google/gemini-2.5-flash`.

Os dois campos também podem ser ajustados em **Mídia** nas configurações do projeto. Configure a chave em **Chaves de API**.

## Configuração recomendada

- SRT: Groq Whisper, idioma detectado automaticamente.
- Agrupar SRT por significado: ativado.
- Somente bancos de mídia real: ativado.
- Preferência: misturar fotos e vídeos.
- OpenRouter textual e multimodal: modelo compatível com as tarefas.
- Piloto automático: desligado até revisar o primeiro projeto e confirmar a qualidade dos resultados.
- Fontes: marque Pexels/Pixabay quando tiver as respectivas chaves; mantenha Wikimedia, Openverse e Prelinger para complementar a pesquisa.

## Limites e direitos

- A IA sugere e verifica correspondência visual; não garante que cada frame do vídeo corresponda perfeitamente à fala.
- Confira licença, atribuição, autorização de pessoas/marcas e regras de monetização de cada arquivo.
- Fontes externas sem API pública confirmada abrem pesquisa no site e não fazem download automatizado.
- Não use vídeo do YouTube como stock sem permissão. O modo stock-only remove YouTube da seleção e esconde a importação.
