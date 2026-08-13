# Draft Showdown Automation Bot

Bot autônomo baseado em Visão Computacional, Máquina de Estados Finitos (FSM) e Arquitetura de Malha Fechada para automação de gameplay do jogo **Draft Showdown** (Android / Emulador).

## Estrutura do Projetos

```text
draft_showdown_bot/
├── assets/
│   ├── templates/
│   │   ├── home/
│   │   ├── draft/
│   │   └── result/
│   └── models/
├── src/
│   ├── capture/          # Módulos de captura de tela (ADB / Scrcpy)
│   ├── vision/           # Classificação de telas, Template Matching, OCR e YOLO
│   ├── state/            # GameState (Pydantic v2) e StateManager (FSM)
│   ├── strategy/         # Matriz de utilidade e avaliação estratégica
│   ├── actions/          # Modelagem e planejamento de ações
│   ├── controllers/      # Drivers de controle de toque (ADB / Minitouch)
│   ├── utils/            # Normalização de coordenadas, Watchdog e Logger
│   └── main.py           # Loop principal da aplicação
├── tests/                # Suíte de testes unitários e simulador offline
├── pyproject.toml
└── requirements.txt
```

## Como Executar

1. Certifique-se de que o emulador (BlueStacks, MEmu, LDPlayer, etc.) está rodando com ADB ativado.
2. Ative o ambiente virtual e execute o bot:
```powershell
.\.venv\Scripts\python.exe src/main.py
```
