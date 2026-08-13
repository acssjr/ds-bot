import math

import pytest

from src.core.cancellation import Cancelled, CancellationToken


def test_cancelled_wait_raises_without_sleeping() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Cancelled):
        token.wait(30.0)


@pytest.mark.parametrize("timeout", [True, math.nan, math.inf, -1.0, object()])
def test_wait_rejects_invalid_timeout(timeout) -> None:
    token = CancellationToken()
    with pytest.raises((TypeError, ValueError), match="timeout"):
        token.wait(timeout)
