from __future__ import annotations

from pathlib import Path


def write_report(
    html: str,
    output_dir: Path,
    date_stamp: str,
) -> tuple[Path, Path]:
    """
    Grava o relatório datado (atlas_report_<data>.html) e sobrescreve a
    cópia atlas_report_latest.html -- cópia simples, não symlink (ambiente
    Windows não garante privilégio para symlink).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dated_path = output_dir / f"atlas_report_{date_stamp}.html"
    latest_path = output_dir / "atlas_report_latest.html"
    dated_path.write_text(html, encoding="utf-8")
    latest_path.write_text(html, encoding="utf-8")
    return dated_path, latest_path


def write_one_pager(
    html: str,
    output_dir: Path,
    symbol: str,
    date_stamp: str,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"atlas_report_{symbol.strip().upper()}_{date_stamp}.html"
    path.write_text(html, encoding="utf-8")
    return path
