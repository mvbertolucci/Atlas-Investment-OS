from __future__ import annotations

import concurrent.futures
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ProviderErrorKind(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    NOT_FOUND = "not_found"
    AUTHENTICATION = "authentication"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


class ProviderError(RuntimeError):
    def __init__(
        self,
        provider: str,
        operation: str,
        kind: ProviderErrorKind,
        message: str,
        *,
        retryable: bool,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.provider = str(provider).strip() or "unknown"
        self.operation = str(operation).strip() or "unknown"
        self.kind = ProviderErrorKind(kind)
        self.retryable = bool(retryable)
        self.attempts = max(1, int(attempts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "kind": self.kind.value,
            "message": str(self),
            "retryable": self.retryable,
            "attempts": self.attempts,
        }


@dataclass(frozen=True)
class ProviderPolicy:
    timeout_seconds: float = 30.0
    max_retries: int = 2
    backoff_seconds: float = 0.5
    rate_limit_per_second: float = 2.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo.")
        if self.max_retries < 0:
            raise ValueError("max_retries não pode ser negativo.")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds não pode ser negativo.")
        if self.rate_limit_per_second <= 0:
            raise ValueError("rate_limit_per_second deve ser positivo.")


def classify_provider_error(
    provider: str,
    operation: str,
    error: BaseException,
) -> ProviderError:
    if isinstance(error, ProviderError):
        return error
    message = str(error) or type(error).__name__
    lowered = message.casefold()
    if isinstance(error, (TimeoutError, concurrent.futures.TimeoutError)):
        kind, retryable = ProviderErrorKind.TIMEOUT, True
    elif "429" in lowered or "rate limit" in lowered or "too many" in lowered:
        kind, retryable = ProviderErrorKind.RATE_LIMITED, True
    elif "401" in lowered or "403" in lowered or "auth" in lowered:
        kind, retryable = ProviderErrorKind.AUTHENTICATION, False
    elif "404" in lowered or "not found" in lowered or "delisted" in lowered:
        kind, retryable = ProviderErrorKind.NOT_FOUND, False
    elif isinstance(error, (TypeError, ValueError, KeyError)):
        kind, retryable = ProviderErrorKind.INVALID_RESPONSE, False
    else:
        kind, retryable = ProviderErrorKind.UNAVAILABLE, True
    return ProviderError(
        provider,
        operation,
        kind,
        message,
        retryable=retryable,
    )


class ProviderClient:
    """Uniform boundary for provider calls with bounded, typed failure."""

    def __init__(
        self,
        provider: str,
        policy: ProviderPolicy | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider = str(provider).strip() or "unknown"
        self.policy = policy or ProviderPolicy()
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._last_started_at: float | None = None

    def _wait_for_rate_limit(self) -> None:
        minimum_interval = 1.0 / self.policy.rate_limit_per_second
        with self._lock:
            now = self._monotonic()
            if self._last_started_at is not None:
                wait = minimum_interval - (now - self._last_started_at)
                if wait > 0:
                    self._sleeper(wait)
                    now = self._monotonic()
            self._last_started_at = now

    def _call_with_timeout(
        self,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(operation, *args, **kwargs)
        try:
            return future.result(timeout=self.policy.timeout_seconds)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def execute(
        self,
        operation_name: str,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        last_error: ProviderError | None = None
        for attempt in range(1, self.policy.max_retries + 2):
            self._wait_for_rate_limit()
            try:
                return self._call_with_timeout(operation, *args, **kwargs)
            except Exception as error:
                typed = classify_provider_error(
                    self.provider,
                    operation_name,
                    error,
                )
                typed.attempts = attempt
                last_error = typed
                if not typed.retryable or attempt > self.policy.max_retries:
                    raise typed from error
                self._sleeper(
                    self.policy.backoff_seconds * (2 ** (attempt - 1))
                )
        assert last_error is not None
        raise last_error
