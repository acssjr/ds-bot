# Draft Showdown Bot

Fundação para automação visual confiável de **uma conta do Draft Showdown em uma única instância do MEmu**, escolhida explicitamente pelo número de série ADB.

## Estado atual: observação com recuperação externa limitada

Esta versão continua sem automação de gameplay. A CLI e a GUI usam o mesmo `BotRuntime` para capturar frames e publicar observações; na GUI, existe apenas uma recuperação limitada para anúncios que abrem outro aplicativo. O runtime atual:

- captura automaticamente a tela nativa do Android via ADB, ou reproduz imagens gravadas;
- alterna entre `adb exec-out`, captura shell e `adbutils` quando o MEmu devolve frames pretos transitórios; após falhas consecutivas, renova o handle ADB sem encerrar a observação;
- na GUI, grava automaticamente um dataset seletivo em `datasets/sessions/`, priorizando transições, `UNKNOWN`, mudanças visuais e amostras periódicas;
- processa apenas a instância MEmu selecionada explicitamente;
- **não envia taps ou swipes de gameplay**;
- na GUI, depois que um anúncio recompensado foi reconhecido, verifica o pacote Android em primeiro plano: se Play Store, navegador ou outro app externo foi aberto, tenta `Voltar`, depois reabrir e, como último fallback, reiniciar apenas o Draft Showdown;
- encerra de forma cooperativa e registra eventos de ciclo de vida, frame, observação e erro.

Os módulos legados de planejamento e entrada ainda existem no código como referência para etapas futuras, mas não são importados nem acionados pelos pontos de entrada atuais. A recuperação externa não usa coordenadas nem reaproveita o planejador legado.

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

A GUI descobre os dispositivos fora da thread do Tk e executa a mesma fundação `BotRuntime` em uma thread de trabalho. Quando há somente um dispositivo, ele é selecionado automaticamente e exibido com nome amigável (por exemplo, `MEmu · 127.0.0.1:21503`); com vários dispositivos, a seleção explícita continua obrigatória. Eventos são consumidos pela thread da interface. A descoberta e a sessão ADB da GUI usam timeout de inatividade de 5 segundos. O painel mostra duração e estabilidade da sessão, observações, transições, taxa de `UNKNOWN`, frames válidos, pretos descartados, recuperações, estratégia de captura, recuperação de aplicativo externo, imagens salvas e o último retrato confiável dos recursos da conta. Energia, gemas, moedas, moeda de maestria, troféus e nível são lidos em regiões específicas; Coleção e Liga recebem uma leitura detalhada ao entrar na respectiva tela. O retrato validado sobrevive a reinícios em `datasets/account_state.json`. Os arquivos JPEG e o `observations.jsonl` ficam numa pasta de sessão em `datasets/sessions/`; frames repetidos são deduplicados para limitar uso de disco. Pausa e automação de gameplay permanecem desabilitadas.

## Limitações conhecidas

- uma partida ADB real completa é reconhecida nas etapas `HOME`, `COLLECTION_MENU`, `WAIT_MATCHMAKING`, `DRAFT_SCREEN`, `COMBAT`, `ROUND_RESULT` e `VICTORY_SUMMARY`;
- uma sessão real de navegação reconhece `SHOP_MENU`, `SHOP_DAILY_OFFERS`, `WATCHING_AD`, `AD_REWARD_GRANTED`, `LEAGUE_MENU`, `RANKED_LOCKED` e `PROFILE_MENU`;
- anúncios com contador textual e anúncios com barra amarela são tratados como pendentes; somente a confirmação visual de recompensa ou o botão de encerramento liberado produz `safe_to_close=true`;
- anúncios compostos (`Ad 1 of 2`, `Ad 2 of 2`) permanecem em espera; a recuperação não interrompe o anúncio enquanto o jogo continua sendo o aplicativo em primeiro plano;
- a presença de ofertas/atualização por anúncio e do contador de renovação diária já é observável; recursos da conta, troféus, nível, posição/pontos da Liga e unidades visíveis da Coleção possuem OCR especializado, enquanto temporizadores de ofertas/anúncios continuam `OCR_PENDING`;
- recompensas especiais e algumas telas fora dos fluxos gravados ainda não possuem cobertura calibrada;
- capturas reais podem permanecer em `UNKNOWN`, o que é esperado nesta fundação;
- ainda não há detector de cartas validado, decisão de draft, execução de ações de gameplay ou verificação de pós-condição dessas ações; a única recuperação automática atual é o retorno seguro de aplicativos externos abertos durante anúncios;
- replay demonstra determinismo e segurança estrutural, mas não substitui a validação controlada de captura ao vivo no MEmu.

## Próximas etapas fechadas

A automação ativa só poderá ser habilitada depois de gates separados e verificáveis:

1. manifesto de percepção com ROIs, escalas, thresholds e corpus de replay;
2. percepção calibrada e observações imutáveis com proveniência de frame;
3. FSM e política de intenção que rejeitem `UNKNOWN` e baixa confiança;
4. action gate e backend de entrada isolado, inicialmente em dry-run;
5. confirmação por frame novo de cada pós-condição;
6. ampliar o supervisor já limitado a anúncios com pós-condições específicas para futuras ações de gameplay.

Consulte a [arquitetura aprovada](docs/superpowers/specs/2026-08-13-draft-showdown-bot-architecture-design.md) e o [plano desta fundação](docs/superpowers/plans/2026-08-13-draft-showdown-safe-foundation.md) para os contratos completos.
