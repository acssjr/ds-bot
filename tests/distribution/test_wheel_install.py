from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ROOT_BUILD_ARTIFACTS = ("build", "dist", "draft_showdown_bot.egg-info")


def _run(command: list[str], *, cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _venv_entrypoint(venv: Path) -> Path:
    return venv / (
        "Scripts/draft-showdown-bot.exe"
        if os.name == "nt"
        else "bin/draft-showdown-bot"
    )


def _artifact_snapshot(root: Path) -> tuple[tuple[object, ...], ...]:
    records: list[tuple[object, ...]] = []
    for name in ROOT_BUILD_ARTIFACTS:
        target = root / name
        if not target.exists():
            records.append((name, "missing"))
            continue
        entries = [target, *sorted(target.rglob("*"), key=lambda path: path.as_posix())]
        for entry in entries:
            stat = entry.stat()
            relative = entry.relative_to(root).as_posix()
            if entry.is_file():
                digest = hashlib.sha256(entry.read_bytes()).hexdigest()
                records.append(
                    (relative, "file", stat.st_mtime_ns, stat.st_size, digest)
                )
            elif entry.is_dir():
                records.append((relative, "directory", stat.st_mtime_ns))
            else:
                records.append((relative, "other", stat.st_mtime_ns, stat.st_size))
    return tuple(records)


def test_artifact_snapshot_preserves_preexisting_editable_metadata(
    tmp_path: Path,
) -> None:
    metadata = tmp_path / "draft_showdown_bot.egg-info"
    metadata.mkdir()
    package_info = metadata / "PKG-INFO"
    package_info.write_text("Version: 0.2.0\n", encoding="utf-8")

    before = _artifact_snapshot(tmp_path)

    assert before == _artifact_snapshot(tmp_path)
    package_info.write_text("Version: changed\n", encoding="utf-8")
    assert before != _artifact_snapshot(tmp_path)


def test_wheel_contains_resources_and_runs_external_replay(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv is required to verify the distribution"
    project_artifacts_before = _artifact_snapshot(PROJECT_ROOT)
    source_tree = tmp_path / "source"
    shutil.copytree(
        PROJECT_ROOT,
        source_tree,
        ignore=shutil.ignore_patterns(
            ".git",
            ".worktrees",
            ".venv",
            ".venv312",
            ".pytest_cache",
            ".hypothesis",
            "__pycache__",
            "*.pyc",
            "*.egg-info",
            "build",
            "dist",
            ".artifacts",
            "artifacts",
            "logs",
            "*.log",
        ),
    )
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()

    _run(
        [
            uv,
            "build",
            "--wheel",
            "--out-dir",
            str(wheel_dir),
            "--no-create-gitignore",
            str(source_tree),
        ],
        cwd=tmp_path,
    )
    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]

    expected_templates = {
        path.relative_to(source_tree).as_posix()
        for path in (source_tree / "assets/templates").rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    }
    assert expected_templates
    with zipfile.ZipFile(wheel) as archive:
        member_list = archive.namelist()
    members = set(member_list)
    assert len(member_list) == len(members)
    assert "assets/__init__.py" in members
    assert expected_templates <= members
    assert not any(member.startswith("screenshots/") for member in members)

    venv = tmp_path / "clean-venv"
    _run([uv, "venv", "--python", "3.12", str(venv)], cwd=tmp_path)
    python = _venv_python(venv)
    _run([uv, "pip", "install", "--python", str(python), str(wheel)], cwd=tmp_path)

    external_cwd = tmp_path / "outside"
    external_cwd.mkdir()
    initialized = _run(
        [
            str(python),
            "-I",
            "-c",
            (
                "import src; "
                "from src.vision.legacy_adapter import LegacyVisionAdapter; "
                "LegacyVisionAdapter(); print('wheel adapter OK')"
            ),
        ],
        cwd=external_cwd,
    )
    assert initialized.stdout.strip() == "wheel adapter OK"

    replayed = _run(
        [
            str(_venv_entrypoint(venv)),
            "--replay",
            str((source_tree / "screenshots").resolve()),
            "--frames",
            "1",
            "--interval",
            "0",
        ],
        cwd=external_cwd,
    )
    output = ANSI_ESCAPE.sub("", replayed.stdout + replayed.stderr)
    lines = output.splitlines()
    assert sum(" - frame | " in line for line in lines) == 1
    assert sum(" - observation | " in line for line in lines) == 1
    assert sum(" - input | " in line for line in lines) == 0
    assert _artifact_snapshot(PROJECT_ROOT) == project_artifacts_before
