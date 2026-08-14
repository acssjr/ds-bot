# Transformações e duplicação — APK 1.14.1

Este estudo separa quatro fontes: `CardSetup` define o que a carta converte e
seus limites; `LocData` registra a explicação mostrada ao jogador; o prefab de
cada tier contém os multiplicadores e comportamentos executados; as animações
determinam quantos eventos de dano existem e quanto dura cada ciclo. Os valores
crus `health` e `damage` do prefab não são usados como base porque o próprio
`UnitComponent` avisa que eles são substituídos pelos dados online.

## Modelo usado pelo planejador

O bot rastreia, por família, quantidade e tier (1 base, 2 avançado, 3 elite).
Um upgrade converte **todos** os corpos do tier atual no tier seguinte. Um x2
tem cartões distintos para cada `UnitType`, logo dobra diretamente os corpos do
tier atual. O valor corporal relativo combina em partes iguais:

1. exposição total de vida, incluindo uma segunda vida quando existe;
2. taxa de dano, corrigida por multiplicador, eventos e duração da animação;
3. um ajuste menor e explícito por velocidade e frequência de invocação.

Counters e sinergias continuam vindo das matrizes oficiais e são somados fora
desse fator. Assim, transformação não apaga a análise dos picks inimigos.

| Família | Base | Avançado | Elite |
|---|---:|---:|---:|
| Cavaleiro | 1,00x | 1,26x | 1,76x |
| Cupido | 1,00x | 1,25x | 1,75x |
| Ganso | 1,00x | 1,40x | 1,70x |
| Engenheiro | 1,00x | 1,24x | 1,49x |

Esses fatores são comparadores, não uma alegação de que vida e DPS sejam
intercambiáveis em toda situação. A explicação da decisão conserva os dados
brutos para auditoria.

## Cavaleiro

- UnitTypes: `0 -> 5 -> 24`; upgrade disponível com 6 ou mais corpos.
- Avançado: vida 1,5x e dano por impacto 1,3x. A animação passa de 0,583 s para
  0,750 s, com dois impactos em ambos os casos; portanto o throughput direto
  fica perto de 1,01x, enquanto a grande vantagem é a sobrevivência.
- Elite: vida 2,0x. Há conflito real de fonte: `LocData` anuncia dano 1,6x, mas
  `Unit Knight3.prefab` contém `damageMultiplierToBaseClass=3` e ciclo de 1,15 s.
  O planejador usa o prefab ativo com a animação, resultando em aproximadamente
  1,52x de taxa direta. O conflito permanece registrado no dataset.
- Consequência: avançar Cavaleiros vale principalmente para segurar a linha;
  x2 elite ganha muito valor quando a retaguarda precisa de tempo para atacar.

## Cupido

- UnitTypes: `1 -> 7 -> 25`; upgrade e x2 exigem ao menos 6 corpos.
- Avançado: a interface declara velocidade de ataque 1,5x. A animação muda de
  um disparo em 1,0 s para dois disparos em aproximadamente 1,183 s.
- Elite: mantém o padrão de dois disparos/velocidade anunciada e sobe a vida
  para 2,0x.
- Consequência: o primeiro upgrade é ofensivo; o segundo adiciona sobretudo
  resistência. Duplicar Cupido avançado/elite é valioso quando existe frontline
  e perde valor relativo se Assassino ou pressão de retaguarda estiverem ativos.

## Ganso zumbi

- UnitTypes: `4 -> 11 -> 26`; `Ganso zumbi!` é exatamente o primeiro upgrade.
  Não é uma transformação paralela. Os cartões exigem 10 ou mais Gansos.
- Avançado: ao morrer, agenda após 0,5 s um `Goose Headless` (UnitType 12), com
  multiplicadores 0,4 de vida e dano. Isso equivale a mais 40% de exposição,
  desde que a segunda forma tenha tempo de agir.
- Elite: primeira vida 1,3x, dano 1,2x e velocidade 15 contra 10 da base;
  mantém a segunda forma 0,4x. O ganho é ofensivo, defensivo e de contato.
- Consequência: 10 Gansos base x2 criam 10 corpos base adicionais; transformar
  os 10 cria uma segunda vida em todos eles. Depois de transformados, x2 cria
  mais 10 Gansos zumbis, cada um também com ressurreição — portanto o x2 passa
  de 10,0 para cerca de 14,0 corpos-base equivalentes de vida.

## Engenheiro

- UnitTypes: `89 -> 90 -> 91`; basta ter 2 Engenheiros. A torreta é UnitType 92.
- Base/avançado/elite: intervalo de torreta `5,0 -> 4,5 -> 4,0 s` e
  multiplicadores de vida/dano `1,0 -> 1,2 -> 1,4`.
- A torreta tem vida 0,2x e dano 0,5x em relação à classe-base do Engenheiro,
  alcance 8 e duração de aproximadamente 5,0–5,5 s. Ela não é um corpo eterno.
- Reduzir o intervalo de 5 para 4,5 s aumenta a taxa real de produção em 11,1%;
  de 4,5 para 4,0 s acrescenta 12,5%; elite produz 25% mais que a base.
- Consequência: x2 de Engenheiro transformado duplica simultaneamente corpos
  mais resistentes e linhas de produção mais rápidas. Isso explica por que 4
  Engenheiros avançados/elite podem superar uma opção com mais corpos simples.

## Regras de decisão resultantes

- O ganho de upgrade é `quantidade × (fator seguinte - fator atual)`, escalado
  pelo valor base real da unidade e combinado com a tabela de contagem do APK.
- O ganho de x2 usa o fator do **tier rastreado**, não o da unidade base.
- Nunca se escolhe upgrade acima do tier 3; isso é marcado como estado
  inconsistente para evitar que erro de OCR receba prioridade.
- A janela do cartão também é validada conceitualmente: Cavaleiro/Cupido 6–12,
  Ganso 10–20, Engenheiro 2–4 para x2. Os upgrades aceitam até 100.
- Ressurreição é descontada naturalmente em cenários onde o round termina antes
  da segunda forma atuar; esta versão usa o valor potencial e deixa a pressão
  visual/counters fazerem o ajuste tático.
