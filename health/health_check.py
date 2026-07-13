from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List


# ============================================================
# MODELOS
# ============================================================


@dataclass
class HealthItem:
    name: str
    success: bool
    message: str = ""


@dataclass
class HealthReport:
    items: List[HealthItem]

    @property
    def passed(self) -> int:
        return sum(item.success for item in self.items)

    @property
    def failed(self) -> int:
        return len(self.items) - self.passed

    @property
    def score(self) -> float:
        if not self.items:
            return 0.0

        return round(
            self.passed / len(self.items) * 100,
            1,
        )

    @property
    def ok(self) -> bool:
        return self.failed == 0


# ============================================================
# CHECKS
# ============================================================


def _check_file(path: Path) -> HealthItem:

    return HealthItem(
        name=path.name,
        success=path.exists(),
        message="" if path.exists() else f"Arquivo não encontrado: {path}",
    )


def _check_directory(path: Path) -> HealthItem:

    exists = path.exists()

    if exists:
        path.mkdir(parents=True, exist_ok=True)

    return HealthItem(
        name=f"{path.name}/",
        success=exists,
        message="" if exists else f"Pasta não encontrada: {path}",
    )


def _check_write_permission(directory: Path) -> HealthItem:

    try:

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        test_file = directory / ".atlas_write_test"

        test_file.write_text(
            "ok",
            encoding="utf-8",
        )

        test_file.unlink()

        return HealthItem(
            name="Write Permission",
            success=True,
        )

    except Exception as exc:

        return HealthItem(
            name="Write Permission",
            success=False,
            message=str(exc),
        )


def _check_sqlite(database: Path) -> HealthItem:

    try:

        database.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        connection = sqlite3.connect(database)

        connection.execute("SELECT 1")

        connection.close()

        return HealthItem(
            name="SQLite",
            success=True,
        )

    except Exception as exc:

        return HealthItem(
            name="SQLite",
            success=False,
            message=str(exc),
        )


def _check_disk_space(path: Path) -> HealthItem:

    try:

        usage = os.statvfs(path)

        free = usage.f_bavail * usage.f_frsize

        free_gb = free / 1024**3

        success = free_gb >= 1.0

        return HealthItem(
            name="Disk Space",
            success=success,
            message=f"{free_gb:.1f} GB livres",
        )

    except AttributeError:
        #
        # Windows
        #
        import shutil

        total, used, free = shutil.disk_usage(path)

        free_gb = free / 1024**3

        success = free_gb >= 1.0

        return HealthItem(
            name="Disk Space",
            success=success,
            message=f"{free_gb:.1f} GB livres",
        )

    except Exception as exc:

        return HealthItem(
            name="Disk Space",
            success=False,
            message=str(exc),
        )


# ============================================================
# EXECUÇÃO
# ============================================================


def run_health_check(
    root: Path,
) -> HealthReport:

    config = root / "config"

    output = root / "output"

    logs = root / "logs"

    data = root / "data"

    items: list[HealthItem] = []

    #
    # Config
    #

    items.append(
        _check_file(
            config / "settings.json"
        )
    )

    items.append(
        _check_file(
            config / "weights.json"
        )
    )

    items.append(
        _check_file(
            config / "deal_breakers.json"
        )
    )

    items.append(
        _check_file(
            config / "watchlist.csv"
        )
    )

    #
    # Diretórios
    #

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    logs.mkdir(
        parents=True,
        exist_ok=True,
    )

    data.mkdir(
        parents=True,
        exist_ok=True,
    )

    items.append(
        _check_directory(output)
    )

    items.append(
        _check_directory(logs)
    )

    items.append(
        _check_directory(data)
    )

    #
    # SQLite
    #

    items.append(
        _check_sqlite(
            data / "atlas_history.db"
        )
    )

    #
    # Escrita
    #

    items.append(
        _check_write_permission(
            output
        )
    )

    #
    # Disco
    #

    items.append(
        _check_disk_space(root)
    )

    return HealthReport(items)


# ============================================================
# TERMINAL
# ============================================================


def print_health_report(
    report: HealthReport,
) -> None:

    print()

    print("=" * 70)

    print("ATLAS HEALTH CHECK")

    print("=" * 70)

    print()

    for item in report.items:

        # Keep terminal output compatible with Windows consoles whose active
        # code page cannot encode Unicode status symbols.
        icon = "[OK]" if item.success else "[FAIL]"

        print(
            f"{icon} {item.name}"
        )

        if item.message:

            print(
                f"    {item.message}"
            )

    print()

    print(
        f"Health Score : {report.score:.1f}%"
    )

    print(
        f"Passed       : {report.passed}"
    )

    print(
        f"Failed       : {report.failed}"
    )

    print()

    if report.ok:

        print("Environment Ready.")

    else:

        print("Environment NOT Ready.")

        raise SystemExit(1)
