# Interface e densidade — v0.4

A densidade padrão passa de 12.000 para 40.000 candidatos a tufos por chunk. Isso visa aproximadamente 900 mil tufos nos 25 chunks carregados; o total efetivo depende dos lagos e dos chunks que já terminaram de carregar. LODs, células de culling, workers e limites do cache são mantidos.

## Interface

O HUD usa `pixel2d`, com fontes dimensionadas em pixels em vez de proporções da altura da janela. Um evento de redimensionamento recalcula fontes, margens, quebra de linhas, posição da mira, avisos e menu de pausa. A interface tem seu próprio receptor de eventos, preservando o tratamento de janela do Panda3D.

Fundos escuros melhoram o contraste sobre água, grama e céu. Janelas pequenas mostram um resumo das métricas e dos controles, preservando a leitura. Em janelas maiores, aparece o painel completo. F1 continua ocultando o painel.

```powershell
.\run.cmd
.\run.cmd --resolution 800x450 --ui-scale 1.25
.\run.cmd --grass-density 50000
.\run.cmd --grass-density 12000
```

`--ui-scale` aceita 0.75 a 2. O layout limita o tamanho em janelas muito pequenas para evitar sobreposição. `--grass-density` é uma contagem de candidatos por chunk, não o total da cena. O valor padrão vem de `game/config.py`.

## Validação

Benchmark final de streaming, 20 segundos, seed 938472, 1280 × 720, sombras LOW, densidade 40.000:

| Métrica | Resultado |
|---|---:|
| FPS médio | 86,0 |
| Frame p50 / p95 / p99 | 9,54 / 22,76 / 40,00 ms |
| Pior frame | 68,28 ms |
| Frames acima de 33,3 ms | 25 de 1.723 |
| Tufos carregados ao final | 766.206 |
| Chunks prontos / trabalhos em andamento | 20 / 4 |
| RAM do processo ao final | 2.635 MiB, aproximadamente 2,57 GiB |

A rota atravessa bordas de chunks e inclui carregamentos após o aquecimento. Ao final ainda havia trabalhos em andamento, por isso o total não representa 25 chunks completos. O aumento de densidade mantém boa média de FPS nesta máquina, mas aumenta memória, custo de carregamento e picos de tempo de frame. Estes resultados offscreen não garantem o mesmo desempenho em uma janela interativa ou em outro hardware. O histórico está em `benchmarks/history-v0.4.csv`.
