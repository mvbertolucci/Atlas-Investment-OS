from __future__ import annotations

from pathlib import Path

import pytest

from health.health_check import (
    HealthItem,
    HealthReport,
    _check_directory,
    _check_disk_space,
    _check_file,
    _check_sqlite,
    _check_write_permission,
    print_health_report,
    run_health_check,
)


def _create_config(root: Path) -> None:
    config = root / "config"
    config.mkdir()
    for name in (
        "settings.json",
        "weights.json",
        "deal_breakers.json",
        "watchlist.csv",
    ):
        (config / name).write_text("{}", encoding="utf-8")


def test_health_report_aggregates_results() -> None:
    report = HealthReport(
        [
            HealthItem("one", True),
            HealthItem("two", False, "failed"),
        ]
    )

    assert report.passed == 1
    assert report.failed == 1
    assert report.score == 50.0
    assert report.ok is False
    assert HealthReport([]).score == 0.0


def test_file_and_directory_checks(tmp_path: Path) -> None:
    existing_file = tmp_path / "present.json"
    existing_file.write_text("{}", encoding="utf-8")
    existing_directory = tmp_path / "present"
    existing_directory.mkdir()

    assert _check_file(existing_file).success is True
    missing_file = _check_file(tmp_path / "missing.json")
    assert missing_file.success is False
    assert "Arquivo não encontrado" in missing_file.message

    assert _check_directory(existing_directory).success is True
    missing_directory = _check_directory(tmp_path / "missing")
    assert missing_directory.success is False
    assert "Pasta não encontrada" in missing_directory.message


def test_write_permission_and_sqlite_checks(tmp_path: Path) -> None:
    write = _check_write_permission(tmp_path / "output")
    sqlite = _check_sqlite(tmp_path / "data" / "history.db")

    assert write.success is True
    assert not (tmp_path / "output" / ".atlas_write_test").exists()
    assert sqlite.success is True
    assert (tmp_path / "data" / "history.db").exists()


def test_check_failures_are_reported(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_mkdir(*args, **kwargs):
        raise PermissionError("blocked")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    write = _check_write_permission(tmp_path / "output")
    sqlite = _check_sqlite(tmp_path / "data" / "history.db")

    assert write.success is False
    assert "blocked" in write.message
    assert sqlite.success is False
    assert "blocked" in sqlite.message


def test_disk_space_success_and_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class Usage:
        f_bavail = 2
        f_frsize = 1024**3

    monkeypatch.setattr(
        "health.health_check.os.statvfs",
        lambda path: Usage(),
        raising=False,
    )
    assert _check_disk_space(tmp_path).success is True

    def fail(path):
        raise OSError("disk unavailable")

    monkeypatch.setattr(
        "health.health_check.os.statvfs",
        fail,
        raising=False,
    )
    result = _check_disk_space(tmp_path)
    assert result.success is False
    assert "disk unavailable" in result.message


def test_disk_space_uses_windows_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def unavailable(path):
        raise AttributeError("statvfs unavailable")

    monkeypatch.setattr(
        "health.health_check.os.statvfs",
        unavailable,
        raising=False,
    )
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda path: (10 * 1024**3, 9 * 1024**3, 1024**3),
    )

    result = _check_disk_space(tmp_path)

    assert result.success is True
    assert result.message == "1.0 GB livres"


def test_run_health_check_builds_operational_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _create_config(tmp_path)
    monkeypatch.setattr(
        "health.health_check._check_disk_space",
        lambda path: HealthItem("Disk Space", True, "10 GB livres"),
    )

    report = run_health_check(tmp_path)

    assert report.ok is True
    assert report.passed == 10
    assert (tmp_path / "output").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "data" / "atlas_history.db").exists()


def test_print_health_report_success_and_failure(capsys) -> None:
    print_health_report(
        HealthReport([HealthItem("ready", True)])
    )
    success_output = capsys.readouterr().out
    assert "[OK] ready" in success_output
    assert "Environment Ready." in success_output
    assert "Health Score : 100.0%" in success_output

    with pytest.raises(SystemExit):
        print_health_report(
            HealthReport(
                [HealthItem("broken", False, "reason")]
            )
        )
    failure_output = capsys.readouterr().out
    assert "[FAIL] broken" in failure_output
    assert "Environment NOT Ready." in failure_output
    assert "reason" in failure_output
