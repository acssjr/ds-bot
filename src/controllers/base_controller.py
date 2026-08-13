from abc import ABC, abstractmethod
from src.actions.action_model import Action

class BaseController(ABC):
    """Interface abstrata para controladores de entrada do dispositivo."""

    @abstractmethod
    def execute(self, action: Action) -> bool:
        """Executa uma ação no dispositivo."""
        pass

    @abstractmethod
    def recover_app_state(self, package_name: str = "com.QuestLab.DraftWar") -> bool:
        """Força o fechamento e reinício do aplicativo em caso de travamento."""
        pass
