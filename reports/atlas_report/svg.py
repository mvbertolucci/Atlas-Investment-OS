from __future__ import annotations


def sparkline_svg(values: list[float], *, width: int = 220, height: int = 40) -> str:
    """SVG inline simples -- sem JS, sem dependência externa."""
    if len(values) < 2:
        return '<p class="section-empty">Histórico insuficiente para gráfico.</p>'
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = width / (len(values) - 1)
    points = " ".join(
        f"{index * step:.1f},{height - ((value - low) / span * height):.1f}"
        for index, value in enumerate(values)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'role="img" aria-label="Histórico">'
        f'<polyline points="{points}" fill="none" stroke="currentColor" '
        'stroke-width="2" /></svg>'
    )
