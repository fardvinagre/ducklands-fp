# Vegetação — v0.3

## Mudanças visuais

- Densidade padrão de grama aumentada de 8.000 para 12.000 candidatos a tufos por chunk (+50%). Candidatos sobre lagos continuam sendo rejeitados.
- Lâminas com dois segmentos e ponta curvada, três triângulos por lâmina e cinco vértices compartilhados por índices. A geometria indexada evita armazenar nove vértices para esses três triângulos.
- Cores com gradiente entre raiz, meio e ponta, variação por lâmina e manchas de tonalidade no campo. O vento afeta progressivamente o meio e a ponta.
- Árvores com troncos afunilados, variação de tons da casca, raízes e galhos. Pinheiros têm cinco camadas de folhagem. Árvores de copa larga têm sete grupos de folhas com contorno irregular e cores por face.
- Três templates por espécie, rotação e tonalidade por árvore. Os templates são preparados uma vez; os workers transformam os buffers em lote.

## Controle de custo

Continuam ativos os workers, o orçamento de montagem por frame, o culling da grama em células de 16 metros e o cache limitado. Para acomodar os detalhes, a troca para o LOD simples da grama ocorre a 36 metros do centro da célula. As três lâminas extras encolhem entre 14 e 24 metros, antes da troca. O LOD distante conserva duas lâminas de um triângulo cada por tufo. As árvores distantes mantêm meshes simples e silhuetas próprias de cada espécie.

O cache restaura os chunks solicitados antes de inserir os que saíram do alcance, evitando expulsar uma região que o jogador acabou de voltar a visitar. O limite de 96 MiB permanece; meshes maiores significam menos chunks guardados nesse limite.

## Validação

23 testes passaram, incluindo topologia e índices das lâminas, subconjunto do LOD, normais e variantes dos templates, streaming e retorno pelo cache. A renderização offscreen com sombras baixas foi executada e a captura foi inspecionada.

Benchmark final local, 20 segundos, seed 938472, 1280 × 720, raio de dois chunks, sombras LOW:

```powershell
.\run.cmd --offscreen --benchmark 20 --benchmark-route streaming --radius 2 --shadows low
```

| Métrica | Resultado |
|---|---:|
| FPS médio | 103,1 |
| Frame p50 / p95 / p99 | 9,03 / 14,42 / 23,08 ms |
| Pior frame | 33,12 ms |
| Frames acima de 33,3 ms | 0 |
| Chunks residentes / cache | 25 / 5 |
| Retornos pelo cache | 5 |
| Tufos residentes | 275.563 |
| Árvores residentes | 741 |
| Working set final | 1.369 MiB, aproximadamente 1,34 GiB |

São resultados de uma execução offscreen, não uma garantia de desempenho em janela ou em outras máquinas. Há maior consumo de memória que na v0.2. O total de triângulos do painel inclui LODs ocultos; não equivale ao total desenhado por frame. Os resultados desta versão são registrados em `benchmarks/history-v0.3.csv`, preservando o histórico anterior.

Para ajustar a densidade, altere `grass_per_chunk` em `game/config.py`. F6 continua permitindo aumentar a densidade durante o jogo.
