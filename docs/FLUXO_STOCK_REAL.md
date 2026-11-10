# Fluxo de vídeo faceless com mídia real

O modo padrão do FACELESS STUDIO passa a priorizar exclusivamente imagens e vídeos reais de bibliotecas stock. O modo fica em **Mídia → Somente bancos de mídia real**.

## Pipeline

1. **Áudio e SRT:** use o SRT sincronizado com a narração. Quando ele ainda não existe ou está estimado, gere novamente com Groq Whisper na aba Arquivos. A transcrição usa o áudio real e produz horários; não use o texto do roteiro como se fosse uma legenda sincronizada.
2. **Agrupamento semântico:** com `OPENROUTER_API_KEY` configurada, o OpenRouter agrupa cues consecutivos em cenas por ação/assunto. Ele só escolhe os pontos de corte: o texto e os timestamps originais do SRT são mantidos. Se a API falhar, o app usa o agrupamento temporal tradicional.
3. **Interpretação por bloco SRT:** cada cena mantém uma lista dos cues originais, com identificador, texto e timestamps individuais. O modelo recebe a fala de cada cue separadamente, além do contexto geral e dos blocos vizinhos, e devolve um plano visual e consultas próprias para cada bloco. As consultas específicas dos cues têm prioridade na busca; a consulta geral da cena é apenas complementar. O agrupamento visual não reescreve nem desloca os horários originais.
4. **Busca stock e YouTube:** os provedores pesquisam fotos e vídeos reais. O YouTube também pode retornar candidatos, mas eles são apenas prévias e não entram no render automaticamente.
5. **Localização do momento no YouTube:** dentro da cena, escolha um candidato ou cole um link e confirme que possui direitos/licença/permissão para reutilizá-lo. O OpenRouter recebe o link como vídeo com processamento temporal `agentic`, junto com a fala exata e o contexto do SRT; o modelo retorna os tempos do momento visualmente compatível. O app baixa somente aquela seção, aplica o teto configurado (máximo absoluto de 10 s), extrai um quadro do mesmo intervalo e adiciona ambos à cena.
6. **Verificação visual:** o modelo multimodal compara miniaturas e metadados dos bancos stock com a fala exata. Candidatos do YouTube não são aprovados pela miniatura: precisam da análise temporal descrita acima.
7. **Revisão:** confira o trecho selecionado e a licença, a atribuição e as autorizações antes de renderizar/publicar.
8. **Render:** o app usa FFmpeg/Remotion para montar as cenas, sincronizar a narração e aplicar as legendas.

## Modelos OpenRouter

- `OPENROUTER_MODEL`: modelo textual que entende a fala e cria buscas.
- `OPENROUTER_VISION_MODEL`: modelo multimodal que precisa aceitar imagens e analisar miniaturas. O padrão sugerido é `google/gemini-2.5-flash`.

Os dois campos também podem ser ajustados em **Mídia** nas configurações do projeto. Configure a chave em **Chaves de API**.

## Configuração recomendada

- SRT: Groq Whisper, idioma detectado automaticamente.
- Agrupar SRT por significado: ativado.
- Geração de mídia por IA: desativada quando quiser usar somente arquivos reais; YouTube continua como banco opcional de candidatos.
- Preferência: misturar fotos e vídeos.
- OpenRouter textual e multimodal: modelo compatível com as tarefas.
- Piloto automático: desligado até revisar o primeiro projeto e confirmar a qualidade dos resultados.
- Fontes: marque Pexels/Pixabay quando tiver as respectivas chaves; mantenha Wikimedia, Openverse e Prelinger para complementar a pesquisa.

## Limites e direitos

- A IA sugere e verifica correspondência visual; não garante que cada frame do vídeo corresponda perfeitamente à fala.
- Confira licença, atribuição, autorização de pessoas/marcas e regras de monetização de cada arquivo.
- Fontes externas sem API pública confirmada abrem pesquisa no site e não fazem download automatizado.
- Candidatos do YouTube não são baixados nem renderizados automaticamente. A importação exige confirmação explícita de que o usuário tem licença ou autorização; o aplicativo não consegue comprovar essa declaração nem verificar direitos automaticamente.
- O trecho importado do YouTube é limitado a no máximo 10 segundos, mesmo que o vídeo original seja longo. O quadro salvo vem do mesmo intervalo.
- Use um modelo OpenRouter compatível com entrada de vídeo para localizar o momento temporal; a análise pode errar e o resultado precisa ser revisado antes de publicar.


## Integridade dos blocos SRT

- Cada cue original é preservado dentro da cena em `source_cues`, com ID estável, fala literal, início e fim.
- A IA recebe os cues individualmente e devolve `cue_visual_plans`; cada plano contém consultas, descrição visual, preferência por foto/vídeo e pontuação de movimento.
- A busca usa primeiro as consultas específicas de cada cue e depois as consultas gerais da cena. Assim, uma frase como “São Paulo, 1970...” pode buscar imagens históricas daquele local e período, sem se perder em uma consulta genérica sobre urbanização.
- Se o provedor não devolver planos por cue, o fallback mantém um plano textual individual para cada bloco. Nenhum texto ou timestamp é inventado.


## Sincronização visual por bloco

- O pipeline cria uma cena para cada cue SRT, sem juntar blocos por ritmo ou por interpretação semântica.
- Cada cena herda o ID, o texto literal, o início e o fim do cue. A busca visual e a seleção de mídia acontecem separadamente para cada bloco.
- A montagem ordena as cenas pelos timestamps do SRT; o início de cada mídia acompanha o início do bloco correspondente. A mídia fica ativa do início ao fim do cue; se houver intervalo vazio antes do próximo cue, o último quadro é mantido até o próximo início. Assim, o próximo bloco nunca começa antes do timestamp do SRT.
- Não há mais limite de 120/1000 cenas aplicado ao agrupamento: todos os cues são mantidos individualmente. Isso evita descartar ou juntar blocos e permite que cada um receba sua própria mídia.
- O menu não exibe mais Flow AI, Flow Blocos nem Roteiros (Skills). Os estilos de vídeo continuam disponíveis.
