import time
import adbutils
from loguru import logger
from typing import Optional

from src.controllers.base_controller import BaseController
from src.actions.action_model import Action, ActionType
from src.utils.coordinates import CoordinateConverter

class ADBController(BaseController):
    """Controlador de toque e gestos baseado em ADB (adbutils)."""

    def __init__(self, device_serial: Optional[str] = None):
        self.device_serial = device_serial
        self.device = None
        self.screen_width = 1280
        self.screen_height = 720
        self._connect()

    def _connect(self) -> bool:
        """Conecta ao dispositivo Android via ADB."""
        try:
            devices = adbutils.adb.device_list()
            if not devices:
                logger.warning("ADBController: Nenhum dispositivo Android encontrado via ADB.")
                return False
            
            if self.device_serial:
                self.device = adbutils.adb.device(serial=self.device_serial)
            else:
                self.device = devices[0]
                self.device_serial = self.device.serial
            
            logger.info(f"ADBController: Conectado com sucesso ao dispositivo '{self.device_serial}'")
            return True
        except Exception as e:
            logger.error(f"ADBController: Erro ao conectar ao ADB: {e}")
            return False

    def update_screen_size(self, width: int, height: int) -> None:
        """Atualiza a resolução conhecida da tela."""
        self.screen_width = width
        self.screen_height = height

    def execute(self, action: Action) -> bool:
        """Executa a ação convertendo coordenadas normalizadas para pixels."""
        if not self.device:
            if not self._connect():
                return False

        px, py = CoordinateConverter.denormalize(
            action.normalized_start[0],
            action.normalized_start[1],
            self.screen_width,
            self.screen_height
        )

        try:
            if action.action_type == ActionType.TAP:
                logger.debug(f"ADB Tap: ({px}, {py}) [{action.metadata}]")
                self.device.click(px, py)

            elif action.action_type in (ActionType.SWIPE, ActionType.DRAG_AND_DROP):
                if not action.normalized_end:
                    logger.warning("SWIPE/DRAG exige 'normalized_end'")
                    return False
                
                ex, ey = CoordinateConverter.denormalize(
                    action.normalized_end[0],
                    action.normalized_end[1],
                    self.screen_width,
                    self.screen_height
                )
                duration_sec = action.duration_ms / 1000.0
                logger.debug(f"ADB Drag: ({px},{py}) -> ({ex},{ey}) {duration_sec}s [{action.metadata}]")
                self.device.swipe(px, py, ex, ey, duration_sec)

            elif action.action_type == ActionType.WAIT:
                time.sleep(action.duration_ms / 1000.0)

            return True

        except Exception as e:
            logger.error(f"ADBController: Falha ao executar ação {action.action_type}: {e}")
            return False

    def recover_app_state(self, package_name: str = "com.QuestLab.DraftWar") -> bool:
        """Força o encerramento do app e o reabre via ADB."""
        if not self.device:
            return False
        try:
            logger.warning(f"ADBController: Forçando parada do app '{package_name}'...")
            self.device.app_stop(package_name)
            time.sleep(2.0)
            logger.info(f"ADBController: Reiniciando aplicativo '{package_name}'...")
            self.device.app_start(package_name)
            time.sleep(5.0)
            return True
        except Exception as e:
            logger.error(f"ADBController: Erro ao recuperar aplicativo: {e}")
            return False
