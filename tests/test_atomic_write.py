from __future__ import annotations

import json
from pathlib import Path

import pytest

from storage.atomic_write import atomic_write_json, replace_with_retry


def test_replace_with_retry_recovers_from_transient_permission_error(
    tmp_path: Path,
) -> None:
    temporary = tmp_path / "file.json.tmp"
    target = tmp_path / "file.json"
    temporary.write_text("{}", encoding="utf-8")
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(path: Path, destination: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("OneDrive lock")
        return original_replace(path, destination)

    sleeps: list[float] = []
    Path.replace = flaky_replace  # type: ignore[assignment]
    try:
        replace_with_retry(
            temporary, target, retry_delay=0, sleeper=sleeps.append
        )
    finally:
        Path.replace = original_replace  # type: ignore[assignment]

    assert attempts == 3
    assert sleeps == [0, 0]
    assert target.exists()


def test_replace_with_retry_reraises_after_exhausting_attempts(
    tmp_path: Path,
) -> None:
    temporary = tmp_path / "file.json.tmp"
    target = tmp_path / "file.json"
    temporary.write_text("{}", encoding="utf-8")

    def always_locked(path: Path, destination: Path) -> Path:
        raise PermissionError("OneDrive lock")

    original_replace = Path.replace
    Path.replace = always_locked  # type: ignore[assignment]
    try:
        with pytest.raises(PermissionError):
            replace_with_retry(
                temporary,
                target,
                replace_attempts=2,
                retry_delay=0,
                sleeper=lambda _delay: None,
            )
    finally:
        Path.replace = original_replace  # type: ignore[assignment]


def test_replace_with_retry_never_swallows_other_errors(tmp_path: Path) -> None:
    temporary = tmp_path / "file.json.tmp"
    target = tmp_path / "file.json"
    temporary.write_text("{}", encoding="utf-8")

    def not_found(path: Path, destination: Path) -> Path:
        raise FileNotFoundError("gone")

    original_replace = Path.replace
    Path.replace = not_found  # type: ignore[assignment]
    try:
        with pytest.raises(FileNotFoundError):
            replace_with_retry(temporary, target, sleeper=lambda _delay: None)
    finally:
        Path.replace = original_replace  # type: ignore[assignment]


def test_replace_with_retry_rejects_nonpositive_attempts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="replace_attempts"):
        replace_with_retry(
            tmp_path / "a.tmp", tmp_path / "a", replace_attempts=0
        )


def test_atomic_write_json_round_trips_and_preserves_dumps_kwargs(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "out.json"

    result = atomic_write_json(
        path, {"b": 1, "a": 2}, indent=2, sort_keys=True
    )

    assert result == path
    assert not path.with_suffix(".json.tmp").exists()
    text = path.read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')  # sort_keys respected
    assert json.loads(text) == {"a": 2, "b": 1}


def test_atomic_write_json_retries_transient_permission_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "out.json"
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(this: Path, destination: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise PermissionError("OneDrive lock")
        return original_replace(this, destination)

    Path.replace = flaky_replace  # type: ignore[assignment]
    try:
        atomic_write_json(
            path, {"x": 1}, retry_delay=0, sleeper=lambda _delay: None
        )
    finally:
        Path.replace = original_replace  # type: ignore[assignment]

    assert attempts == 2
    assert json.loads(path.read_text(encoding="utf-8")) == {"x": 1}
