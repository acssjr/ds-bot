# Draft Showdown Safe Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the prototype plumbing with a tested, single-device, observe-only runtime that cannot send live input and that supports native ADB capture, deterministic replay, immutable frames, explicit coordinates, cancellation, and thread-safe UI events.

**Architecture:** One explicitly selected `DeviceSession` is shared by capture and future input components. `CaptureManager` owns frame identity, freshness, cache invalidation, and provenance; `BotRuntime` consumes it through a cancellation-aware observe-only loop and publishes immutable events to CLI or GUI adapters. The existing visual pipeline is temporarily wrapped as legacy perception, but it is not allowed to trigger any action in this phase.

**Tech Stack:** Python 3.12, uv, pytest, Hypothesis, NumPy, OpenCV, adbutils, Pydantic v2, Loguru, CustomTkinter.

---

## Scope and sequencing

This is the first independently testable sub-project from the approved architecture specification. It deliberately ends in observe-only mode. Do not enable the existing action planner or `ADBController` from the new runtime.

The remaining specification is split into later plans, created after the preceding interfaces have passed their quality gates:

1. Perception manifest, ROIs, automatic dataset recording, diagnostics, and real state coverage.
2. Atomic FSM, action ledger, postcondition verification, health monitor, and recovery ladder.
3. Card recognition, OCR profiles, knowledge base, and explainable draft strategy.
4. Arena calibration, positioning, results/rewards, and complete match cycle.
5. Measured Scrcpy, Minitouch, ONNX, or YOLO optimization where benchmarks justify it.

## Workspace prerequisite

The current workspace is not a Git repository. Before executing commit steps, initialize Git and make a reviewed baseline commit, or explicitly agree to execute without commits. A dedicated worktree cannot be created until that baseline exists. Do not delete or overwrite the current `.venv`; create `.venv312` alongside it.

## File map

### Create

- `.python-version` — declares the supported interpreter line.
- `src/__init__.py` — makes the application package explicit.
- `src/geometry/models.py` — typed sizes, points, rectangles, and display profile.
- `src/geometry/mapper.py` — coordinate conversion and bounded target sampling.
- `src/capture/models.py` — immutable frame and capture request contracts.
- `src/capture/adb_source.py` — native ADB capture through the shared device session.
- `src/capture/replay.py` — deterministic image-sequence capture source.
- `src/capture/manager.py` — frame sequence, cache, freshness, and invalidation.
- `src/device/session.py` — explicit serial binding and shared ADB device access.
- `src/core/cancellation.py` — cooperative cancellation and cancel-aware waits.
- `src/core/events.py` — immutable runtime events and thread-safe event bus.
- `src/core/lifecycle.py` — validated runtime lifecycle transitions.
- `src/runtime/bot_runtime.py` — single observe-only runtime loop.
- `src/vision/legacy_adapter.py` — adapter around the current `VisionPipeline`.
- `src/input/models.py` — typed low-level input command and receipt contracts.
- `src/input/dry_run.py` — recorder that never contacts the device.
- `src/gui/presenter.py` — pure formatting of runtime events for Tk.
- `tests/test_project_metadata.py`
- `tests/geometry/test_mapper.py`
- `tests/capture/test_models.py`
- `tests/capture/test_manager.py`
- `tests/device/test_session.py`
- `tests/core/test_cancellation.py`
- `tests/core/test_events.py`
- `tests/core/test_lifecycle.py`
- `tests/input/test_dry_run.py`
- `tests/runtime/test_bot_runtime.py`
- `tests/gui/test_presenter.py`
- `tests/test_legacy_compatibility.py`

### Modify

- `pyproject.toml` — interpreter range, runtime dependency parity, test configuration, CLI entry point.
- `src/utils/coordinates.py` — correct edge semantics while retaining the legacy API.
- `src/main.py` — safe CLI over the shared observe-only runtime.
- `src/gui/app.py` — consume runtime events on the Tk thread and remove the legacy clicking loop.
- `README.md` — accurately document current observe-only capability and commands.

### Remove after compatibility tests pass

- `tests/offline_harness.py` — replaced by discoverable tests with stronger assertions.

---

### Task 1: Pin the runtime and make tests discoverable

**Files:**
- Create: `.python-version`
- Create: `src/__init__.py`
- Create: `tests/test_project_metadata.py`
- Modify: `pyproject.toml`
- Generate: `uv.lock`

- [ ] **Step 1: Write the failing metadata test**

```python
# tests/test_project_metadata.py
from pathlib import Path
import tomllib


def test_project_metadata_matches_supported_runtime() -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    pytest_options = metadata["tool"]["pytest"]["ini_options"]

    assert project["requires-python"] == ">=3.12,<3.13"
    assert any(item.startswith("customtkinter") for item in project["dependencies"])
    assert pytest_options["testpaths"] == ["tests"]
    assert pytest_options["python_files"] == ["test_*.py"]
    assert Path("src/__init__.py").is_file()
```

- [ ] **Step 2: Run the test and verify the current metadata fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_metadata.py -v
```

Expected: FAIL because the Python upper bound, CustomTkinter dependency, pytest discovery settings, and explicit package file are absent.

- [ ] **Step 3: Add the runtime pin, package marker, and complete project metadata**

```text
# .python-version
3.12
```

```python
# src/__init__.py
"""Draft Showdown automation package."""

__version__ = "0.2.0"
```

Replace `pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "draft-showdown-bot"
version = "0.2.0"
description = "Closed-loop visual automation for Draft Showdown"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = [
    "adbutils>=2.8,<3",
    "customtkinter>=5.2,<6",
    "loguru>=0.7,<1",
    "numpy>=2,<3",
    "opencv-python>=4.10,<5",
    "pillow>=10,<13",
    "pydantic>=2.8,<3",
]

[project.optional-dependencies]
dev = [
    "hypothesis>=6,<7",
    "pytest>=8,<10",
]

[project.scripts]
draft-showdown-bot = "src.main:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-ra --strict-markers"
pythonpath = ["."]
```

- [ ] **Step 4: Create a separate Python 3.12 environment and lock dependencies**

Run:

```powershell
uv python install 3.12
uv venv .venv312 --python 3.12
uv lock --python 3.12
uv pip install --python .venv312\Scripts\python.exe -e ".[dev]"
```

Expected: `.venv312\Scripts\python.exe --version` reports Python 3.12.x, `uv.lock` is created, and installation completes successfully. The existing `.venv` remains untouched.

- [ ] **Step 5: Run the metadata test in the supported environment**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\test_project_metadata.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the runtime foundation metadata**

```powershell
git add .python-version pyproject.toml uv.lock src/__init__.py tests/test_project_metadata.py
git commit -m "build: pin supported Python runtime"
```

---

### Task 2: Introduce typed geometry and correct coordinate edges

**Files:**
- Create: `src/geometry/models.py`
- Create: `src/geometry/mapper.py`
- Create: `tests/geometry/test_mapper.py`
- Modify: `src/utils/coordinates.py`

- [ ] **Step 1: Write failing geometry and compatibility tests**

```python
# tests/geometry/test_mapper.py
import random

import numpy as np
import pytest
from hypothesis import given, strategies as st

from src.geometry.mapper import CoordinateMapper
from src.geometry.models import DisplayProfile, NormalizedPoint, RectXYXY, Size
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
```

- [ ] **Step 2: Run the geometry tests and verify imports or edge assertions fail**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\geometry\test_mapper.py -v
```

Expected: FAIL because `src.geometry` does not exist and the legacy converter maps `1.0` outside the framebuffer.

- [ ] **Step 3: Implement typed geometry**

```python
# src/geometry/models.py
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
```

```python
# src/geometry/mapper.py
from __future__ import annotations

import random

from src.geometry.models import DisplayProfile, NormalizedPoint, PixelPoint, RectXYXY


class CoordinateMapper:
    def __init__(self, profile: DisplayProfile):
        self.profile = profile

    def normalized_to_framebuffer(self, point: NormalizedPoint) -> PixelPoint:
        rect = self.profile.content_rect
        x = rect.left + round(point.x * max(0, rect.width - 1))
        y = rect.top + round(point.y * max(0, rect.height - 1))
        return PixelPoint(
            min(max(x, rect.left), rect.right - 1),
            min(max(y, rect.top), rect.bottom - 1),
        )

    def sample_target(
        self,
        target: RectXYXY,
        *,
        inset_px: int,
        rng: random.Random,
    ) -> PixelPoint:
        safe = target.inset(inset_px) if inset_px else target
        point = PixelPoint(
            rng.randint(safe.left, safe.right - 1),
            rng.randint(safe.top, safe.bottom - 1),
        )
        if not target.contains(point):
            raise AssertionError("sampled point escaped target")
        return point
```

- [ ] **Step 4: Correct the legacy coordinate adapter**

Replace `src/utils/coordinates.py` with:

```python
import math
from typing import Tuple


class CoordinateConverter:
    """Compatibility adapter for normalized framebuffer coordinates."""

    @staticmethod
    def normalize(
        pixel_x: int,
        pixel_y: int,
        screen_width: int,
        screen_height: int,
    ) -> Tuple[float, float]:
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive")
        if not (0 <= pixel_x < screen_width and 0 <= pixel_y < screen_height):
            raise ValueError("pixel coordinates must be inside the screen")
        nx = 0.0 if screen_width == 1 else pixel_x / (screen_width - 1)
        ny = 0.0 if screen_height == 1 else pixel_y / (screen_height - 1)
        return nx, ny

    @staticmethod
    def denormalize(
        norm_x: float,
        norm_y: float,
        screen_width: int,
        screen_height: int,
    ) -> Tuple[int, int]:
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive")
        if not (0.0 <= norm_x <= 1.0 and 0.0 <= norm_y <= 1.0):
            raise ValueError("normalized coordinates must be between 0 and 1")
        x = round(norm_x * max(0, screen_width - 1))
        y = round(norm_y * max(0, screen_height - 1))
        return x, y

    @staticmethod
    def crop_roi(image, norm_box: Tuple[float, float, float, float]):
        height, width = image.shape[:2]
        left, top, right, bottom = norm_box
        if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
            raise ValueError("ROI must be ordered and inside the normalized screen")
        x1 = max(0, min(width, math.floor(left * width)))
        y1 = max(0, min(height, math.floor(top * height)))
        x2 = max(0, min(width, math.ceil(right * width)))
        y2 = max(0, min(height, math.ceil(bottom * height)))
        return image[y1:y2, x1:x2]
```

- [ ] **Step 5: Run geometry and legacy coordinate tests**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\geometry\test_mapper.py tests\offline_harness.py::test_coordinate_conversion -v
```

Expected: the new geometry tests PASS. Update the legacy test's normalized midpoint expectation from exact `0.5` to `640 / 1279` and `360 / 719`, then rerun until both suites PASS; the pixel round-trip must remain exact.

Use this exact replacement inside `test_coordinate_conversion`:

```python
assert nx == pytest.approx(640 / 1279)
assert ny == pytest.approx(360 / 719)
```

- [ ] **Step 6: Commit typed geometry**

```powershell
git add src/geometry src/utils/coordinates.py tests/geometry/test_mapper.py tests/offline_harness.py
git commit -m "feat: add bounded coordinate geometry"
```

---

### Task 3: Define immutable frame and capture contracts

**Files:**
- Create: `src/capture/models.py`
- Modify: `src/capture/base_capture.py`
- Create: `tests/capture/test_models.py`

- [ ] **Step 1: Write failing frame contract tests**

```python
# tests/capture/test_models.py
import numpy as np
import pytest

from src.capture.models import CaptureBackend, CaptureRequest, CapturedImage, Frame, Freshness
from src.geometry.models import Size


def test_frame_owns_a_read_only_image_and_provenance() -> None:
    original = np.zeros((8, 6, 3), dtype=np.uint8)
    captured = CapturedImage(original, 10.0, CaptureBackend.REPLAY)
    frame = Frame.from_capture(
        captured,
        frame_id=7,
        device_serial="replay",
        connection_generation=2,
        capture_generation=3,
    )

    original[0, 0, 0] = 255
    assert frame.id == 7
    assert frame.size == Size(6, 8)
    assert frame.image[0, 0, 0] == 0
    with pytest.raises(ValueError):
        frame.image[0, 0, 0] = 1


def test_capture_requests_validate_age_and_generation() -> None:
    assert CaptureRequest.reuse_ok(0.25).freshness is Freshness.REUSE_OK
    assert CaptureRequest.fresh_required(4).minimum_generation == 4
    with pytest.raises(ValueError):
        CaptureRequest.reuse_ok(-0.1)
```

- [ ] **Step 2: Run the test and verify the model import fails**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\capture\test_models.py -v
```

Expected: FAIL because the capture contracts do not exist.

- [ ] **Step 3: Implement the capture contracts**

```python
# src/capture/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from src.geometry.models import Size


class CaptureBackend(str, Enum):
    ADB_PNG = "adb_png"
    REPLAY = "replay"


class Freshness(str, Enum):
    REUSE_OK = "reuse_ok"
    FRESH_REQUIRED = "fresh_required"


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    freshness: Freshness
    max_age_seconds: float = 0.0
    minimum_generation: int = 0

    def __post_init__(self) -> None:
        if self.max_age_seconds < 0:
            raise ValueError("max age must be non-negative")
        if self.minimum_generation < 0:
            raise ValueError("minimum generation must be non-negative")

    @classmethod
    def reuse_ok(cls, max_age_seconds: float) -> "CaptureRequest":
        return cls(Freshness.REUSE_OK, max_age_seconds=max_age_seconds)

    @classmethod
    def fresh_required(cls, minimum_generation: int = 0) -> "CaptureRequest":
        return cls(Freshness.FRESH_REQUIRED, minimum_generation=minimum_generation)


@dataclass(frozen=True, slots=True)
class CapturedImage:
    image: np.ndarray = field(repr=False, compare=False)
    captured_at_monotonic: float
    backend: CaptureBackend

    def __post_init__(self) -> None:
        if self.image.ndim != 3 or self.image.shape[2] != 3:
            raise ValueError("captured image must be an HxWx3 BGR array")


@dataclass(frozen=True, slots=True)
class Frame:
    id: int
    image: np.ndarray = field(repr=False, compare=False)
    captured_at_monotonic: float
    device_serial: str
    backend: CaptureBackend
    size: Size
    connection_generation: int
    capture_generation: int

    @classmethod
    def from_capture(
        cls,
        captured: CapturedImage,
        *,
        frame_id: int,
        device_serial: str,
        connection_generation: int,
        capture_generation: int,
    ) -> "Frame":
        image = np.ascontiguousarray(captured.image).copy()
        image.setflags(write=False)
        height, width = image.shape[:2]
        return cls(
            id=frame_id,
            image=image,
            captured_at_monotonic=captured.captured_at_monotonic,
            device_serial=device_serial,
            backend=captured.backend,
            size=Size(width, height),
            connection_generation=connection_generation,
            capture_generation=capture_generation,
        )

    def age_seconds(self, now_monotonic: float) -> float:
        return max(0.0, now_monotonic - self.captured_at_monotonic)
```

Replace `src/capture/base_capture.py` with:

```python
from typing import Protocol

from src.capture.models import CapturedImage


class CaptureSource(Protocol):
    def start(self) -> None: ...

    def capture(self) -> CapturedImage: ...

    def stop(self) -> None: ...
```

- [ ] **Step 4: Run capture model tests**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\capture\test_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit immutable frame contracts**

```powershell
git add src/capture/models.py src/capture/base_capture.py tests/capture/test_models.py
git commit -m "feat: define immutable capture frames"
```

---

### Task 4: Bind all device access to one explicit serial

**Files:**
- Create: `src/device/session.py`
- Create: `tests/device/test_session.py`

- [ ] **Step 1: Write failing explicit-device tests**

```python
# tests/device/test_session.py
import pytest

from src.device.session import DeviceNotFound, DeviceSession


class FakeDevice:
    def __init__(self, serial: str):
        self.serial = serial
        self.clicks: list[tuple[int, int]] = []

    def screenshot(self):
        return "image"

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class FakeAdbClient:
    def __init__(self, serials: list[str]):
        self.devices = {serial: FakeDevice(serial) for serial in serials}

    def device_list(self):
        return list(self.devices.values())

    def device(self, serial: str):
        return self.devices[serial]


def test_session_requires_an_explicit_serial() -> None:
    with pytest.raises(ValueError, match="explicit serial"):
        DeviceSession("", adb_client=FakeAdbClient(["A"]))


def test_session_binds_only_to_requested_device() -> None:
    client = FakeAdbClient(["A", "B"])
    session = DeviceSession("B", adb_client=client)
    session.connect()
    session.click(10, 20)

    assert session.serial == "B"
    assert session.connection_generation == 1
    assert client.devices["A"].clicks == []
    assert client.devices["B"].clicks == [(10, 20)]


def test_missing_requested_device_is_not_replaced_by_first_device() -> None:
    session = DeviceSession("missing", adb_client=FakeAdbClient(["A", "B"]))
    with pytest.raises(DeviceNotFound, match="missing"):
        session.connect()
```

- [ ] **Step 2: Run the tests and verify the device module is missing**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\device\test_session.py -v
```

Expected: FAIL because `DeviceSession` does not exist.

- [ ] **Step 3: Implement the shared device session**

```python
# src/device/session.py
from __future__ import annotations

from typing import Any

import adbutils


class DeviceSessionError(RuntimeError):
    pass


class DeviceNotFound(DeviceSessionError):
    pass


class DeviceNotConnected(DeviceSessionError):
    pass


class DeviceSession:
    def __init__(self, serial: str, *, adb_client: Any = None):
        if not serial or not serial.strip():
            raise ValueError("an explicit serial is required")
        self.serial = serial.strip()
        self._adb = adb_client if adb_client is not None else adbutils.adb
        self._device: Any = None
        self.connection_generation = 0

    @property
    def connected(self) -> bool:
        return self._device is not None

    def connect(self) -> None:
        available = {device.serial for device in self._adb.device_list()}
        if self.serial not in available:
            raise DeviceNotFound(
                f"requested device {self.serial!r} is unavailable; found {sorted(available)!r}"
            )
        self._device = self._adb.device(serial=self.serial)
        self.connection_generation += 1

    def disconnect(self) -> None:
        self._device = None

    def _require_device(self):
        if self._device is None:
            raise DeviceNotConnected(f"device {self.serial!r} is not connected")
        return self._device

    def screenshot(self):
        return self._require_device().screenshot()

    def click(self, x: int, y: int) -> None:
        self._require_device().click(x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_seconds: float) -> None:
        self._require_device().swipe(x1, y1, x2, y2, duration_seconds)

    def shell(self, command: str) -> str:
        return str(self._require_device().shell(command))

    def stop_app(self, package_name: str) -> None:
        self._require_device().app_stop(package_name)

    def start_app(self, package_name: str) -> None:
        self._require_device().app_start(package_name)
```

- [ ] **Step 4: Run explicit-device tests**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\device\test_session.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit explicit device binding**

```powershell
git add src/device/session.py tests/device/test_session.py
git commit -m "feat: bind runtime to explicit adb device"
```

---

### Task 5: Add ADB and replay sources with freshness-aware capture

**Files:**
- Create: `src/capture/adb_source.py`
- Create: `src/capture/replay.py`
- Create: `src/capture/manager.py`
- Create: `tests/capture/test_manager.py`

- [ ] **Step 1: Write failing capture-manager tests**

```python
# tests/capture/test_manager.py
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from src.capture.adb_source import ADBCaptureSource
from src.capture.manager import CaptureManager
from src.capture.models import CaptureBackend, CaptureRequest, CapturedImage
from src.capture.replay import ReplayCaptureSource, ReplayExhausted


class FakeClock:
    def __init__(self, value: float = 10.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeSource:
    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.calls = 0

    def start(self) -> None:
        pass

    def capture(self) -> CapturedImage:
        self.calls += 1
        image = np.full((4, 5, 3), self.calls, dtype=np.uint8)
        return CapturedImage(image, self.clock(), CaptureBackend.REPLAY)

    def stop(self) -> None:
        pass


class FakeSession:
    def __init__(self):
        self.connected = False
        self.connection_generation = 0

    def connect(self) -> None:
        self.connected = True
        self.connection_generation += 1

    def screenshot(self):
        rgb = np.array([[[255, 0, 0], [0, 255, 0]]], dtype=np.uint8)
        return Image.fromarray(rgb, mode="RGB")


def test_adb_source_connects_once_and_converts_rgb_to_bgr() -> None:
    session = FakeSession()
    source = ADBCaptureSource(session, clock=lambda: 3.0)
    source.start()
    captured = source.capture()

    assert session.connected
    assert captured.backend is CaptureBackend.ADB_PNG
    assert captured.captured_at_monotonic == 3.0
    assert captured.image.tolist() == [[[0, 0, 255], [0, 255, 0]]]


def test_manager_reuses_only_a_fresh_frame_from_current_generation() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 1, clock=clock)

    first = manager.next_frame(CaptureRequest.fresh_required())
    reused = manager.next_frame(CaptureRequest.reuse_ok(0.5))
    assert reused is first
    assert source.calls == 1

    clock.value += 0.6
    expired = manager.next_frame(CaptureRequest.reuse_ok(0.5))
    assert expired.id == 2
    assert source.calls == 2


def test_input_invalidation_forces_a_new_generation_and_frame() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 1, clock=clock)
    first = manager.next_frame(CaptureRequest.fresh_required())

    generation = manager.invalidate_after_input()
    second = manager.next_frame(CaptureRequest.fresh_required(generation))

    assert second.id == first.id + 1
    assert second.capture_generation == generation
    assert source.calls == 2


def test_replay_reads_each_file_once_and_reports_exhaustion(tmp_path: Path) -> None:
    paths = []
    for index in range(2):
        path = tmp_path / f"{index}.png"
        assert cv2.imwrite(str(path), np.full((3, 4, 3), index, dtype=np.uint8))
        paths.append(path)

    replay = ReplayCaptureSource(paths, clock=lambda: 5.0)
    replay.start()
    assert int(replay.capture().image[0, 0, 0]) == 0
    assert int(replay.capture().image[0, 0, 0]) == 1
    with pytest.raises(ReplayExhausted):
        replay.capture()
```

- [ ] **Step 2: Run tests and verify source/manager imports fail**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\capture\test_manager.py -v
```

Expected: FAIL because the source and manager modules do not exist.

- [ ] **Step 3: Implement the ADB source**

```python
# src/capture/adb_source.py
from __future__ import annotations

import time
from collections.abc import Callable

import cv2
import numpy as np

from src.capture.models import CaptureBackend, CapturedImage
from src.device.session import DeviceSession


class ADBCaptureSource:
    def __init__(self, session: DeviceSession, *, clock: Callable[[], float] = time.monotonic):
        self._session = session
        self._clock = clock

    def start(self) -> None:
        if not self._session.connected:
            self._session.connect()

    def capture(self) -> CapturedImage:
        rgb = np.asarray(self._session.screenshot())
        if rgb.ndim != 3 or rgb.shape[2] not in (3, 4):
            raise ValueError(f"unexpected screenshot shape: {rgb.shape!r}")
        conversion = cv2.COLOR_RGBA2BGR if rgb.shape[2] == 4 else cv2.COLOR_RGB2BGR
        bgr = cv2.cvtColor(rgb, conversion)
        return CapturedImage(bgr, self._clock(), CaptureBackend.ADB_PNG)

    def stop(self) -> None:
        pass
```

- [ ] **Step 4: Implement deterministic replay**

```python
# src/capture/replay.py
from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path

import cv2

from src.capture.models import CaptureBackend, CapturedImage


class ReplayExhausted(EOFError):
    pass


class ReplayCaptureSource:
    def __init__(
        self,
        paths: Iterable[Path],
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._paths = tuple(Path(path) for path in paths)
        if not self._paths:
            raise ValueError("replay requires at least one image")
        self._clock = clock
        self._index = 0

    def start(self) -> None:
        self._index = 0

    def capture(self) -> CapturedImage:
        if self._index >= len(self._paths):
            raise ReplayExhausted("replay sequence is complete")
        path = self._paths[self._index]
        self._index += 1
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"unable to decode replay image: {path}")
        return CapturedImage(image, self._clock(), CaptureBackend.REPLAY)

    def stop(self) -> None:
        pass
```

- [ ] **Step 5: Implement capture freshness and provenance**

```python
# src/capture/manager.py
from __future__ import annotations

import time
from collections.abc import Callable

from src.capture.base_capture import CaptureSource
from src.capture.models import CaptureRequest, Frame, Freshness


class CaptureManager:
    def __init__(
        self,
        source: CaptureSource,
        *,
        device_serial: str,
        connection_generation: Callable[[], int],
        clock: Callable[[], float] = time.monotonic,
    ):
        self._source = source
        self._device_serial = device_serial
        self._connection_generation = connection_generation
        self._clock = clock
        self._last_frame: Frame | None = None
        self._next_frame_id = 1
        self._capture_generation = 0

    def start(self) -> None:
        self._source.start()

    def stop(self) -> None:
        self._source.stop()

    def invalidate_after_input(self) -> int:
        self._capture_generation += 1
        self._last_frame = None
        return self._capture_generation

    def next_frame(self, request: CaptureRequest) -> Frame:
        if self._capture_generation < request.minimum_generation:
            raise ValueError("capture generation was not invalidated for requested action")

        cached = self._last_frame
        if (
            request.freshness is Freshness.REUSE_OK
            and cached is not None
            and cached.capture_generation == self._capture_generation
            and cached.age_seconds(self._clock()) <= request.max_age_seconds
        ):
            return cached

        captured = self._source.capture()
        frame = Frame.from_capture(
            captured,
            frame_id=self._next_frame_id,
            device_serial=self._device_serial,
            connection_generation=self._connection_generation(),
            capture_generation=self._capture_generation,
        )
        self._next_frame_id += 1
        self._last_frame = frame
        return frame
```

- [ ] **Step 6: Run capture manager tests**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\capture -v
```

Expected: all capture tests PASS.

- [ ] **Step 7: Commit capture sources and manager**

```powershell
git add src/capture/adb_source.py src/capture/replay.py src/capture/manager.py tests/capture
git commit -m "feat: add freshness-aware capture manager"
```

---

### Task 6: Add cancellation, events, and validated lifecycle

**Files:**
- Create: `src/core/cancellation.py`
- Create: `src/core/events.py`
- Create: `src/core/lifecycle.py`
- Create: `tests/core/test_cancellation.py`
- Create: `tests/core/test_events.py`
- Create: `tests/core/test_lifecycle.py`

- [ ] **Step 1: Write failing core coordination tests**

```python
# tests/core/test_cancellation.py
import pytest

from src.core.cancellation import Cancelled, CancellationToken


def test_cancelled_wait_raises_without_sleeping() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Cancelled):
        token.wait(30.0)
```

```python
# tests/core/test_events.py
from src.core.events import EventBus, EventKind, RuntimeEvent


def test_event_bus_preserves_fifo_order() -> None:
    bus = EventBus()
    bus.publish(RuntimeEvent(EventKind.FRAME, 1.0, {"frame_id": 1}))
    bus.publish(RuntimeEvent(EventKind.OBSERVATION, 2.0, {"frame_id": 1}))
    assert [event.kind for event in bus.drain()] == [EventKind.FRAME, EventKind.OBSERVATION]
    assert bus.drain() == []
```

```python
# tests/core/test_lifecycle.py
import pytest

from src.core.lifecycle import InvalidLifecycleTransition, Lifecycle, RuntimeStatus


def test_lifecycle_accepts_normal_start_and_stop() -> None:
    lifecycle = Lifecycle()
    lifecycle.transition(RuntimeStatus.STARTING)
    lifecycle.transition(RuntimeStatus.RUNNING)
    lifecycle.transition(RuntimeStatus.STOPPING)
    lifecycle.transition(RuntimeStatus.STOPPED)
    assert lifecycle.status is RuntimeStatus.STOPPED


def test_lifecycle_rejects_running_directly_from_stopped() -> None:
    with pytest.raises(InvalidLifecycleTransition):
        Lifecycle().transition(RuntimeStatus.RUNNING)
```

- [ ] **Step 2: Run the core tests and verify imports fail**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\core -v
```

Expected: FAIL because the core coordination modules do not exist.

- [ ] **Step 3: Implement cooperative cancellation**

```python
# src/core/cancellation.py
from __future__ import annotations

import threading


class Cancelled(RuntimeError):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise Cancelled("operation cancelled")

    def wait(self, timeout_seconds: float) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout must be non-negative")
        if self._event.wait(timeout_seconds):
            raise Cancelled("operation cancelled")
```

- [ ] **Step 4: Implement immutable runtime events**

```python
# src/core/events.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from queue import Empty, SimpleQueue
from types import MappingProxyType
from typing import Any, Mapping


class EventKind(str, Enum):
    LIFECYCLE = "lifecycle"
    FRAME = "frame"
    OBSERVATION = "observation"
    INPUT = "input"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    kind: EventKind
    emitted_at_monotonic: float
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class EventBus:
    def __init__(self) -> None:
        self._queue: SimpleQueue[RuntimeEvent] = SimpleQueue()

    def publish(self, event: RuntimeEvent) -> None:
        self._queue.put(event)

    def drain(self, limit: int = 1000) -> list[RuntimeEvent]:
        events: list[RuntimeEvent] = []
        while len(events) < limit:
            try:
                events.append(self._queue.get_nowait())
            except Empty:
                break
        return events
```

- [ ] **Step 5: Implement validated lifecycle transitions**

```python
# src/core/lifecycle.py
from __future__ import annotations

from enum import Enum


class RuntimeStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    FAILED = "failed"


class InvalidLifecycleTransition(RuntimeError):
    pass


_ALLOWED = {
    RuntimeStatus.STOPPED: {RuntimeStatus.STARTING},
    RuntimeStatus.STARTING: {RuntimeStatus.RUNNING, RuntimeStatus.STOPPING, RuntimeStatus.FAILED},
    RuntimeStatus.RUNNING: {RuntimeStatus.PAUSED, RuntimeStatus.STOPPING, RuntimeStatus.FAILED},
    RuntimeStatus.PAUSED: {RuntimeStatus.RUNNING, RuntimeStatus.STOPPING, RuntimeStatus.FAILED},
    RuntimeStatus.STOPPING: {RuntimeStatus.STOPPED, RuntimeStatus.FAILED},
    RuntimeStatus.FAILED: {RuntimeStatus.STOPPED},
}


class Lifecycle:
    def __init__(self) -> None:
        self._status = RuntimeStatus.STOPPED

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    def transition(self, target: RuntimeStatus) -> None:
        if target not in _ALLOWED[self._status]:
            raise InvalidLifecycleTransition(f"cannot transition from {self._status} to {target}")
        self._status = target
```

- [ ] **Step 6: Run all core tests**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\core -v
```

Expected: PASS.

- [ ] **Step 7: Commit core coordination primitives**

```powershell
git add src/core tests/core
git commit -m "feat: add cancellable runtime coordination"
```

---

### Task 7: Add a dry-run input boundary that cannot touch ADB

**Files:**
- Create: `src/input/models.py`
- Create: `src/input/dry_run.py`
- Create: `tests/input/test_dry_run.py`

- [ ] **Step 1: Write the failing dry-run input test**

```python
# tests/input/test_dry_run.py
from src.core.events import EventBus, EventKind
from src.geometry.models import PixelPoint
from src.input.dry_run import DryRunInput
from src.input.models import InputStatus, TapCommand


def test_dry_run_records_command_without_a_device_dependency() -> None:
    bus = EventBus()
    backend = DryRunInput(events=bus, clock=lambda: 12.0)
    command = TapCommand(command_id="tap-1", point=PixelPoint(10, 20), hold_ms=30)

    receipt = backend.execute(command)

    assert receipt.status is InputStatus.DRY_RUN
    assert receipt.backend == "dry_run"
    assert backend.commands == [command]
    events = bus.drain()
    assert len(events) == 1
    assert events[0].kind is EventKind.INPUT
    assert events[0].payload["command_id"] == "tap-1"
```

- [ ] **Step 2: Run the test and verify input modules are absent**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\input\test_dry_run.py -v
```

Expected: FAIL because the input contracts do not exist.

- [ ] **Step 3: Implement typed input commands and receipts**

```python
# src/input/models.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.geometry.models import PixelPoint


class InputStatus(str, Enum):
    DRY_RUN = "dry_run"
    FAILED_BEFORE_SEND = "failed_before_send"
    SENT = "sent"
    COMMIT_UNKNOWN = "commit_unknown"


@dataclass(frozen=True, slots=True)
class TapCommand:
    command_id: str
    point: PixelPoint
    hold_ms: int = 30

    def __post_init__(self) -> None:
        if not self.command_id:
            raise ValueError("command id is required")
        if self.hold_ms <= 0:
            raise ValueError("hold duration must be positive")


@dataclass(frozen=True, slots=True)
class InputReceipt:
    command_id: str
    status: InputStatus
    backend: str
    started_at_monotonic: float
    completed_at_monotonic: float
    detail: str = ""
```

- [ ] **Step 4: Implement dry-run recording without accepting a device**

```python
# src/input/dry_run.py
from __future__ import annotations

import time
from collections.abc import Callable

from src.core.events import EventBus, EventKind, RuntimeEvent
from src.input.models import InputReceipt, InputStatus, TapCommand


class DryRunInput:
    def __init__(self, *, events: EventBus, clock: Callable[[], float] = time.monotonic):
        self._events = events
        self._clock = clock
        self.commands: list[TapCommand] = []

    def execute(self, command: TapCommand) -> InputReceipt:
        started = self._clock()
        self.commands.append(command)
        receipt = InputReceipt(
            command_id=command.command_id,
            status=InputStatus.DRY_RUN,
            backend="dry_run",
            started_at_monotonic=started,
            completed_at_monotonic=self._clock(),
            detail="command recorded; no input sent",
        )
        self._events.publish(
            RuntimeEvent(
                EventKind.INPUT,
                receipt.completed_at_monotonic,
                {"command_id": command.command_id, "status": receipt.status.value},
            )
        )
        return receipt
```

- [ ] **Step 5: Run the dry-run test**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\input\test_dry_run.py -v
```

Expected: PASS. Static inspection must confirm `src/input/dry_run.py` does not import `adbutils`, `DeviceSession`, or the legacy `ADBController`.

- [ ] **Step 6: Commit the safe input boundary**

```powershell
git add src/input tests/input
git commit -m "feat: add non-invasive dry-run input"
```

---

### Task 8: Build the single observe-only runtime and safe CLI

**Files:**
- Create: `src/runtime/bot_runtime.py`
- Create: `src/vision/legacy_adapter.py`
- Create: `tests/runtime/test_bot_runtime.py`
- Modify: `src/main.py`

- [ ] **Step 1: Write failing runtime tests**

```python
# tests/runtime/test_bot_runtime.py
import numpy as np
import pytest

from src.capture.manager import CaptureManager
from src.capture.models import CaptureBackend, CapturedImage
from src.core.cancellation import CancellationToken
from src.core.events import EventBus, EventKind
from src.core.lifecycle import Lifecycle, RuntimeStatus
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings


class OneFrameSource:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def capture(self) -> CapturedImage:
        return CapturedImage(np.zeros((4, 5, 3), dtype=np.uint8), 1.0, CaptureBackend.REPLAY)

    def stop(self) -> None:
        self.stopped = True


class FakePerception:
    def analyze(self, image):
        return {"screen": "UNKNOWN", "confidence": 0.0, "shape": image.shape}


class FailingPerception:
    def analyze(self, image):
        raise RuntimeError("vision failed")


def test_runtime_processes_one_frame_and_never_requires_input() -> None:
    source = OneFrameSource()
    manager = CaptureManager(
        source,
        device_serial="replay",
        connection_generation=lambda: 0,
        clock=lambda: 1.0,
    )
    events = EventBus()
    lifecycle = Lifecycle()
    runtime = BotRuntime(
        capture=manager,
        perception=FakePerception(),
        events=events,
        lifecycle=lifecycle,
        cancellation=CancellationToken(),
        settings=RuntimeSettings(poll_interval_seconds=0.0),
        clock=lambda: 1.0,
    )

    assert runtime.run(max_frames=1) == 1
    assert source.started and source.stopped
    assert lifecycle.status is RuntimeStatus.STOPPED
    kinds = [event.kind for event in events.drain()]
    assert kinds == [
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
        EventKind.FRAME,
        EventKind.OBSERVATION,
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
    ]
    assert EventKind.INPUT not in kinds


def test_runtime_stops_capture_and_preserves_failed_status() -> None:
    source = OneFrameSource()
    manager = CaptureManager(
        source,
        device_serial="replay",
        connection_generation=lambda: 0,
        clock=lambda: 1.0,
    )
    events = EventBus()
    lifecycle = Lifecycle()
    runtime = BotRuntime(
        capture=manager,
        perception=FailingPerception(),
        events=events,
        lifecycle=lifecycle,
        cancellation=CancellationToken(),
        settings=RuntimeSettings(poll_interval_seconds=0.0),
        clock=lambda: 1.0,
    )

    with pytest.raises(RuntimeError, match="vision failed"):
        runtime.run(max_frames=1)
    assert source.stopped
    assert lifecycle.status is RuntimeStatus.FAILED
    assert EventKind.ERROR in [event.kind for event in events.drain()]
```

- [ ] **Step 2: Run the runtime test and verify imports fail**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\runtime\test_bot_runtime.py -v
```

Expected: FAIL because `BotRuntime` does not exist.

- [ ] **Step 3: Implement the observe-only runtime**

```python
# src/runtime/bot_runtime.py
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from src.capture.manager import CaptureManager
from src.capture.models import CaptureRequest
from src.core.cancellation import Cancelled, CancellationToken
from src.core.events import EventBus, EventKind, RuntimeEvent
from src.core.lifecycle import Lifecycle, RuntimeStatus


class Perception(Protocol):
    def analyze(self, image) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    poll_interval_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.poll_interval_seconds < 0:
            raise ValueError("poll interval must be non-negative")


class BotRuntime:
    """Single-session, observe-only runtime. It has no input dependency."""

    def __init__(
        self,
        *,
        capture: CaptureManager,
        perception: Perception,
        events: EventBus,
        lifecycle: Lifecycle,
        cancellation: CancellationToken,
        settings: RuntimeSettings,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._capture = capture
        self._perception = perception
        self._events = events
        self._lifecycle = lifecycle
        self._cancellation = cancellation
        self._settings = settings
        self._clock = clock

    def _transition(self, status: RuntimeStatus) -> None:
        self._lifecycle.transition(status)
        self._events.publish(
            RuntimeEvent(EventKind.LIFECYCLE, self._clock(), {"status": status.value})
        )

    def run(self, *, max_frames: int | None = None) -> int:
        if max_frames is not None and max_frames <= 0:
            raise ValueError("max_frames must be positive or None")
        processed = 0
        self._transition(RuntimeStatus.STARTING)
        try:
            self._capture.start()
            self._transition(RuntimeStatus.RUNNING)
            while max_frames is None or processed < max_frames:
                self._cancellation.raise_if_cancelled()
                frame = self._capture.next_frame(CaptureRequest.fresh_required())
                self._events.publish(
                    RuntimeEvent(
                        EventKind.FRAME,
                        self._clock(),
                        {
                            "frame_id": frame.id,
                            "backend": frame.backend.value,
                            "width": frame.size.width,
                            "height": frame.size.height,
                        },
                    )
                )
                observation = dict(self._perception.analyze(frame.image))
                observation["frame_id"] = frame.id
                self._events.publish(
                    RuntimeEvent(EventKind.OBSERVATION, self._clock(), observation)
                )
                processed += 1
                if max_frames is None or processed < max_frames:
                    self._cancellation.wait(self._settings.poll_interval_seconds)
        except Cancelled:
            pass
        except Exception as exc:
            self._events.publish(
                RuntimeEvent(EventKind.ERROR, self._clock(), {"error": repr(exc)})
            )
            self._transition(RuntimeStatus.FAILED)
            raise
        finally:
            self._capture.stop()
            if self._lifecycle.status in (RuntimeStatus.STARTING, RuntimeStatus.RUNNING, RuntimeStatus.PAUSED):
                self._transition(RuntimeStatus.STOPPING)
                self._transition(RuntimeStatus.STOPPED)
        return processed
```

- [ ] **Step 4: Add the legacy perception adapter without changing its behavior**

```python
# src/vision/legacy_adapter.py
from __future__ import annotations

from typing import Any

from src.state.game_state import ScreenState
from src.vision.pipeline import VisionPipeline


class LegacyVisionAdapter:
    def __init__(self, templates_dir: str = "assets/templates"):
        self._pipeline = VisionPipeline(templates_dir=templates_dir)

    def analyze(self, image) -> dict[str, Any]:
        result = dict(self._pipeline.analyze(image))
        screen = result.get("screen", ScreenState.UNKNOWN)
        result["screen"] = screen.value if isinstance(screen, ScreenState) else str(screen)
        result.pop("available_choices", None)
        result.pop("frame_shape", None)
        return result
```

The adapter intentionally removes fabricated card choices from emitted runtime observations. Task 2 of the perception plan will remove that fabrication at its source.

- [ ] **Step 5: Replace the CLI with explicit live or replay observe-only modes**

```python
# src/main.py
from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from src.capture.adb_source import ADBCaptureSource
from src.capture.manager import CaptureManager
from src.capture.replay import ReplayCaptureSource
from src.core.cancellation import CancellationToken
from src.core.events import EventBus
from src.core.lifecycle import Lifecycle
from src.device.session import DeviceSession
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings
from src.utils.logging_config import setup_logger
from src.vision.legacy_adapter import LegacyVisionAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft Showdown observe-only runtime")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--device", help="explicit ADB serial, for example 127.0.0.1:21503")
    source.add_argument("--replay", type=Path, help="directory containing replay PNG/JPG files")
    parser.add_argument("--frames", type=int, default=None, help="stop after this many frames")
    parser.add_argument("--interval", type=float, default=0.25, help="seconds between frames")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logger("INFO")
    cancellation = CancellationToken()
    events = EventBus()

    if args.replay is not None:
        paths = sorted(
            path for path in args.replay.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
        )
        source = ReplayCaptureSource(paths)
        serial = "replay"
        connection_generation = lambda: 0
        max_frames = args.frames if args.frames is not None else len(paths)
    else:
        session = DeviceSession(args.device)
        source = ADBCaptureSource(session)
        serial = session.serial
        connection_generation = lambda: session.connection_generation
        max_frames = args.frames

    capture = CaptureManager(
        source,
        device_serial=serial,
        connection_generation=connection_generation,
    )
    runtime = BotRuntime(
        capture=capture,
        perception=LegacyVisionAdapter(),
        events=events,
        lifecycle=Lifecycle(),
        cancellation=cancellation,
        settings=RuntimeSettings(args.interval),
    )

    logger.warning("OBSERVE-ONLY: no taps or swipes can be sent by this runtime")
    try:
        processed = runtime.run(max_frames=max_frames)
    except KeyboardInterrupt:
        cancellation.cancel()
        return 130
    finally:
        for event in events.drain():
            logger.info("{} | {}", event.kind.value, dict(event.payload))
    logger.info("processed {} frames", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run runtime and CLI help tests**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\runtime\test_bot_runtime.py -v
.\.venv312\Scripts\python.exe -m src.main --help
```

Expected: runtime test PASS; CLI help lists the mutually exclusive `--device` and `--replay` modes and describes observe-only operation.

- [ ] **Step 7: Run one deterministic replay frame**

Run:

```powershell
.\.venv312\Scripts\python.exe -m src.main --replay screenshots --frames 1 --interval 0
```

Expected: exit code 0, one FRAME and one OBSERVATION event, and the warning that no tap or swipe can be sent.

- [ ] **Step 8: Commit the observe-only runtime and CLI**

```powershell
git add src/runtime src/vision/legacy_adapter.py src/main.py tests/runtime/test_bot_runtime.py
git commit -m "feat: add single-session observe-only runtime"
```

---

### Task 9: Rewire the GUI to the safe runtime and Tk-thread event polling

**Files:**
- Create: `src/gui/presenter.py`
- Create: `tests/gui/test_presenter.py`
- Modify: `src/gui/app.py`

- [ ] **Step 1: Write the failing presenter test**

```python
# tests/gui/test_presenter.py
from src.core.events import EventKind, RuntimeEvent
from src.gui.presenter import format_runtime_event


def test_observation_event_is_formatted_without_tk_dependency() -> None:
    event = RuntimeEvent(
        EventKind.OBSERVATION,
        1.0,
        {"frame_id": 7, "screen": "HOME", "confidence": 0.923, "sub_element": "battle"},
    )
    assert format_runtime_event(event) == "Tela: HOME | Confiança: 92% | Elemento: battle | Frame: 7"
```

- [ ] **Step 2: Run the presenter test and verify the module is missing**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\gui\test_presenter.py -v
```

Expected: FAIL because `src.gui.presenter` does not exist.

- [ ] **Step 3: Implement the pure GUI presenter**

```python
# src/gui/presenter.py
from src.core.events import EventKind, RuntimeEvent


def format_runtime_event(event: RuntimeEvent) -> str | None:
    if event.kind is not EventKind.OBSERVATION:
        return None
    confidence = float(event.payload.get("confidence", 0.0))
    return (
        f"Tela: {event.payload.get('screen', 'UNKNOWN')} | "
        f"Confiança: {confidence:.0%} | "
        f"Elemento: {event.payload.get('sub_element') or '-'} | "
        f"Frame: {event.payload.get('frame_id', '-')}"
    )
```

- [ ] **Step 4: Replace GUI worker ownership and remove the clicking loop**

In `DraftShowdownGUI.__init__`, add these fields after the existing state fields:

```python
self.runtime_events = EventBus()
self.cancellation: CancellationToken | None = None
```

Add imports:

```python
from src.capture.adb_source import ADBCaptureSource
from src.capture.manager import CaptureManager
from src.core.cancellation import CancellationToken
from src.core.events import EventBus, EventKind, RuntimeEvent
from src.core.lifecycle import Lifecycle
from src.device.session import DeviceSession
from src.gui.presenter import format_runtime_event
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings
from src.vision.legacy_adapter import LegacyVisionAdapter
```

Delete imports used only by the legacy GUI loop: `ADBCapture`, `VisionPipeline`, `StateManager`, `DraftEvaluator`, `ActionPlanner`, `ADBController`, and `Watchdog`.

Schedule event polling from `__init__`:

```python
self.after(100, self._process_runtime_events)
```

Replace `start_bot` with:

```python
def start_bot(self):
    if self.is_running:
        return

    serial = self.device_option.get().strip()
    if not serial or serial.startswith("Nenhum") or serial.startswith("ADB") or serial.startswith("Buscando"):
        logger.error("Selecione explicitamente um dispositivo ADB disponível.")
        return

    self.is_running = True
    self.is_paused = False
    self.stats = SessionStats()
    self.status_badge.configure(text="🟢 OBSERVANDO", fg_color="#2E7D32")
    self.btn_start.configure(state="disabled")
    self.btn_pause.configure(state="disabled", text="⏸ Pausar")
    self.btn_stop.configure(state="normal")
    self.bot_thread = threading.Thread(
        target=self._run_bot_loop,
        args=(serial,),
        daemon=True,
        name="draft-showdown-observer",
    )
    self.bot_thread.start()
```

Replace `stop_bot` with:

```python
def stop_bot(self):
    if not self.is_running:
        return
    self.is_running = False
    self.is_paused = False
    if self.cancellation is not None:
        self.cancellation.cancel()
    self.status_badge.configure(text="🔴 PARANDO", fg_color="#A91B0D")
    self.btn_start.configure(state="disabled")
    self.btn_pause.configure(state="disabled", text="⏸ Pausar")
    self.btn_stop.configure(state="disabled")
    logger.info("Parada cooperativa solicitada.")
```

Replace `_run_bot_loop` with:

```python
def _run_bot_loop(self, device_serial: Optional[str]):
    if not device_serial:
        logger.error("Selecione explicitamente um dispositivo ADB.")
        self.runtime_events.publish(
            RuntimeEvent(EventKind.ERROR, time.monotonic(), {"error": "missing device serial"})
        )
        return

    self.cancellation = CancellationToken()
    session = DeviceSession(device_serial)
    source = ADBCaptureSource(session)
    capture = CaptureManager(
        source,
        device_serial=session.serial,
        connection_generation=lambda: session.connection_generation,
    )
    runtime = BotRuntime(
        capture=capture,
        perception=LegacyVisionAdapter(),
        events=self.runtime_events,
        lifecycle=Lifecycle(),
        cancellation=self.cancellation,
        settings=RuntimeSettings(0.25),
    )
    logger.warning("GUI em modo SOMENTE OBSERVAÇÃO; nenhuma ação será enviada.")
    try:
        runtime.run()
    except Exception:
        logger.exception("Falha no runtime de observação")
