"""Tests for the notification channels.

The webhook test spins up a real local HTTP server on an ephemeral port so
delivery is verified end-to-end (serialization, headers, HTTP transport)
without leaving the machine. Uses only the standard library.
"""

from __future__ import annotations

import http.server
import json
import logging
import threading
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from channels import JsonChannel, WebhookChannel
from models import EventType, SecurityAlert, Severity


def sample_alert(**overrides) -> SecurityAlert:
    defaults = dict(
        alert_id="ALT-9001",
        event_id="EVT-9001",
        event_type=EventType.VIRTUAL_FENCE_BREACH,
        object_type="person",
        track_id=42,
        camera_id="BOP-CAM-01",
        severity=Severity.CRITICAL,
        status="ACTIVE",
        message="Person crossed the virtual fence at camera BOP-CAM-01",
        timestamp=datetime(2026, 1, 1, 12, 0, 0),
        frame_number=42,
        evidence_path="output/evidence/EVT-9001.jpg",
        metadata={"observations": 5},
    )
    defaults.update(overrides)
    return SecurityAlert(**defaults)


class _Handler(http.server.BaseHTTPRequestHandler):
    """Records the JSON body of the single POST it expects."""

    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _Handler.received.append(
            {
                "body": json.loads(body.decode("utf-8")),
                "auth": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *args: object) -> None:  # silence stderr
        return None


class WebhookChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        logging.getLogger("ibvap").addHandler(logging.NullHandler())
        _Handler.received = []
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2.0)

    def test_delivers_alert_with_auth_header(self) -> None:
        webhook = WebhookChannel(
            f"http://127.0.0.1:{self.port}/ingest/alerts",
            token="s3cret",
            timeout=2.0,
            max_retries=1,
        )
        try:
            webhook.start()
            alert = sample_alert()
            webhook.send(alert)
        finally:
            webhook.close()

        self.assertEqual(len(_Handler.received), 1)
        payload = _Handler.received[0]
        self.assertIsNotNone(payload)
        self.assertEqual(payload["auth"], "Bearer s3cret")
        self.assertEqual(payload["content_type"], "application/json")
        self.assertEqual(payload["body"]["alert_id"], "ALT-9001")
        self.assertEqual(payload["body"]["severity"], "CRITICAL")
        self.assertEqual(payload["body"]["metadata"]["observations"], 5)

    def test_unreachable_endpoint_never_raises(self) -> None:
        # port 1 on loopback is effectively unreachable; the channel must
        # fail gracefully and not raise into the caller.
        webhook = WebhookChannel(
            "http://127.0.0.1:1/unreachable",
            timeout=0.3,
            max_retries=1,
        )
        try:
            webhook.start()
            webhook.send(sample_alert())  # must not raise
            import time
            time.sleep(1.0)  # let the worker exhaust its single attempt
        finally:
            webhook.close()
        self.assertEqual(len(_Handler.received), 1, "only the reachable test posted")


class JsonChannelTests(unittest.TestCase):
    def test_appends_and_round_trips(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "alerts.json"
            channel = JsonChannel(path)
            channel.send(sample_alert(alert_id="ALT-0001"))
            channel.send(sample_alert(alert_id="ALT-0002"))
            channel.close()

            with path.open("r", encoding="utf-8") as handle:
                items = json.load(handle)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["alert_id"], "ALT-0001")
            self.assertEqual(items[1]["alert_id"], "ALT-0002")

    def test_resumes_from_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "alerts.json"
            first = JsonChannel(path)
            first.send(sample_alert(alert_id="ALT-0001"))
            first.close()

            second = JsonChannel(path)
            second.send(sample_alert(alert_id="ALT-0002"))
            second.close()

            with path.open("r", encoding="utf-8") as handle:
                items = json.load(handle)
            self.assertEqual([i["alert_id"] for i in items], ["ALT-0001", "ALT-0002"])


if __name__ == "__main__":
    unittest.main()