from importlib import import_module
from importlib.metadata import entry_points
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
