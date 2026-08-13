from typing import Tuple

class CoordinateConverter:
    """Utilitário para normalizar e denormalizar coordenadas de tela entre [0.0, 1.0] e pixels reais."""
    
    @staticmethod
    def normalize(pixel_x: int, pixel_y: int, screen_width: int, screen_height: int) -> Tuple[float, float]:
        """Converte coordenadas em pixels para o espaço normalizado [0.0, 1.0]."""
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("Dimensões da tela devem ser maiores que zero.")
        norm_x = max(0.0, min(1.0, pixel_x / screen_width))
        norm_y = max(0.0, min(1.0, pixel_y / screen_height))
        return (norm_x, norm_y)

    @staticmethod
    def denormalize(norm_x: float, norm_y: float, screen_width: int, screen_height: int) -> Tuple[int, int]:
        """Converte coordenadas normalizadas [0.0, 1.0] para pixels absolutos da tela."""
        pixel_x = int(round(norm_x * screen_width))
        pixel_y = int(round(norm_y * screen_height))
        return (pixel_x, pixel_y)

    @staticmethod
    def crop_roi(image, norm_box: Tuple[float, float, float, float]):
        """
        Recorta uma Região de Interesse (ROI) de uma imagem OpenCV (NumPy array)
        usando caixa normalizada (min_x, min_y, max_x, max_y).
        """
        h, w = image.shape[:2]
        min_x, min_y, max_x, max_y = norm_box
        x1, y1 = CoordinateConverter.denormalize(min_x, min_y, w, h)
        x2, y2 = CoordinateConverter.denormalize(max_x, max_y, w, h)
        return image[y1:y2, x1:x2]
