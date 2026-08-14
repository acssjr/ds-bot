# Draft Showdown Bot

Fundação para automação visual confiável de **uma conta do Draft Showdown em uma única instância do MEmu**, escolhida explicitamente pelo número de série ADB.

## Estado atual: observação segura e uma batalha supervisionada

A CLI padrão continua observe-only. A GUI separa explicitamente **Iniciar observação** de **Executar 1 batalha**; o segundo exige confirmação humana e envia taps reais. Tanto a observação quanto o executor conseguem abrir `com.QuestLab.DraftWar` a partir da tela inicial do MEmu e aguardam o jogo chegar ao primeiro plano. O executor usa OCR e uma política determinística explicável para comparar as cartas visualmente válidas. O runtime padrão:

- captura automaticamente a tela nativa do Android via ADB, ou reproduz imagens gravadas;
- alterna entre `adb exec-out`, captura shell e `adbutils` quando o MEmu devolve frames pretos transitórios; após falhas consecutivas, renova o handle ADB sem encerrar a observação;
- na GUI, grava automaticamente um dataset seletivo em `datasets/sessions/`, priorizando transições, `UNKNOWN`, mudanças visuais e amostras periódicas;
- processa apenas a instância MEmu selecionada explicitamente;
- **Iniciar observação não envia taps ou swipes de gameplay**; somente a CLI confirmada ou o botão confirmado **Executar 1 batalha** habilitam entrada;
- na GUI, depois que um anúncio recompensado foi reconhecido, verifica o pacote Android em primeiro plano: se Play Store, navegador ou outro app externo foi aberto, tenta `Voltar`, depois reabrir e, como último fallback, reiniciar apenas o Draft Showdown;
- encerra de forma cooperativa e registra eventos de ciclo de vida, frame, observação e erro.

Os módulos legados de planejamento e entrada ainda existem no código como referência. O executor usa uma FSM nova e isolada, sem reaproveitar o controlador legado.

## Requisitos

