from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Size:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("size dimensions must be positive")


@dataclass(frozen=True, slots=True)
class PixelPoint:
    x: int
    y: int

    def as_tuple(self) -> tuple[int, int]:
        return self.x, self.y


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0):
            raise ValueError("normalized coordinates must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class RectXYXY:
    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("rectangle must have positive width and height")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def contains(self, point: PixelPoint) -> bool:
        return self.left <= point.x < self.right and self.top <= point.y < self.bottom

    def inset(self, pixels: int) -> "RectXYXY":
        if pixels < 0:
            raise ValueError("inset must be non-negative")
        if self.width <= pixels * 2 or self.height <= pixels * 2:
            raise ValueError("inset removes the complete rectangle")
        return RectXYXY(
            self.left + pixels,
            self.top + pixels,
            self.right - pixels,
            self.bottom - pixels,
        )


@dataclass(frozen=True, slots=True)
class DisplayProfile:
    framebuffer: Size
    logical: Size
    density_dpi: int
    rotation_degrees: int
    content_rect: RectXYXY

    def __post_init__(self) -> None:
        if self.density_dpi <= 0:
            raise ValueError("density must be positive")
        if self.rotation_degrees not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180, or 270")
        if self.content_rect.left < 0 or self.content_rect.top < 0:
            raise ValueError("content rectangle starts outside framebuffer")
        if self.content_rect.right > self.framebuffer.width or self.content_rect.bottom > self.framebuffer.height:
            raise ValueError("content rectangle ends outside framebuffer")
