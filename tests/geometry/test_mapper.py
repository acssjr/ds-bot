import math
import random

import numpy as np
import pytest
from hypothesis import given, strategies as st

from src.geometry.mapper import CoordinateMapper
from src.geometry.models import DisplayProfile, NormalizedPoint, PixelPoint, RectXYXY, Size
from src.utils.coordinates import CoordinateConverter


def portrait_profile() -> DisplayProfile:
    return DisplayProfile(
        framebuffer=Size(720, 1280),
        logical=Size(720, 1280),
        density_dpi=240,
        rotation_degrees=0,
        content_rect=RectXYXY(0, 0, 720, 1280),
    )


def test_normalized_edges_stay_inside_framebuffer() -> None:
    mapper = CoordinateMapper(portrait_profile())
    assert mapper.normalized_to_framebuffer(NormalizedPoint(0.0, 0.0)).as_tuple() == (0, 0)
    assert mapper.normalized_to_framebuffer(NormalizedPoint(1.0, 1.0)).as_tuple() == (719, 1279)


def test_normalized_points_reject_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        NormalizedPoint(1.01, 0.5)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Size(True, 1),
        lambda: Size(1.5, 2),
        lambda: PixelPoint(math.nan, 1),
        lambda: PixelPoint(1, object()),
        lambda: RectXYXY(0.0, 0, 2, 2),
        lambda: RectXYXY(0, 0, 1.5, 2),
        lambda: DisplayProfile(Size(2, 2), Size(2, 2), True, 0, RectXYXY(0, 0, 2, 2)),
        lambda: DisplayProfile(Size(2, 2), Size(2, 2), 160, False, RectXYXY(0, 0, 2, 2)),
    ],
)
def test_integer_geometry_rejects_bool_and_non_integer_values(factory) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        factory()


@pytest.mark.parametrize(
    "x, y",
    [(True, 0.5), (math.nan, 0.5), (math.inf, 0.5), (object(), 0.5)],
)
def test_normalized_point_rejects_non_finite_or_non_real_values(x, y) -> None:
    with pytest.raises((TypeError, ValueError), match="real numbers|finite"):
        NormalizedPoint(x, y)


@given(
    width=st.integers(min_value=1, max_value=2000),
    height=st.integers(min_value=1, max_value=2000),
    x=st.floats(min_value=0, max_value=1, allow_nan=False),
    y=st.floats(min_value=0, max_value=1, allow_nan=False),
)
def test_mapping_never_escapes_frame(width: int, height: int, x: float, y: float) -> None:
    profile = DisplayProfile(
        framebuffer=Size(width, height),
        logical=Size(width, height),
        density_dpi=160,
        rotation_degrees=0,
        content_rect=RectXYXY(0, 0, width, height),
    )
    point = CoordinateMapper(profile).normalized_to_framebuffer(NormalizedPoint(x, y))
    assert 0 <= point.x < width
    assert 0 <= point.y < height


def test_safe_sampling_stays_inside_inset_box() -> None:
    mapper = CoordinateMapper(portrait_profile())
    target = RectXYXY(100, 200, 200, 300)
    points = [mapper.sample_target(target, inset_px=10, rng=random.Random(seed)) for seed in range(100)]
    assert all(110 <= point.x < 190 and 210 <= point.y < 290 for point in points)


def test_legacy_converter_round_trips_and_full_roi_keeps_last_pixel() -> None:
    nx, ny = CoordinateConverter.normalize(719, 1279, 720, 1280)
    assert CoordinateConverter.denormalize(nx, ny, 720, 1280) == (719, 1279)

    image = np.zeros((1280, 720, 3), dtype=np.uint8)
    assert CoordinateConverter.crop_roi(image, (0.0, 0.0, 1.0, 1.0)).shape == image.shape


@pytest.mark.parametrize("image", [None, np.array([]), np.empty((0, 10, 3)), np.empty((10, 0, 3))])
def test_crop_roi_rejects_missing_or_empty_images(image) -> None:
    with pytest.raises(ValueError, match="non-empty array"):
        CoordinateConverter.crop_roi(image, (0.0, 0.0, 1.0, 1.0))
