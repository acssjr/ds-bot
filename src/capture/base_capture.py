from abc import ABC, abstractmethod
from typing import Optional
import numpy as np

class BaseCapture(ABC):
    """Interface abstrata para captura de tela do emulador/dispositivo."""

    @abstractmethod
    def start(self) -> bool:
        """Inicializa a captura de tela."""
        pass

    @abstractmethod
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Retorna o frame mais recente como uma matriz BGR (NumPy ndarray)."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Encerra os recursos de captura."""
        pass
