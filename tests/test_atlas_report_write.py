from __future__ import annotations

from pathlib import Path

from reports.atlas_report.write import write_one_pager, write_report


def test_write_report_creates_dated_and_latest_files(tmp_path: Path) -> None:
    dated, latest = write_report("<html>oi</html>", tmp_path, "2026-07-14T00-00-00")

    assert dated.name == "atlas_report_2026-07-14T00-00-00.html"
    assert latest.name == "atlas_report_latest.html"
    assert dated.read_text(encoding="utf-8") == "<html>oi</html>"
    assert latest.read_text(encoding="utf-8") == "<html>oi</html>"


def test_write_report_overwrites_latest_on_subsequent_runs(tmp_path: Path) -> None:
    write_report("<html>primeiro</html>", tmp_path, "2026-07-14T00-00-00")
    _, latest = write_report("<html>segundo</html>", tmp_path, "2026-07-14T01-00-00")

    assert latest.read_text(encoding="utf-8") == "<html>segundo</html>"
    # O arquivo datado do primeiro run continua existindo (histórico).
    assert (tmp_path / "atlas_report_2026-07-14T00-00-00.html").exists()


def test_write_one_pager_names_file_by_symbol(tmp_path: Path) -> None:
    path = write_one_pager("<html>msft</html>", tmp_path, "msft", "2026-07-14T00-00-00")

    assert path.name == "atlas_report_MSFT_2026-07-14T00-00-00.html"
    assert path.read_text(encoding="utf-8") == "<html>msft</html>"
