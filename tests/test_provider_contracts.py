from __future__ import annotations

import threading

import pytest

from providers.contracts import (
    ProviderClient,
    ProviderError,
    ProviderErrorKind,
    ProviderPolicy,
)


def test_provider_retries_transient_failure_and_returns_value() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("provider unavailable")
        return "ok"

    client = ProviderClient(
        "Test",
        ProviderPolicy(max_retries=2, backoff_seconds=0.25, rate_limit_per_second=1000),
        sleeper=sleeps.append,
    )

    assert client.execute("fetch", operation) == "ok"
    assert attempts == 3
    assert 0.25 in sleeps
    assert 0.5 in sleeps


def test_provider_non_retryable_error_is_typed() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("404 delisted")

    client = ProviderClient(
        "Test",
        ProviderPolicy(max_retries=3, rate_limit_per_second=1000),
    )
    with pytest.raises(ProviderError) as captured:
        client.execute("fetch", operation)

    assert calls == 1
    assert captured.value.kind == ProviderErrorKind.NOT_FOUND
    assert captured.value.retryable is False
    assert captured.value.attempts == 1


def test_provider_timeout_is_typed_and_bounded() -> None:
    release = threading.Event()
    client = ProviderClient(
        "Test",
        ProviderPolicy(timeout_seconds=0.01, max_retries=0, rate_limit_per_second=1000),
    )
    try:
        with pytest.raises(ProviderError) as captured:
            client.execute("slow", lambda: release.wait(0.2))
        assert captured.value.kind == ProviderErrorKind.TIMEOUT
        assert captured.value.retryable is True
    finally:
        release.set()


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"timeout_seconds": 0}, "timeout"),
        ({"max_retries": -1}, "max_retries"),
        ({"backoff_seconds": -1}, "backoff"),
        ({"rate_limit_per_second": 0}, "rate_limit"),
    ],
)
def test_provider_policy_rejects_invalid_values(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        ProviderPolicy(**kwargs)
