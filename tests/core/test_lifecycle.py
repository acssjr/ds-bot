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


def test_lifecycle_rejects_raw_string_without_changing_state() -> None:
    lifecycle = Lifecycle()
    with pytest.raises(TypeError, match="RuntimeStatus"):
        lifecycle.transition("starting")
    assert lifecycle.status is RuntimeStatus.STOPPED
