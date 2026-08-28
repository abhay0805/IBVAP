"""Tests for configuration resolution and validation.

Guards against silent overrides being dropped (field/flag name drift) and
ensures invalid configurations fail fast before touching the pipeline.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]


def _argv(*args: str) -> list[str]:
    return list(args)


class ConfigCliTests(unittest.TestCase):
    def test_cli_overrides_survive_resolution(self) -> None:
        endpoint = "https://control-room.example/ingest/alerts"
        settings = load_settings(
            _argv(
                "--video", "videos/test.mp4",
                "--fence-y", "512",
                "--confidence", "0.55",
                "--camera-id", "BOP-CAM-77",
                "--webhook-url", endpoint,
                "--webhook-token", "t0k3n",
                "--alert-cooldown", "7",
                "--min-observations", "5",
                "--webhook-retries", "1",
            )
        )
        self.assertEqual(settings.fence_y, 512)
        self.assertEqual(settings.confidence, 0.55)
        self.assertEqual(settings.camera_id, "BOP-CAM-77")
        self.assertEqual(settings.webhook_url, endpoint)
        self.assertEqual(settings.webhook_token, "t0k3n")
        self.assertEqual(settings.alert_cooldown_seconds, 7.0)
        self.assertEqual(settings.min_observations, 5)
        self.assertEqual(settings.webhook_max_retries, 1)

    def test_defaults_are_sane(self) -> None:
        settings = Settings()
        self.assertEqual(settings.fence_y, 700)
        self.assertGreater(settings.confidence, 0)
        self.assertEqual(settings.camera_id, "BOP-CAM-01")
        self.assertIsNone(settings.webhook_url)

    def test_missing_video_fails_fast(self) -> None:
        with self.assertRaises(ValueError):
            load_settings(_argv("--video", "no/such/file.mp4"))

    def test_invalid_fence_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load_settings(_argv("--fence-y", "-5"))

    def test_invalid_confidence_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load_settings(_argv("--confidence", "1.5"))


class ConfigFileTests(unittest.TestCase):
    def test_json_config_seeds_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps({"fence_y": 333, "camera_id": "BOP-CAM-09"}),
                encoding="utf-8",
            )
            settings = load_settings(_argv("--config", str(config_path)))
            self.assertEqual(settings.fence_y, 333)
            self.assertEqual(settings.camera_id, "BOP-CAM-09")

    def test_cli_wins_over_json_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps({"fence_y": 333}), encoding="utf-8")
            settings = load_settings(
                _argv("--config", str(config_path), "--fence-y", "444")
            )
            self.assertEqual(settings.fence_y, 444)

    def test_missing_config_file_fails_fast(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_settings(_argv("--config", "nope.json"))

    def test_path_aliases_resolve_under_output_dir(self) -> None:
        settings = Settings()
        self.assertEqual(settings.db_path.name, "ibvap.db")
        self.assertEqual(settings.evidence_dir.name, "evidence")


if __name__ == "__main__":
    unittest.main()