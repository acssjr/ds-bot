# Estratégia de duplicação — Draft Showdown 1.14.1

Data da análise: 2026-08-14. Esta nota separa valores oficiais do APK de
estimativas calculadas pelo bot.

## Regra oficial por quantidade

`AiUnitCountSetup.txt` divide as unidades pelo tamanho `N` de sua carta inicial.
Os valores abaixo são pesos da IA de draft do jogo, não bônus de combate:

| Contagem atual | Adicionar N | Duplicar | Interpretação |
|---:|---:|---:|---|
| 0 | 50 | 0 | formar uma nova linha |
| N | 100 | 0 | completar a primeira entrada |
| 2N | -50 | 750 | primeira janela forte de x2 |
| 3N | 200 | 500 | adicionar ainda é útil, mas x2 continua forte |
| 4N | -100 | 1000 | janela máxima de x2 |

Fora desses pontos o peso explícito de multiplicação é zero. O bot ainda pode
preferir x2 pelo número real de corpos adicionados, nível da conta, counters e
sinergia, mas não inventa uma extrapolação da tabela.

## Janelas por unidade do deck

| Unidade | N inicial | Boa janela x2 | Janela x2 máxima |
|---|---:|---:|---:|
| Cavaleiro | 3 | 6 ou 9 | 12 |
| Cupido | 3 | 6 ou 9 | 12 |
| Ganso | 5 | 10 ou 15 | 20 |
| Engenheiro | 1 | 2 ou 3 | 4 |
| Caracol | 1 | 2 ou 3 | 4 |

Portanto, 15 Gansos é realmente uma boa janela: a tabela dá 500 para x2 e 200
para adicionar. Com 20 Gansos, x2 atinge o peso máximo de 1000.

## O que o bot calcula além da tabela

Para cada carta x2, a política calcula:

1. quantidade confirmada da unidade no campo;
2. quantidade adicional criada pelo multiplicador;
3. multiplicador de atributos do nível real lido por ADB;
4. vida total adicionada;
5. DPS direto aproximado pelos eventos `OnAttack`/`OnShoot` da animação;
6. tendência contra as unidades inimigas reconhecidas;
7. sinergia com a composição própria;
8. habilidades não incluídas no DPS, como torretas e outras invocações.

O DPS é uma aproximação comparativa. Ele não inclui deslocamento, aquisição de
alvo, dano em área, sobrevida real, torretas, projéteis desperdiçados ou
habilidades especiais.

## Última sessão: escolha que viria após a interrupção

Estado reconstruído: 10 Gansos, 3 Cupidos e 4 Engenheiros. O próximo conjunto
era `Engenheiros x2`, `Gansos x2`, `Ganso zumbi!`, contra Cavaleiro e Splime.

| Escolha | Corpos adicionados | Vida aproximada | DPS direto aproximado | Peso APK por contagem |
|---|---:|---:|---:|---:|
| Engenheiros x2 | 4 | 878 | 301 + torretas | 1000 |
| Gansos x2 | 10 | 666 | 420 | 750 |
| Ganso zumbi | upgrade dos 10 Gansos para tier avançado | +40% de exposição de vida via ressurreição | +40% de exposição de dano após a primeira morte | 500 |

O bot escolheria `Engenheiros x2`. O texto `Ganso zumbi!` foi inicialmente
classificado como transformação genérica; a inspeção do `CardSetup` mostrou que
ele é precisamente o upgrade Goose (UnitType 4) -> Goose2 (UnitType 11).
Gansos ofereceriam mais dano direto imediato,
mas Engenheiros adicionariam mais vida, duplicariam a produção de torretas,
estavam exatamente na janela máxima `4N` e não recebiam a penalidade que Ganso
tem diante de Cavaleiro na matriz da IA.

## Regras táticas resultantes

- Duplicar Engenheiro ganha prioridade em 4 unidades, principalmente contra
  pressão de Assassino, Ganso ou composição que não elimine invocadores cedo.
- Duplicar Ganso é especialmente forte em 10 e 20; em 15 ainda é muito bom.
  Perde valor contra Engenheiro, Caracol e TNT/área conforme a matriz inimiga.
- Duplicar Cupido é melhor em 6/9/12 quando existe linha de frente. Evitar
  concentração excessiva contra Assassino, Ganso ou Caracol.
- Duplicar Cavaleiro em 6/9/12 reforça a linha de frente e protege ranged, mas
  tem forte penalidade interna diante de Caracol.
- Duplicar Caracol em 2/3/4 aumenta muito o dano por salva e alcance, mas deve
  ser evitado quando Assassino consegue alcançar a retaguarda.
- A escolha final nunca usa somente a tabela: x2 pode ser recusado quando o
  inimigo possui um counter forte ou quando falta um papel essencial na equipe.
