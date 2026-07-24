"""
Disparo de execução a partir do visor local -- uma run por vez.

Até aqui o visor era estritamente read-only e a atualização vivia do outro
lado da costura: no menu do `Atlas.bat`/`atlas.py`. A página inicial apenas
imprimia o comando para copiar. Este módulo fecha essa costura expondo os
MESMOS dois modos que o menu já oferece (`--portfolio` e `--full`), sem
inventar um terceiro caminho de execução.

Três invariantes, nesta ordem de importância:

1. **Uma run por vez.** Duas execuções simultâneas escreveriam ao mesmo tempo
   em `data/atlas_history.db` e `output/dados/dashboard.json`. A trava é o
   requisito central, não um refinamento: sem ela, um duplo-clique no botão
   corrompe o histórico.
2. **Modo vem de allowlist.** O cliente escolhe uma chave (`portfolio` |
   `full`); os argumentos do pipeline são montados aqui. Nada que venha do
   HTTP chega a `run_all` como argumento.
3. **Local por construção.** Quem decide se a rota existe é o servidor
   (`serve(allow_run=...)`), e a Fase 2 (visor hospedado) a desliga: lá não
   há motor do outro lado, e uma rota de execução exposta na rede é outro
   problema inteiramente.

O módulo não sabe o que é HTTP: devolve status e dicionários, e o servidor
adapta. Isso o torna testável sem subir porta.
"""
from __future__ import annotations

import threading
import traceback
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

# Allowlist: rótulo humano e os argumentos exatos de `run_all.main`. São os
# mesmos do menu (`atlas.py`), para não existirem dois contratos de execução.
RUN_MODES: dict[str, tuple[str, tuple[str, ...]]] = {
    "portfolio": ("Carteira e watchlist", ("--portfolio",)),
    "full": ("Completo, com screener", ("--full",)),
}

IDLE = "idle"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


def _default_execute(argv: Sequence[str]) -> None:
    """Roda o motor de sempre, no mesmo processo (como faz `atlas.py`)."""
    from run_all import main as run_main

    run_main(list(argv))


class PipelineRunner:
    """Estado de execução do pipeline, consultável e disparável.

    Um único objeto vive no processo do servidor. `start` devolve (status
    HTTP, payload) para o adaptador não precisar traduzir exceção em código.
    """

    def __init__(self, execute: Callable[[Sequence[str]], None] | None = None) -> None:
        self._execute = execute or _default_execute
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: dict[str, Any] = {
            "state": IDLE,
            "mode": None,
            "label": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
        }

    # -- leitura ---------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            snapshot = dict(self._state)
        snapshot["modes"] = {
            key: label for key, (label, _) in RUN_MODES.items()
        }
        return snapshot

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._state["state"] == RUNNING

    # -- escrita ---------------------------------------------------------

    def start(self, mode: object) -> tuple[int, dict[str, Any]]:
        key = str(mode or "").strip().lower()
        if key not in RUN_MODES:
            return 400, {
                "error": "modo inválido.",
                "accepted": sorted(RUN_MODES),
            }
        label, argv = RUN_MODES[key]

        with self._lock:
            if self._state["state"] == RUNNING:
                return 409, {
                    "error": "já existe uma execução em andamento.",
                    "running": dict(self._state),
                }
            self._state = {
                "state": RUNNING,
                "mode": key,
                "label": label,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": None,
                "error": None,
            }
            thread = threading.Thread(
                target=self._run, args=(argv,), name=f"atlas-run-{key}", daemon=True
            )
            self._thread = thread
        thread.start()
        return 202, self.status()

    def _run(self, argv: Sequence[str]) -> None:
        error: str | None = None
        try:
            self._execute(argv)
        except SystemExit:
            # O Health Check aborta com SystemExit; para o visor isso é uma
            # falha com causa nos logs, não um encerramento do servidor.
            error = (
                "execução interrompida pelo Health Check. "
                "Veja logs/atlas.log para a causa."
            )
        except BaseException as exc:  # noqa: BLE001 -- a trava não pode vazar
            error = f"{type(exc).__name__}: {exc}".strip()
            traceback.print_exc()
        finally:
            with self._lock:
                self._state["state"] = FAILED if error else DONE
                self._state["finished_at"] = datetime.now().isoformat(
                    timespec="seconds"
                )
                self._state["error"] = error
                self._thread = None

    def join(self, timeout: float | None = None) -> None:
        """Espera a run corrente terminar. Existe para os testes."""
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout)


RUNNER = PipelineRunner()
