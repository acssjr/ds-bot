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
