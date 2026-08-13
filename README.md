# Draft Showdown Bot

Fundação para automação visual confiável de **uma conta do Draft Showdown em uma única instância do MEmu**, escolhida explicitamente pelo número de série ADB.

## Estado atual: somente observação

Esta versão é estritamente **SOMENTE OBSERVAÇÃO**. A CLI e a GUI usam o mesmo `BotRuntime` para capturar frames e publicar observações. O runtime atual:

- captura automaticamente a tela nativa do Android via ADB, ou reproduz imagens gravadas;
- alterna entre `adb exec-out` e captura shell quando o MEmu devolve frames pretos transitórios, sem encerrar a observação;
- na GUI, grava automaticamente um dataset seletivo em `datasets/sessions/`, priorizando transições, `UNKNOWN`, mudanças visuais e amostras periódicas;
- processa apenas a instância MEmu selecionada explicitamente;
- não cria controladores de entrada e **não envia taps, swipes ou outros comandos ao jogo**;
- encerra de forma cooperativa e registra eventos de ciclo de vida, frame, observação e erro.

Os módulos legados de planejamento e entrada ainda existem no código como referência para etapas futuras, mas não são importados nem acionados pelos pontos de entrada atuais.

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

A GUI descobre os dispositivos fora da thread do Tk, exige a escolha explícita de um serial e executa a mesma fundação `BotRuntime` em uma thread de trabalho. Eventos são consumidos pela thread da interface. A descoberta e a sessão ADB da GUI usam timeout de inatividade de 5 segundos. O painel mostra frames válidos, pretos descartados, estratégia de captura e imagens salvas. Os arquivos JPEG e o `observations.jsonl` ficam numa pasta de sessão em `datasets/sessions/`; frames repetidos são deduplicados para limitar uso de disco. Pausa e automação ativa permanecem desabilitadas.

## Limitações conhecidas

- uma partida ADB real completa é reconhecida nas etapas `HOME`, `COLLECTION_MENU`, `WAIT_MATCHMAKING`, `DRAFT_SCREEN`, `COMBAT`, `ROUND_RESULT` e `VICTORY_SUMMARY`;
- anúncios, recompensas especiais e algumas telas fora do fluxo normal da partida ainda não possuem cobertura calibrada;
- capturas reais podem permanecer em `UNKNOWN`, o que é esperado nesta fundação;
- não há ainda OCR especializado, detector de cartas validado, decisão de draft, execução de ações, verificação de pós-condição ou recuperação automática;
- replay demonstra determinismo e segurança estrutural, mas não substitui a validação controlada de captura ao vivo no MEmu.

## Próximas etapas fechadas

A automação ativa só poderá ser habilitada depois de gates separados e verificáveis:

1. manifesto de percepção com ROIs, escalas, thresholds e corpus de replay;
2. percepção calibrada e observações imutáveis com proveniência de frame;
3. FSM e política de intenção que rejeitem `UNKNOWN` e baixa confiança;
4. action gate e backend de entrada isolado, inicialmente em dry-run;
5. confirmação por frame novo de cada pós-condição;
6. supervisor com timeouts, recuperação limitada e parada segura.

Consulte a [arquitetura aprovada](docs/superpowers/specs/2026-08-13-draft-showdown-bot-architecture-design.md) e o [plano desta fundação](docs/superpowers/plans/2026-08-13-draft-showdown-safe-foundation.md) para os contratos completos.