- Windows com MEmu e ADB habilitado, somente para observação ao vivo;
- Python 3.12 (a faixa suportada é `>=3.12,<3.13`);
- [uv](https://docs.astral.sh/uv/) para criar o ambiente reproduzível;
- clone do repositório recomendado para desenvolvimento e para usar o corpus manual de replay incluído em `screenshots/`.

## Preparação

No diretório raiz do clone:

```powershell
uv python install 3.12
$env:UV_PROJECT_ENVIRONMENT = ".venv312"
uv sync --locked --extra dev
```

`uv sync --locked` consome o `uv.lock` sem atualizá-lo e instala o projeto de forma editável em `.venv312`, preservando uma eventual `.venv` antiga. Esse continua sendo o fluxo recomendado de desenvolvimento. O wheel do projeto contém os templates legados necessários para a percepção padrão, mas não inclui as capturas manuais de `screenshots/`.

## Testes

```powershell
.\.venv312\Scripts\python.exe -m pytest -q
.\.venv312\Scripts\python.exe -m compileall -q src tests
```

## CLI: replay determinístico

```powershell
.\.venv312\Scripts\python.exe -m src.main --replay screenshots --frames 3 --interval 0
```

Em replay, `--frames` deve ser um inteiro positivo e não pode superar a quantidade de PNG/JPG disponível. Se omitido, todas as imagens do diretório são processadas. `--interval` é o intervalo não negativo, em segundos, entre frames; o padrão é `0.25`.

As capturas feitas manualmente em `screenshots/` são referências das telas e de suas variações, úteis para pesquisa, replay e construção de testes. Elas não são tratadas como templates perfeitos nem distribuídas no wheel. O comando acima pressupõe o clone; numa instalação por wheel, informe em `--replay` um diretório de imagens fornecido pelo usuário, preferencialmente com caminho absoluto. Na observação ao vivo, a produção captura cada frame automaticamente do dispositivo por ADB.

## CLI: observação ao vivo no MEmu

Se o executável `adb` estiver disponível no `PATH`, confirme o número de série exposto pelo MEmu:

```powershell
adb devices
```

Esse comando pertence ao Android SDK Platform Tools ou à distribuição ADB do MEmu; ele não é instalado por este projeto. Se não houver um `adb` de linha de comando no `PATH`, abra a GUI abaixo e use **Atualizar lista**: ela consulta o servidor ADB ativo diretamente com `adbutils` e mostra os seriais disponíveis. O ADB do MEmu ainda precisa estar habilitado e seu servidor acessível.

Depois informe exatamente esse serial, por exemplo:

```powershell
.\.venv312\Scripts\python.exe -m src.main --device 127.0.0.1:21503 --frames 10 --interval 0.25
```

Não há seleção implícita do primeiro emulador. Em modo ao vivo, `--frames` limita a quantidade de capturas; sem esse argumento, a observação continua até `Ctrl+C`. A CLI configura timeout de inatividade do socket ADB em 10 segundos. Esse timeout limita espera sem tráfego, não constitui prazo absoluto de parede para toda operação nativa do ADB.

## GUI

```powershell
.\.venv312\Scripts\python.exe -m src.gui.app
```

A GUI descobre os dispositivos fora da thread do Tk e executa observação ou uma batalha, nunca ambos ao mesmo tempo. Quando há somente um dispositivo, ele é selecionado automaticamente e exibido com nome amigável (por exemplo, `MEmu · 127.0.0.1:21503`); com vários dispositivos, a seleção explícita continua obrigatória. O painel mostra inicialização do aplicativo, fase da FSM, ação pendente/confirmada, opções reconhecidas no draft, pontuação e justificativa da escolha, além de duração, `UNKNOWN`, saúde da captura, dataset e recursos. O retrato validado sobrevive a reinícios em `datasets/account_state.json`.

## Executor experimental de uma batalha

Este comando envia taps reais. O MEmu pode estar na tela inicial; o executor abre o jogo pelo pacote Android e aguarda a HOME antes de iniciar:

```powershell
.\.venv312\Scripts\python.exe -m src.automation.main --device 127.0.0.1:21503 --confirm-live-input
```

Opcionalmente, `--max-minutes 20` limita o tempo total. Sem esse argumento, o matchmaking não recebe timeout artificial; `Ctrl+C` continua disponível. Não existe seed porque não há escolha aleatória.

O executor:

- toca Batalha uma vez e aguarda matchmaking;
- escolhe somente slots visualmente preenchidos em drafts normais e bônus de recuperação;
- lê nome/efeito com RapidOCR e pontua quantidade, multiplicador, upgrade válido, papéis ausentes, continuidade e confiança;
- reconhece unidades já reveladas no exército inimigo e combina esse sinal com a matriz de sinergias/counters da versão 1.14.1 instalada;
- registra candidatos, notas e justificativa em `actions.jsonl` e mostra a mesma análise na GUI;
- reivindica o pacote de vitória e `x2 BITS` quando o anúncio recompensado está disponível;
- aguarda contador/barra e só fecha o anúncio após `safe_to_close=true`, inclusive em sequências de dois anúncios;
- aplica no máximo um impulso de maestria por slot visualmente habilitado e para quando a moeda M conhecida chega a zero;
- trata vitória e derrota separadamente, pulando a distribuição da derrota antes de processar os impulsos;
- pula Bit Pack, confirma nova unidade e recupera Play Store/navegador para o jogo;
- não toca durante combate ou resultado de round;
- separa splash, distribuição de maestria, pacote pronto e animação pós-pacote;
- fecha a oferta paga pós-batalha exclusivamente pelo X detectado;
- retorna da Liga para HOME e encerra;
- para sem repetir o tap se uma pós-condição não aparecer;
- grava frames em `datasets/sessions/<sessão>/observations.jsonl` e ações em `actions.jsonl`.

Anúncios recompensados e impulsos que consomem moeda M estão habilitados na batalha confirmada. Compras em reais, gemas ou moedas, ofertas pagas e upgrades da coleção permanecem bloqueados. **Iniciar observação** não envia taps de gameplay.

## Limitações conhecidas

- uma partida ADB real completa é reconhecida nas etapas `HOME`, `COLLECTION_MENU`, `WAIT_MATCHMAKING`, `DRAFT_SCREEN`, `COMBAT`, `ROUND_RESULT` e `VICTORY_SUMMARY`;
- uma sessão real de navegação reconhece `SHOP_MENU`, `SHOP_DAILY_OFFERS`, `WATCHING_AD`, `AD_REWARD_GRANTED`, `LEAGUE_MENU`, `RANKED_LOCKED` e `PROFILE_MENU`;
- anúncios com contador textual e anúncios com barra amarela são tratados como pendentes; somente a confirmação visual de recompensa ou o botão de encerramento liberado produz `safe_to_close=true`;
- anúncios compostos (`Ad 1 of 2`, `Ad 2 of 2`) permanecem em espera; a recuperação não interrompe o anúncio enquanto o jogo continua sendo o aplicativo em primeiro plano;
- a presença de ofertas/atualização por anúncio e do contador de renovação diária já é observável; recursos da conta, troféus, nível, posição/pontos da Liga e unidades visíveis da Coleção possuem OCR especializado, enquanto temporizadores de ofertas/anúncios continuam `OCR_PENDING`;
- recompensas especiais e algumas telas fora dos fluxos gravados ainda não possuem cobertura calibrada;
- capturas reais podem permanecer em `UNKNOWN`, o que é esperado nesta fundação;
- o executor reconhece os efeitos já observados (`+N`, `xN`, `UP` e transformação zumbi) e usa uma utilidade determinística com papéis, sinergia própria, counters e pressão visual inimiga; os pesos continuam auditáveis e devem ser calibrados com resultados reais, não tratados como uma tier list infalível;
- replay demonstra determinismo e segurança estrutural, mas não substitui a validação controlada de captura ao vivo no MEmu.

## Próximas etapas fechadas

A automação ativa só poderá ser habilitada depois de gates separados e verificáveis:

1. manifesto de percepção com ROIs, escalas, thresholds e corpus de replay;
2. percepção calibrada e observações imutáveis com proveniência de frame;
3. FSM e política de intenção que rejeitem `UNKNOWN` e baixa confiança;
4. action gate e backend de entrada isolado, validados em dry-run e disponíveis no entrypoint experimental;
5. confirmação por frame novo de cada pós-condição, implementada sem repetição cega;
6. calibrar custos/benefícios dos impulsos e recompensas com resultados reais, mantendo orçamento explícito.

Consulte a [arquitetura aprovada](docs/superpowers/specs/2026-08-13-draft-showdown-bot-architecture-design.md) e o [plano desta fundação](docs/superpowers/plans/2026-08-13-draft-showdown-safe-foundation.md) para os contratos completos.
