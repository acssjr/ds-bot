# Draft Showdown 1.14.1: dados de estratégia extraídos

Data da análise: 2026-08-14. Pacote Android: `com.QuestLab.DraftWar`, versão
`1.14.1` (`versionCode 515`), Unity `6000.3.14f1`, IL2CPP metadata v39.

## O que é dado e o que é julgamento

O arquivo gerado `src/strategy/data/game_data_1_14_1.json` contém somente fatos
extraídos: 25 unidades, vida/dano, quantidade inicial e tardia por carta,
movimento, alcance, timing das animações, parâmetros especiais, matriz de
sinergia, matriz de tendência contra o oponente e tabela de decisão por
quantidade. Os papéis e o pequeno peso da tier list ficam separadamente em
`src/strategy/unit_knowledge.py`.

Os cinco CSVs decisivos também estavam na configuração remota corrente do
emulador. O conteúdo remoto, decodificado com o mecanismo AES usado pelo jogo,
foi comparado byte a byte com os arquivos do APK e era idêntico em 2026-08-14:

- `UnitUpgradeSetup`
- `DraftPool`
- `AiUnitCountSetup`
- `DraftSynergySetup`
- `AiTendencySetup`

Isso elimina, para esta sessão, a dúvida de que as tabelas empacotadas estavam
desatualizadas em relação ao balanceamento remoto.

## Atributos das unidades já observadas

Vida e dano vêm da configuração de balanceamento atual. Movimento, alcance e
timing vêm dos prefabs e animações.

| Unidade | Vida | Dano | Entrada cedo/tarde | Move speed | Alcance | Ciclo de ataque* |
|---|---:|---:|---:|---:|---:|---:|
| Knight | 95 | 10 | 3 / 5 | 3 | 2 | 0,583 s |
| Cupid | 35 | 12 | 3 / 5 | 2 | 17 | 1,000 s |
| Goose | 50 | 10 | 5 / 8 | 10 | 2 | 0,317 s |
| TNT | 70 | 75 | 2 / 3 | 6 | 2 | 1,000 s |
| Snail | 130 | 100 | 1 / 2 | 2 | 30 | 5,250 s |
| Assassin | 28 | 10 | 3 / 5 | 5 | 2 | 0,583 s |
| Splime | 65 | 15 | 4 / 7 | 3 | 2 | 0,467 s |
| Kingclops | 100 | 15 | 1 / 2 | 2,5 | 2 | 0,583 s |
| Engineer | 150 | 15 | 1 / 2 | 2 | 2 | 0,583 s |

\* O ciclo da animação não deve ser chamado diretamente de “ataques por
segundo”. Cada clipe possui eventos diferentes (`OnAttack`, `OnShoot`,
`OnSuicide`, `SpawnUnit`) e algumas unidades acertam mais de uma vez. O JSON
preserva todos os eventos para um cálculo posterior de DPS que respeite cada
comportamento.

Todos os níveis usam multiplicador `1,1` por nível para vida e dano, até o
nível 15. O primeiro upgrade custa 100 e o custo cresce por `1,5` a cada nível.

## Engineer, Assassin, TNT e Goose

- Engineer é deliberadamente lento (`move speed 2`), mas coloca a primeira
  torre em `1,5 s` e repete a cada `5 s`, com jitter de `0,2`. A tabela da IA
  dá **+20** para Engineer contra Assassin.
- Assassin tem `move speed 5`, inicia o teleporte entre `0,2–0,8 s` e espera
  `1 s` no teleporte. A torre criada ao lado do Engineer explica por que o
  Assassin que chega atrás encontra um alvo/defensor imediatamente.
- A tabela da IA dá **+12** para TNT contra Goose. Ao mesmo tempo, a matriz de
  composição própria marca TNT + Goose como **-1**: TNT responde a uma massa
  inimiga de Geese, mas não é automaticamente uma boa parceria com Geese do
  próprio time.

## Quando usar 2x

`AiUnitCountSetup` agrupa unidades pelo tamanho de sua carta inicial (`x1` a
`x5`). Para um grupo `xN`, a regra empacotada é:

| Quantidade atual | Adicionar | 2x | Upgrade |
|---:|---:|---:|---:|
| 0 | 50 | 0 | 0 |
| N | 100 | 0 | 0 |
| 2N | -50 | 750 | -100 |
| 3N | 200 | 500 | varia por grupo |
| 4N | -100 | 1000 | positivo |

Portanto, para Goose (`N=5`):

- 10 Geese: `2x = 750`, adicionar = `-50`, upgrade = `-100`;
- 15 Geese: `2x = 500`, adicionar = `200`, upgrade = `0`;
- 20 Geese: `2x = 1000`, adicionar = `-100`, upgrade = `200`.

A política agora consulta essa tabela em cada candidato. Ela acompanha a
quantidade apenas depois que o toque foi confirmado visualmente, então não
“imagina” uma carta que falhou. O histórico usa aliases, portanto `Goose` e
`Ganso` são a mesma unidade. Valores acima do domínio explícito 0–24 são
limitados ao último índice; não foi inventada uma extrapolação que o APK não
fornece.

## Comparação com a tier list de 2026-08-14

A imagem fornecida põe Engineer, Goose e TNT em A, Assassin em C e Kingclops em
D. Isso é coerente com os dados internos nos pontos principais:

- Engineer tem utilidade que vida/dano/velocidade isolados não capturam;
- Goose escala por quantidade e tem velocidade 10, mas sofre contra área;
- TNT recebe tendência positiva justamente contra Goose;
- Assassin tem os menores atributos base entre as unidades observadas e pode
  ser anulado por Engineer;
- não existe unidade universal: as matrizes contêm respostas positivas e
  negativas, coerente com a ausência de tier S na imagem.

A comunidade atual diverge nos limites: há jogadores defendendo Engineer um
nível acima e outros dizendo que Goose piora no late game. Por isso a tier list
entra apenas como desempate pequeno. Contagem, composição e counters do APK têm
mais peso.

## Reprodutibilidade e limites

Rode o extrator sobre um export do AssetRipper:

```powershell
python scripts/extract_apk_strategy_data.py `
  C:\caminho\ExportedProject\Assets `
  src\strategy\data\game_data_1_14_1.json `
  --apk-version 1.14.1
```

O repositório não inclui o APK, bibliotecas nativas ou prefabs proprietários;
somente os fatos numéricos gerados. Uma atualização do jogo exige nova extração
e nova comparação da configuração remota. A política sabe escolher usando a
contagem que ela própria confirmou; reconhecimento visual independente de cada
miniatura já presente no campo é uma camada futura de auditoria, não um dado
que o APK resolve sozinho.
