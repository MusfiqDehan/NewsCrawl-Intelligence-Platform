"""Graceful shutdown: translate SIGTERM/SIGINT into a drain event.

Workers check `should_stop` between units of work (or await `wait()`),
finish in-flight items, release leases, and exit cleanly. A second signal
forces immediate exit.
"""

import asyncio
import signal
import sys

from newscrawl_api.observability import get_logger

log = get_logger("shutdown")


class GracefulShutdown:
    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._installed = False

    def install(self) -> None:
        """Install SIGTERM/SIGINT handlers on the running loop."""
        if self._installed:
            return
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._on_signal, sig)
        self._installed = True

    def _on_signal(self, sig: signal.Signals) -> None:
        if self._event.is_set():
            log.warning("forced_shutdown", signal=sig.name)
            sys.exit(1)
        log.info("graceful_shutdown_requested", signal=sig.name)
        self._event.set()

    def trigger(self) -> None:
        """Programmatic shutdown (e.g. a 'shutdown' control signal)."""
        self._event.set()

    @property
    def should_stop(self) -> bool:
        return self._event.is_set()

    async def wait(self, timeout: float | None = None) -> bool:  # noqa: ASYNC109 - deliberate poll-or-wait API
        """Wait until shutdown is requested (or timeout). Returns should_stop."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except TimeoutError:
            pass
        return self._event.is_set()
