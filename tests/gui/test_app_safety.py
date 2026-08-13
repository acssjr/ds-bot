from __future__ import annotations

import ast
import queue
from pathlib import Path

from src.gui.app import BoundedTextSink


APP_PATH = Path("src/gui/app.py")


def _tree() -> ast.Module:
    return ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"module-level function {name!r} not found")


def _method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return child
    raise AssertionError(f"method {class_name}.{method_name} not found")


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def test_gui_source_has_no_legacy_planner_or_live_input_path() -> None:
    tree = _tree()
    forbidden_names = {
        "ADBCapture",
        "StateManager",
        "DraftEvaluator",
        "ActionPlanner",
        "ADBController",
        "Watchdog",
    }
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert referenced_names.isdisjoint(forbidden_names)
    assert called_attributes.isdisjoint(
        {"click", "swipe", "execute", "stop_app", "start_app", "shell"}
    )


def test_observer_worker_is_tk_independent_and_uses_safe_runtime() -> None:
    worker = _function(_tree(), "run_observer_worker")
    names = {node.id for node in ast.walk(worker) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(worker) if isinstance(node, ast.Attribute)}

    assert "self" not in names
    assert {"BotRuntime", "DeviceSession", "ADBCaptureSource", "LegacyVisionAdapter"} <= names
    assert attributes.isdisjoint(
        {"configure", "get", "set", "insert", "see", "stats", "after", "destroy"}
    )


def test_session_runtime_primitives_are_created_before_thread_start() -> None:
    start = _method(_tree(), "DraftShowdownGUI", "start_observation")
    calls = [
        (_called_name(node), node.lineno)
        for node in ast.walk(start)
        if isinstance(node, ast.Call)
    ]

    token_line = min(line for name, line in calls if name == "CancellationToken")
    bus_line = min(line for name, line in calls if name == "EventBus")
    thread_line = min(line for name, line in calls if name == "_thread_factory")
    start_line = max(line for name, line in calls if name == "start")

    assert token_line < thread_line < start_line
    assert bus_line < thread_line < start_line


def test_device_discovery_uses_a_finite_socket_timeout_off_tk_path() -> None:
    discovery = _function(_tree(), "discover_adb_serials")
    calls = [node for node in ast.walk(discovery) if isinstance(node, ast.Call)]
    adb_client_calls = [call for call in calls if _called_name(call) == "AdbClient"]

    assert len(adb_client_calls) == 1
    timeout = next(
        keyword.value
        for keyword in adb_client_calls[0].keywords
        if keyword.arg == "socket_timeout"
    )
    assert isinstance(timeout, ast.Constant)
    assert isinstance(timeout.value, (int, float))
    assert 0 < timeout.value <= 10


def test_gui_copy_describes_observation_not_active_automation() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "OBSERVAÇÃO" in source
    assert "Iniciar Bot" not in source
    assert "RODANDO" not in source
    assert "Configurações & Ads" not in source


def test_gui_log_sink_is_bounded_and_keeps_the_latest_messages() -> None:
    messages: queue.Queue[str] = queue.Queue(maxsize=2)
    sink = BoundedTextSink(messages)

    sink.write("primeiro")
    sink.write("segundo")
    sink.write("terceiro")

    assert messages.qsize() == 2
    assert messages.get_nowait() == "segundo"
    assert messages.get_nowait() == "terceiro"
