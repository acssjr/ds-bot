import cv2
import numpy as np
import adbutils
from loguru import logger
from typing import Optional

from src.capture.base_capture import BaseCapture

class ADBCapture(BaseCapture):
    """Captura de tela estática via ADB screencap (para bootstrapping e MVP 1)."""

    def __init__(self, device_serial: Optional[str] = None):
        self.device_serial = device_serial
        self.device = None
        self.running = False

    def start(self) -> bool:
        try:
            devices = adbutils.adb.device_list()
            if not devices:
                logger.error("ADBCapture: Nenhum dispositivo ativado via ADB.")
                return False
            
            if self.device_serial:
                self.device = adbutils.adb.device(serial=self.device_serial)
            else:
                self.device = devices[0]
                self.device_serial = self.device.serial
            
            self.running = True
            logger.info(f"ADBCapture: Inicializado no dispositivo {self.device_serial}")
            return True
        except Exception as e:
            logger.error(f"ADBCapture: Falha ao inicializar: {e}")
            return False

    def get_latest_frame(self) -> Optional[np.ndarray]:
        if not self.running or not self.device:
            return None
        try:
            # Obtém screenshot bruta (PIL Image ou PNG bytes) do adbutils
            pil_img = self.device.screenshot()
            frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            return frame
        except Exception as e:
            logger.error(f"ADBCapture: Erro ao capturar screenshot: {e}")
            return None

    def stop(self) -> None:
        self.running = False
        logger.info("ADBCapture: Parado com sucesso.")
