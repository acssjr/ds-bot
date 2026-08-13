import pytest

from src.core.cancellation import Cancelled, CancellationToken


def test_cancelled_wait_raises_without_sleeping() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Cancelled):
        token.wait(30.0)
