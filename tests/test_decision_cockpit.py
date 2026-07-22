from __future__ import annotations

from pathlib import Path

import pytest

from decision.cockpit import render_decision_cockpit, write_decision_cockpit
from decision.queue import build_decision_queue


def _queue():
    return build_decision_queue(
        priority={
            "sell": {
                "items": [
                    {
                        "symbol": "<FMC>",
                        "action": "SELL",
                        "reason": "distress & risco",
                        "priority": 0,
                    }
                ]
            }
        },
        active_watchlist=(
            {
                "symbol": "KGC",
                "effective_state": "promotion_ready",
                "state_reason": "gatilho",
                "analytical_origin": "adr",
            },
        ),
        generated_at="2026-07-22T15:00:00",
    )


def test_renders_responsive_cockpit_and_escapes_content() -> None:
    html = render_decision_cockpit(_queue())
    assert "Atlas Decision Cockpit" in html
    assert 'name="viewport"' in html
    assert "@media(max-width:800px)" in html
    assert "&lt;FMC&gt;" in html
    assert "distress &amp; risco" in html
    assert "REVIEW_FOR_PURCHASE" in html
    assert "Nenhum item nesta fila." in html


def test_write_is_atomic_and_validates_type(tmp_path: Path) -> None:
    output = write_decision_cockpit(_queue(), tmp_path / "reports" / "cockpit.html")
    assert output.exists()
    assert not output.with_suffix(".html.tmp").exists()
    with pytest.raises(TypeError):
        render_decision_cockpit(object())
