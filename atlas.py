"""
Atlas -- porta única (Fase 1 de usabilidade).

Um só ponto de entrada: roda o modo escolhido (ou nenhum) e já abre o visor no
navegador, para o usuário não precisar decorar flags nem caçar arquivo em
`output/relatorios/`. É um invólucro fino sobre o que já existe:

- `run_all.main(argv)` continua sendo o motor (mesmos modos --full/--portfolio/
  --ticker, mesmos contratos de saída);
- `api.server.serve` continua sendo o servidor local read-only (loopback).

Uso:
    python atlas.py                 menu interativo
    python atlas.py ver             só abre o visor do que já rodou
    python atlas.py hoje            atualiza a carteira e abre o cockpit
    python atlas.py full            atualização completa (com screener) e abre
    python atlas.py ticker MSFT     analisa um ticker e abre o one-pager

No Windows, `Atlas.bat` faz o mesmo com duplo-clique (ativa a venv antes).
"""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "output" / "relatorios"

MENU = """
=======================================
  Atlas Investment OS
=======================================
  1) Ver o que já rodou (abrir o visor)
  2) Atualizar carteira e abrir       (rápido)
  3) Atualização completa e abrir     (lento, com screener)
  4) Analisar um ticker
  5) Sair
"""


def _run_pipeline(argv: list[str]) -> None:
    """Roda o motor no mesmo processo, com os mesmos modos de sempre."""
    from run_all import main as run_main

    try:
        run_main(argv)
    except SystemExit:
        print(
            "\n[!] Execução interrompida pelo Health Check. "
            "Veja logs/atlas.log para a causa.\n"
        )
        raise


def _serve(open_path: str = "/") -> None:
    from api.server import serve

    print("\nAbrindo o visor no navegador. Ctrl+C aqui encerra o servidor.\n")
    serve(open_browser=True, open_path=open_path)


def _open_ticker(symbol: str) -> None:
    matches = sorted(REPORTS.glob(f"atlas_report_{symbol.upper()}_*.html"))
    if not matches:
        print(f"[!] One-pager de {symbol.upper()} não encontrado em {REPORTS}.")
        return
    latest = matches[-1]
    print(f"Abrindo {latest.name}")
    webbrowser.open(latest.as_uri())


def _menu() -> None:
    print(MENU)
    choice = input("Escolha [1-5]: ").strip()
    if choice == "1":
        _serve("/")
    elif choice == "2":
        _run_pipeline(["--portfolio"])
        _serve("/cockpit")
    elif choice == "3":
        _run_pipeline(["--full"])
        _serve("/cockpit")
    elif choice == "4":
        symbol = input("Ticker (ex.: MSFT): ").strip().upper()
        if symbol:
            _run_pipeline(["--ticker", symbol])
            _open_ticker(symbol)
    else:
        print("Até logo.")


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        _menu()
        return

    cmd = args[0].lower()
    if cmd in ("ver", "view", "serve"):
        _serve("/")
    elif cmd in ("hoje", "carteira", "portfolio"):
        _run_pipeline(["--portfolio"])
        _serve("/cockpit")
    elif cmd in ("full", "completo"):
        _run_pipeline(["--full"])
        _serve("/cockpit")
    elif cmd == "ticker":
        if len(args) < 2:
            print("Uso: python atlas.py ticker SYM")
            return
        symbol = args[1].strip().upper()
        _run_pipeline(["--ticker", symbol])
        _open_ticker(symbol)
    else:
        print(f"Comando desconhecido: {cmd!r}")
        print("Rode 'python atlas.py' para o menu, ou veja o cabeçalho do arquivo.")


if __name__ == "__main__":
    main()
