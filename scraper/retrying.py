from __future__ import annotations

import random
import time
from typing import Any, Callable

from loguru import logger
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential


def random_delay(min_delay: float, max_delay: float) -> None:
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)


def retry_with_backoff(
    *,
    max_retries: int,
    min_delay: float,
    max_delay: float,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def _before_sleep(retry_state: RetryCallState) -> None:
        random_delay(min_delay, max_delay)
        err = retry_state.outcome.exception() if retry_state.outcome else None
        logger.warning(
            "Retrying {} attempt {}/{} due to {}",
            retry_state.fn.__name__ if retry_state.fn else "unknown_fn",
            retry_state.attempt_number,
            max_retries,
            err,
        )

    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=_before_sleep,
        reraise=True,
    )

