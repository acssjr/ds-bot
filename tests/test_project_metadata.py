import os
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path
import subprocess
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_matches_supported_runtime() -> None:
    metadata = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = metadata["project"]
    pytest_options = metadata["tool"]["pytest"]["ini_options"]

    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["description"] == "Observe-only visual foundation for Draft Showdown"
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
        "include": ["src", "src.*"],
        "namespaces": True,
    }


def test_console_script_resolves_to_a_callable() -> None:
    matches = [
        entry
        for entry in entry_points(group="console_scripts")
        if entry.name == "draft-showdown-bot"
    ]

    assert len(matches) == 1
    entry = matches[0]
    assert entry.value == "src.main:main"

    module_name, attribute_name = entry.value.split(":", maxsplit=1)
    module = import_module(module_name)
    target = getattr(module, attribute_name)

    assert callable(target)


def test_editable_install_imports_and_entrypoint_work_outside_repository(
    tmp_path: Path,
) -> None:
    scripts_dir = PROJECT_ROOT / ".venv312" / (
        "Scripts" if os.name == "nt" else "bin"
    )
    python = scripts_dir / ("python.exe" if os.name == "nt" else "python")
    entrypoint = scripts_dir / (
        "draft-showdown-bot.exe" if os.name == "nt" else "draft-showdown-bot"
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
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
        [str(python), "-I", "-c", imports],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr
    assert imported.stdout.strip() == "external imports OK"

    helped = subprocess.run(
        [str(entrypoint), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert helped.returncode == 0, helped.stdout + helped.stderr
    assert "Draft Showdown observe-only runtime" in helped.stdout
