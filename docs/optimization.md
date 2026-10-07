# Otimização do streaming — v0.2

Medições locais em 7 de outubro de 2026. Não representam garantia de desempenho em outra máquina. As mudanças mantêm a densidade configurada pelo usuário: 8.000 candidatos a tufos de grama por chunk.

## Construção dos meshes

Antes, o worker gerava somente posições. `World.commit` calculava triângulos, normais e cores e fazia chamadas Python por vértice na thread principal. Agora os workers preparam buffers NumPy completos. Árvores e pedras usam templates calculados uma vez, transformados em lote. A thread principal copia buffers em bloco para o Panda3D.

| Chunk | Montagem CPU anterior | Preparação no worker | Montagem CPU nova, total | Maior etapa individual |
|---|---:|---:|---:|---:|
| 0,0 | 68,3 ms | 27,6 ms | 4,1 ms | 0,87 ms |
| 1,0 | 118,9 ms | 35,9 ms | 4,9 ms | 0,82 ms |
| 1,1 | 114,7 ms | 35,1 ms | 5,7 ms | 0,86 ms |

Os totais novos incluem mais objetos de grama que antes: células menores e um segundo LOD. Essas medidas usam um scene graph sem janela e **não incluem upload/execução GPU**. O carregamento inicial continua síncrono; durante a exploração, o total é dividido entre frames. O limite padrão é 2 ms e até 8 passos por frame. Cada passo é indivisível, portanto o orçamento pode ser ultrapassado.

## Visibilidade, densidade e cache

- Grama dividida em células de 16 × 16 metros, com bounds que incluem o deslocamento do vento. O frustum culling do Panda3D pode descartar uma célula fora da visão sem enviar o batch inteiro do chunk.
- LOD próximo com cinco lâminas; distante com duas. As três lâminas extras encolhem entre 20 e 32 metros, antes da troca de mesh pela distância do centro da célula a 45 metros. A camada restante mantém o fade anterior entre 55 e 90 metros. Células a mais de 105 metros são ocultadas.
- Cache LRU de até oito chunks e 96 MiB estimados em vértices/índices. Os nós ficam destacados da cena e não são renderizados. Retornar reutiliza os meshes; fauna ausente é recriada sem duplicar os patos que ainda estão carregados.
- Trabalhos em andamento são limitados a quatro, contando o upload parcial. Mudanças de densidade invalidam o cache e os resultados antigos. Chunks em construção só entram na cena quando completos.

O cache troca memória por menor custo de reconstrução. Seu limite em MiB não inclui overhead dos objetos, cópias do driver ou alocações GPU. GPU instancing e occlusion culling continuam como evoluções futuras.

## Pausas causadas pelo painel

O painel chamava `SceneGraphAnalyzer` a cada 0,4 segundo. Esse analisador examina os arrays de vértices; com a grama densa, apareciam pausas periódicas de aproximadamente 260 ms. A v0.2 consulta apenas contagens de primitivas, sem essa varredura. Os números continuam descrevendo geometria residente, incluindo LODs ocultos, e não draw calls reais.

## Validação final

Comando usado:

```powershell
.\run.cmd --offscreen --benchmark 20 --benchmark-route streaming --radius 2 --shadows low
```

Seed 938472, 1280 × 720, Windows, Panda3D 1.10.16, VSync desligado. A rota atravessa bordas de chunks e retorna; começa a registrar após os chunks iniciais estarem prontos.

| Métrica | Resultado |
|---|---:|
| Frames / duração medida | 2.128 / 20,005 s |
| FPS médio | 106,4 |
| Frame p50 / p95 / p99 | 8,91 / 12,86 / 21,21 ms |
| Pior frame | 43,06 ms |
| Frames acima de 33,3 ms | 1 |
| Pico CPU do streaming, incluindo aquecimento | 8,67 ms |
| Chunks residentes / em cache | 25 / 8 |
| Chunks restaurados do cache | 3 |
| Tufos de grama residentes | 183.722 |
| Patos residentes | 124 |
| Working set ao final | 973 MiB |

O resultado é offscreen e não equivale a uma sessão interativa em janela. O benchmark anterior à troca do analisador, já com a montagem nova, teve 50 frames acima de 33 ms em 20 segundos. Como a simulação limita o delta em frames longos, o caminho percorrido difere entre essas execuções; esse contraste não é um A/B controlado de FPS.

Vinte testes verificam determinismo, bordas, colisões, comportamento dos patos, buffers, LOD, cache, invalidação e cancelamento de uploads parciais. A renderização offscreen com sombras baixas foi validada e a captura foi inspecionada. Os CSVs da v0.2 usam `benchmarks/history-v0.2.csv`; o arquivo antigo permanece intacto.
