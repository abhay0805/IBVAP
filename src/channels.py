"""Alert notification channels for the IBVAP platform.

A :class:`SecurityAlert` produced by the alert engine is fanned out to one
or more sinks. Each sink implements the :class:`AlertChannel` protocol:

* :class:`ConsoleChannel`  - structured, human-readable console output
* :class:`JsonChannel`     - append to a JSON array file (alerts/events feed)
* :class:`WebhookChannel`  - async HTTP(S) delivery with retry and backoff,
  sized to be usable from a remote border post with intermittent links
* :class:`LogChannel`      - routed through the standard :mod:`logging` API

The webhook sink runs on a dedicated background thread with a bounded
queue, so slow or unresponsive endpoints can never block the live
detection loop.
"""

from __future__ import annotations

import io
import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.request
from queue import Empty, Full, Queue
from pathlib import Path
from typing import Protocol

from models import SecurityAlert

Logger = logging.Logger


class AlertChannel(Protocol):
    """Common interface every notification sink implements."""

    def send(self, alert: SecurityAlert) -> None: ...

    def close(self) -> None: ...


class LogChannel:
    """Dispatch alerts through the standard logging framework."""

    def __init__(self, logger: Logger, level: int = logging.WARNING) -> None:
        self._log = logger.getChild("alerts")
        self._level = level

    def send(self, alert: SecurityAlert) -> None:
        self._log.log(
            self._level,
            "[%s] %s | %s | track %s @ %s frame %d",
            alert.alert_id,
            alert.severity.value,
            alert.message,
            alert.track_id,
            alert.camera_id,
            alert.frame_number,
        )

    def close(self) -> None:
        return None


class ConsoleChannel:
    """Print a structured, ASCII-safe alert block to the console.

    ASCII-safe by design: emoji and box-drawing characters render
    inconsistently across Windows consoles, so a border watch-post terminal
    cannot garble a critical alert.
    """

    def __init__(self, stream: io.TextIOBase | None = None) -> None:
        self._stream = stream

    def send(self, alert: SecurityAlert) -> None:
        width = 62
        rule = "-" * width
        lines = [
            rule,
            "  SECURITY ALERT",
            rule,
            f"  Alert     : {alert.alert_id}",
            f"  Severity  : {alert.severity.value}",
            f"  Event     : {alert.event_id or '-'}",
            f"  Type      : {alert.event_type.value}",
            f"  Object    : {alert.object_type}",
            f"  Track     : {alert.track_id}",
            f"  Camera    : {alert.camera_id}",
            f"  Time      : {alert.timestamp.isoformat(timespec='seconds')}",
            f"  Frame     : {alert.frame_number}",
            f"  Message   : {alert.message}",
            f"  Evidence  : {alert.evidence_path or 'capturing...'}",
            rule,
        ]
        text = "\n".join(lines)
        if self._stream is not None:
            print(text, file=self._stream, flush=True)
        else:
            print(text, flush=True)

    def close(self) -> None:
        return None


class JsonChannel:
    """Persist an ordered JSON array of records to a file.

    The file is rewritten atomically (temp file + rename) so a power-cut
    mid-write cannot corrupt the alert log. Guarded by a lock so it is safe
    to share between threads.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._items: list[dict] = self._load_existing()

    def _load_existing(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, OSError):
            return []

    def append(self, record: dict) -> None:
        with self._lock:
            self._items.append(record)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(self._items, handle, indent=4)
            tmp.replace(self._path)

    def send(self, alert: SecurityAlert) -> None:
        self.append(alert.as_dict())

    def close(self) -> None:
        return None


class WebhookChannel:
    """Deliver alerts to an HTTP(S) endpoint on a background worker.

    Features:
      * bounded queue --- an unreachable endpoint never blocks the detector
      * at-most-``max_retries`` delivery attempts with exponential backoff
      * optional ``Authorization: Bearer`` header for control-room gateways
      * non-fatal: delivery failures are logged, never raised to the caller
    """

    def __init__(
        self,
        url: str | None,
        *,
        token: str | None = None,
        timeout: float = 5.0,
        max_retries: int = 3,
        queue_size: int = 256,
        logger: Logger | None = None,
    ) -> None:
        self._url = url
        self._token = token
        self._timeout = max(0.1, float(timeout))
        self._max_retries = max(0, int(max_retries))
        self._queue: Queue[SecurityAlert] = Queue(maxsize=max(1, int(queue_size)))
        self._log = (logger or logging.getLogger("ibvap")).getChild("webhook")
        self._thread = threading.Thread(
            target=self._worker, name="ibvap-webhook", daemon=True
        )
        self._running = False

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        if self._url is None:
            self._log.debug("Webhook disabled (no URL configured)")
            return
        self._running = True
        self._thread.start()
        self._log.info("Webhook channel started -> %s", self._url)

    def send(self, alert: SecurityAlert) -> None:
        if self._url is None:
            return
        try:
            self._queue.put_nowait(alert)
        except Full:
            self._log.warning(
                "Webhook queue full; dropping alert %s to protect detection loop",
                alert.alert_id,
            )

    def close(self) -> None:
        """Stop the worker, draining buffered alerts within a grace window."""
        if not self._running:
            return
        self._running = False
        self._thread.join(timeout=self._timeout * (self._max_retries + 1) + 2.0)
        if self._thread.is_alive():
            self._log.warning("Webhook worker did not stop within grace period")

    # ------------------------------------------------------------- internals
    def _worker(self) -> None:
        while self._running or not self._queue.empty():
            try:
                alert = self._queue.get(timeout=0.25)
            except Empty:
                continue
            self._deliver_with_retries(alert)
            self._queue.task_done()

    def _deliver_with_retries(self, alert: SecurityAlert) -> None:
        payload = json.dumps(alert.as_dict())
        for attempt in range(1, self._max_retries + 1):
            try:
                self._post(payload)
                self._log.debug("Delivered alert %s (attempt %d)", alert.alert_id, attempt)
                return
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
                if attempt < self._max_retries:
                    delay = 2 ** (attempt - 1)
                    self._log.warning(
                        "Webhook attempt %d/%d failed for %s: %s; "
                        "retrying in %.0fs",
                        attempt, self._max_retries, alert.alert_id, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    self._log.error(
                        "Webhook delivery failed for %s after %d attempts: %s",
                        alert.alert_id, self._max_retries, exc,
                    )

    def _post(self, payload: str) -> None:
        assert self._url is not None
        request = urllib.request.Request(
            self._url,
            data=payload.encode("utf-8"),
            headers=self._headers(len(payload)),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            response.read()

    def _headers(self, content_length: int) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Length": str(content_length),
            "User-Agent": "IBVAP/1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers