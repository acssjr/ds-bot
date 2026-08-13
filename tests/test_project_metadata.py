import os
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_matches_supported_runtime() -> None:
    metadata = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = metadata["project"]
    pytest_options = metadata["tool"]["pytest"]["ini_options"]

    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["description"] == (
        "Observe-first visual foundation with bounded ad recovery for Draft Showdown"
    )
    assert any(item.startswith("customtkinter") for item in project["dependencies"])
    assert pytest_options["testpaths"] == ["tests"]
    assert pytest_options["python_files"] == ["test_*.py"]
    assert (PROJECT_ROOT / "src/__init__.py").is_file()


def test_setuptools_explicitly_discovers_src_namespace_packages() -> None:
    metadata = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    package_find = metadata["tool"]["setuptools"]["packages"]["find"]

    assert package_find == {
        "where": ["."],
        "include": ["src", "src.*", "assets"],
        "namespaces": True,
    }
    assert metadata["tool"]["setuptools"]["package-data"]["assets"] == [
        "templates/*.json",
        "templates/*.png",
        "templates/*.jpg",
        "templates/*.jpeg",
        "templates/**/*.png",
        "templates/**/*.jpg",
        "templates/**/*.jpeg",
    ]
    assert (PROJECT_ROOT / "assets/__init__.py").is_file()


def test_configured_console_script_resolves_to_a_callable() -> None:
    metadata = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    entry_value = metadata["project"]["scripts"]["draft-showdown-bot"]

    assert entry_value == "src.main:main"

    module_name, attribute_name = entry_value.split(":", maxsplit=1)
    module = import_module(module_name)
    target = getattr(module, attribute_name)

    assert callable(target)


def _isolated_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def test_current_python_imports_install_outside_repository(tmp_path: Path) -> None:
    imports = (
        "import importlib; "
        "modules = ('src', 'src.main', 'src.actions.action_planner', "
        "'src.capture.models', 'src.controllers.base_controller', "
        "'src.core.events', 'src.device.session', 'src.geometry.mapper', "
        "'src.gui.presenter', 'src.input.dry_run', 'src.runtime.bot_runtime', "
        "'src.state.game_state', 'src.strategy.draft_evaluator', "
        "'src.utils.coordinates', 'src.vision.classifiers.screen_classifier'); "
        "[importlib.import_module(name) for name in modules]; "
        "print('external imports OK')"
    )

    imported = subprocess.run(
        [str(Path(sys.executable).resolve()), "-I", "-c", imports],
        cwd=tmp_path,
        env=_isolated_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr
    assert imported.stdout.strip() == "external imports OK"


def test_installed_console_script_works_outside_repository(tmp_path: Path) -> None:
    matches = [
        entry
        for entry in entry_points(group="console_scripts")
        if entry.name == "draft-showdown-bot"
    ]
    if not matches:
        pytest.skip("current runner has no installed draft-showdown-bot metadata")
    assert len(matches) == 1
    assert matches[0].value == "src.main:main"

    scripts_dir = Path(sys.executable).resolve().parent
    entrypoint = scripts_dir / (
        "draft-showdown-bot.exe" if os.name == "nt" else "draft-showdown-bot"
    )
    if not entrypoint.is_file():
        pytest.skip("current runner has metadata but no installed console launcher")

    helped = subprocess.run(
        [str(entrypoint), "--help"],
        cwd=tmp_path,
        env=_isolated_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert helped.returncode == 0, helped.stdout + helped.stderr
    assert "Draft Showdown observe-only runtime" in helped.stdout