```

Add the Tk-thread poller:

```python
def _process_runtime_events(self):
    for event in self.runtime_events.drain():
        text = format_runtime_event(event)
        if text is not None:
            self.lbl_current_state.configure(text=text)
        if event.kind is EventKind.LIFECYCLE and event.payload.get("status") == "stopped":
            self.is_running = False
            self.status_badge.configure(text="🔴 PARADO", fg_color="#A91B0D")
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled", text="⏸ Pausar")
            self.btn_stop.configure(state="disabled")
        if event.kind is EventKind.ERROR:
            logger.error("Runtime: {}", event.payload.get("error"))
            self.is_running = False
            self.status_badge.configure(text="🔴 FALHA", fg_color="#A91B0D")
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled", text="⏸ Pausar")
            self.btn_stop.configure(state="disabled")
    self.after(100, self._process_runtime_events)
```

Disable the pause button for this first foundation phase by leaving it disabled in `start_bot`; pause is reintroduced through lifecycle commands in the closed-loop runtime plan. Change the running badge text to `🟢 OBSERVANDO` so the GUI cannot imply active automation.

The worker must not call `configure`, read Tk variables, mutate session statistics, or instantiate any live input controller.

- [ ] **Step 5: Run presenter and source-level GUI safety checks**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\gui\test_presenter.py -v
rg -n "ADBController|controller\.execute|\.click\(|\.swipe\(|lbl_current_state\.configure" src\gui\app.py
```

Expected: presenter test PASS. `rg` finds `lbl_current_state.configure` only inside `_process_runtime_events`, which is scheduled by Tk; it finds no `ADBController`, `controller.execute`, direct click, or swipe in the GUI.

- [ ] **Step 6: Launch and close the GUI without starting the bot**

Run:

```powershell
.\.venv312\Scripts\python.exe src\gui\app.py
```

Expected: GUI opens, device selector populates, no bot starts automatically, and closing the window exits without a traceback.

- [ ] **Step 7: Commit the safe GUI adapter**

```powershell
git add src/gui/app.py src/gui/presenter.py tests/gui/test_presenter.py
git commit -m "refactor: route gui through observe-only runtime"
```

---

### Task 10: Migrate legacy tests, document actual capability, and verify the foundation

**Files:**
- Create: `tests/test_legacy_compatibility.py`
- Remove: `tests/offline_harness.py`
- Modify: `README.md`

- [ ] **Step 1: Create discoverable compatibility tests before removing the old harness**

```python
# tests/test_legacy_compatibility.py
import numpy as np

from src.actions.action_planner import ActionPlanner
from src.state.game_state import ScreenState
from src.state.state_manager import StateManager
from src.utils.coordinates import CoordinateConverter
from src.vision.pipeline import VisionPipeline


def test_coordinate_round_trip() -> None:
    normalized = CoordinateConverter.normalize(640, 360, 1280, 720)
    assert CoordinateConverter.denormalize(*normalized, 1280, 720) == (640, 360)


def test_legacy_fsm_requires_two_matching_observations() -> None:
    manager = StateManager(persistence_frames=2)
    observation = {"screen": ScreenState.HOME, "confidence": 0.9, "sub_element": "battle"}
    assert manager.update(observation).screen is ScreenState.UNKNOWN
    assert manager.update(observation).screen is ScreenState.HOME


def test_legacy_vision_returns_unknown_for_blank_frame() -> None:
    result = VisionPipeline(templates_dir="assets/templates").analyze(
        np.zeros((1280, 720, 3), dtype=np.uint8)
    )
    assert result["screen"] is ScreenState.UNKNOWN
    assert result["confidence"] == 0.0


def test_reward_policy_keeps_existing_user_choice() -> None:
    action = ActionPlanner().plan_handle_victory_summary(
        sub_element="timer_ad_btn",
        watch_ads=True,
    )
    assert "Continuar" in action.metadata
```

- [ ] **Step 2: Run both old and replacement tests before deletion**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest tests\offline_harness.py tests\test_legacy_compatibility.py -v
```

Expected: both suites PASS and the replacement covers the four legacy concerns with stricter vision behavior.

- [ ] **Step 3: Remove the undiscoverable harness and rewrite the README accurately**

Delete `tests/offline_harness.py` with `apply_patch` only after Step 2 passes.

Replace `README.md` with:

```markdown
# Draft Showdown Bot

Reliable visual automation for one Draft Showdown account running in one explicitly selected MEmu instance.

## Current capability

The current foundation is **observe-only**. It can capture native Android frames through ADB or replay recorded screenshots through the same runtime. It cannot send taps or swipes. Active automation remains disabled until perception, postcondition verification, and recovery pass their quality gates.

## Requirements

- Windows with MEmu and ADB enabled for live observation
- Python 3.12
- [uv](https://docs.astral.sh/uv/) for the reproducible environment

## Setup

```powershell
uv python install 3.12
uv venv .venv312 --python 3.12
uv pip install --python .venv312\Scripts\python.exe -e ".[dev]"
```

## Test

```powershell
.\.venv312\Scripts\python.exe -m pytest
```

## Replay one reference frame

```powershell
.\.venv312\Scripts\python.exe -m src.main --replay screenshots --frames 1 --interval 0
```

## Observe the selected MEmu device

```powershell
.\.venv312\Scripts\python.exe -m src.main --device 127.0.0.1:21503 --frames 10
```

## GUI

```powershell
.\.venv312\Scripts\python.exe src\gui\app.py
```

The GUI also runs in observe-only mode. Capture, state, and input architecture are documented in `docs/superpowers/specs/2026-08-13-draft-showdown-bot-architecture-design.md`.
```

- [ ] **Step 4: Run the complete automated suite and compilation check**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest
.\.venv312\Scripts\python.exe -m compileall -q src tests
```

Expected: pytest discovers all `test_*.py` files and all tests PASS; compileall exits with code 0.

- [ ] **Step 5: Run replay smoke validation**

Run:

```powershell
.\.venv312\Scripts\python.exe -m src.main --replay screenshots --frames 3 --interval 0
```

Expected: exit code 0; exactly three FRAME and three OBSERVATION events; zero INPUT events.

- [ ] **Step 6: Run read-only live MEmu validation**

Run:

```powershell
.\.venv312\Scripts\python.exe -m src.main --device 127.0.0.1:21503 --frames 3 --interval 0.25
```

Expected: exit code 0; native `720x1280` frame metadata; exactly three FRAME and three OBSERVATION events; zero INPUT events. Classification may remain UNKNOWN in this phase and is not a failure of the foundation.

- [ ] **Step 7: Review the final diff for accidental live-input paths**

Run:

```powershell
git diff --check
rg -n "ADBController|controller\.execute|device\.click|device\.swipe" src\main.py src\runtime src\gui
git status --short
```

Expected: `git diff --check` has no output; the safety search returns no live input path in the new runtime or entry points; status lists only intended files.

- [ ] **Step 8: Commit the verified observe-only foundation**

```powershell
git add README.md tests/test_legacy_compatibility.py tests/offline_harness.py
git commit -m "docs: document verified observe-only foundation"
```

## Completion checkpoint

This plan is complete only when:

- the supported Python 3.12 environment is reproducible without altering the old environment;
- plain `pytest` discovers and passes the complete suite;
- both CLI and GUI use the same `BotRuntime`;
- one explicit ADB serial is required for live mode;
- replay and live capture emit immutable, identified frames;
- no new runtime or entry-point path can instantiate or call live input;
- GUI updates occur only through events consumed on the Tk thread;
- replay and live smoke checks complete with zero INPUT events.

At this checkpoint, request code review before writing or executing the perception plan.
