# Água — v0.5

Referência: Wang et al., *Physics-based fluid simulation in computer graphics: Survey, research trends, and challenges* (2024), DOI [10.1007/s41095-023-0368-y](https://www.sciopen.com/article/10.1007/s41095-023-0368-y). 

O artigo é uma revisão de métodos. Esta implementação adapta a ideia de **simulação restrita à superfície**, discutida na seção 8.1, páginas 27–28 do PDF (829–830 impressas). Também aplica a separação entre a simulação mais grossa e detalhes finos de aparência. Não implementa o método iWave, o método de síntese de wakes citado pelo artigo, SPH nem Navier–Stokes completo.

## Modelo implementado

Cada lago carregado possui uma grade de 65 × 65 amostras de altura e velocidade vertical. A evolução segue uma aproximação linear de ondas de superfície em água rasa:

`h_tt = div(g · depth · grad(h)) − damping · h_t`

As profundidades vêm dos mesmos triângulos usados pelo terreno renderizado e pelas colisões. Fluxos nas faces da grade são simétricos; células secas bloqueiam propagação. A profundidade usada na velocidade de propagação fica limitada a 1,5 m. Impulsos locais têm compensação de média para não adicionar volume ao lago. Ondas se propagam, interagem com as bordas e amortecem progressivamente.

O passo fixo é de até 1/60 s, limitado pelo critério CFL bidimensional, com no máximo quatro subpassos por frame. Frames muito longos descartam atraso acumulado. Um limite de deslocamento de ±12 cm mantém estáveis os testes com forças excessivas; quando acionado, esse limitador pode alterar a conservação de volume.

Patos nadando e o jogador dentro da água geram impulsos após deslocamentos de 30 cm. Teletransportes acima de 3 m são ignorados. Os impulsos de posições atual/anterior produzem rastros. A altura visual dos patos acompanha uma amostragem bilinear da superfície; colisões e velocidade do jogador continuam usando o nível médio do lago.

## Renderização e custo

- A GPU desloca os vértices pela altura simulada e combina as inclinações com ondulações finas de vento.
- O material combina Fresnel, reflexo analítico do céu, brilho solar, cor e transparência por profundidade, espuma nas margens e nas ondulações fortes. As normais das ondas têm amplificação artística para o estilo do jogo.
- Texturas RGBA float carregam altura, duas derivadas e profundidade, atualizadas no máximo a 30 Hz. Cada campo tem aproximadamente 66 KiB.
- Somente os quatro lagos mais próximos, a menos de 110 m da margem, têm física ativa. Lagos mais distantes conservam o detalhe de vento no shader; suas perturbações são reiniciadas ao trocar de estado.
- Superfícies são carregadas até 200 m da margem, no máximo uma criação por frame, e removidas ao sair desse raio. O frustum culling do Panda3D usa limites que incluem a deformação vertical. Uma criação individual ainda pode produzir um pico de CPU.
- Pausar congela a física e o tempo do material. A contagem e o tempo de CPU da água aparecem no JSON/CSV do benchmark.

O reflexo representa o céu, sem renderizar novamente árvores, terreno ou patos. Ainda não há refração geométrica, reflexos planares/SSR, espuma transportada, volumes de respingos ou correntes com transporte de massa. O vento fino altera as normais, não a altura da grade. São escolhas para manter o custo controlado.

## Validação

Os 33 testes do projeto passaram. Os testes de água verificam propagação, compensação de volume, amortecimento, estabilidade sob impulsos excessivos, limite de subpassos, bloqueio por uma barreira seca, profundidade coerente com colisões, ordem dos canais da textura, limites de culling, geração de wakes, pausa, descarregamento e limite de quatro lagos ativos. Capturas offscreen com 25 chunks e 948.845 tufos foram inspecionadas; os shaders renderizaram sem erros.

Ensaio isolado de 1.200 atualizações da água, com dois lagos ativos e jogador em movimento, sem renderização GPU: mediana **0,48 ms**, p95 **0,95 ms**, pior atualização **6,65 ms**. A primeira criação foi excluída, mas as criações subsequentes permanecem nessa amostra. Esses valores não incluem desenho na GPU nem IA dos patos.

Benchmark dentro da água: 20 s, 1280 × 720, sombras LOW, densidade 40.000, seed 938472, rota `water`: **72,1 FPS**, p50/p95/p99 **13,03 / 20,84 / 28,75 ms**, pior frame **41,59 ms**, **2 de 1.442** frames acima de 33,3 ms. Ao final: 25 chunks, 948.845 tufos, dois lagos ativos e aproximadamente 2.230 MiB de RAM.

Primeira medição de streaming com a água nova: **74,6 FPS**, p95 **27,37 ms**, p99 **48,52 ms**. Uma execução de referência na mesma sessão, usando temporariamente o material e a geometria antigos, marcou **81,6 FPS**, p95 **23,50 ms**, p99 **35,10 ms**. Isso indica custo adicional; a comparação não isola perfeitamente a água porque carregamento e fauna dependem do tempo de execução. A medição histórica v0.4 era 86 FPS.

Repetição com o código final: **78,4 FPS**, p95 **25,85 ms**, p99 **40,84 ms**, pior frame **62,71 ms**, 36 de 1.569 frames acima de 33,3 ms. Ao final havia 22 chunks prontos, três trabalhos em andamento e 846.481 tufos. A referência antiga está identificada no CSV como `offscreen/streaming/reference-v04-water`.

```powershell
.\run.cmd
.\run.cmd --offscreen --smoke --benchmark-route water --frames 300
.\run.cmd --offscreen --benchmark 20 --benchmark-route water --shadows low
.\run.cmd --offscreen --benchmark 20 --benchmark-route streaming --shadows low
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Resultados offscreen são locais à máquina e não garantem desempenho em janela ou em outro hardware. O histórico desta etapa usa `benchmarks/history-v0.5.csv`. As distâncias e o limite de lagos ficam em `WaterSystem`, em `game/world/water.py`.

## Contornos e integração das margens

[Prévia da margem e do contorno irregular](lake-shoreline-v0.5.png).

Os lagos agora usam um perfil radial assimétrico, combinando três harmônicos com uma fase derivada da seed e da posição de cada lago. Isso gera alongamentos, enseadas e variações entre lados opostos. A extensão máxima é limitada para manter o streaming e a grade de 65 × 65. O lago inicial varia aproximadamente entre 12 e 22,6 m de raio conforme a direção.

O mesmo perfil define a depressão do terreno e o limite amostrado pela textura de profundidade. O shader deixa de recortar um círculo: a presença de água depende da profundidade sobre os triângulos do terreno. Consultas de água para colisões e comportamento dos patos usam esses mesmos triângulos. A interpolação da textura ainda pode produzir diferenças submétricas na linha d'água.

A altura do terreno continua subindo após a margem, eliminando o anel plano anterior. Tons de solo úmido se misturam gradualmente à cor do terreno, com largura variável por ruído procedural. A grama chega à margem seca em manchas, ficando menor e menos densa perto da água. Árvores e pedras mantêm um pequeno afastamento. O posicionamento próximo dos lagos considera a altura efetiva dos triângulos, evitando vegetação submersa ou flutuando na encosta.

As consultas escalares de altura possuem um cache LRU de até 64 grades de terreno. O cache conserva a mesma interpolação dos triângulos, limita a memória e evita recalcular ruído e contornos nas consultas frequentes de jogador/patos. Workers continuam usando o caminho NumPy vetorizado.

**Validação desta alteração:** 36 testes passaram, incluindo assimetria e limites do contorno, coerência entre profundidade e detecção de água, subida da margem, equivalência entre consultas escalares/vetorizadas e limite do cache. Capturas da margem e de uma vista elevada foram inspecionadas. Um smoke com 25 chunks carregou cerca de 967 mil tufos e renderizou sem erros.

Benchmark de streaming de 20 s com o cache de altura, seed 938472, 1280 × 720, sombras LOW, 40.000 candidatos por chunk: **79,4 FPS**, p50/p95/p99 **10,17 / 26,70 / 44,58 ms**, pior frame **86,61 ms**, **41 de 1.588** frames acima de 33,3 ms. Ao final: 22 chunks prontos, três trabalhos em andamento, 859.233 tufos e aproximadamente 2.724 MiB de RAM. A densidade junto à margem recebeu depois um pequeno ajuste visual; os totais podem variar. Esses dados indicam média próxima dos 78,4 FPS da medição anterior, com picos de carregamento ainda presentes.
