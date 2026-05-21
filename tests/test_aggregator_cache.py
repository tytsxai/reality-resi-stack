from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
AGGREGATOR_PATH = REPO_ROOT / "subscription" / "aggregator_server.py"


def load_aggregator_module():
    os.environ.setdefault("TOKEN", "test-token")
    spec = importlib.util.spec_from_file_location("aggregator_server_under_test", AGGREGATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AggregatorCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.aggregator = load_aggregator_module()
        self.aggregator.CACHE_FILE = Path(self.tmp.name) / "usage-cache.json"
        self.aggregator.CACHE_TTL_SECONDS = 60
        self.aggregator.FALLBACK_USED_BYTES = 12

    def set_time(self, now: int) -> None:
        patcher = patch.object(self.aggregator.time, "time", return_value=now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_cache(self, used_bytes: int, cached_at: int = 100) -> None:
        self.aggregator.CACHE_FILE.write_text(
            json.dumps({"reported_used_bytes": used_bytes, "cached_at": cached_at}),
            encoding="utf-8",
        )

    def test_fresh_cache_does_not_poll_remote(self) -> None:
        self.write_cache(55, cached_at=100)
        self.set_time(120)

        def fail_if_called() -> dict:
            raise AssertionError("fresh cache should not poll remote")

        self.aggregator.read_remote_status = fail_if_called

        used, meta = self.aggregator.current_usage()

        self.assertEqual(used, 55)
        self.assertEqual(meta["source"], "cache-fresh")

    def test_stale_cache_refreshes(self) -> None:
        self.write_cache(55, cached_at=100)
        self.set_time(200)
        self.aggregator.read_remote_status = lambda: {"reported_used_bytes": 77}

        used, meta = self.aggregator.current_usage()

        self.assertEqual(used, 77)
        self.assertEqual(meta["source"], "remote_status")
        cached = json.loads(self.aggregator.CACHE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(cached["reported_used_bytes"], 77)

    def test_remote_failure_uses_stale_cache(self) -> None:
        self.write_cache(55, cached_at=100)
        self.set_time(200)

        def fail_remote() -> dict:
            raise TimeoutError("leaf down")

        self.aggregator.read_remote_status = fail_remote

        used, meta = self.aggregator.current_usage()

        self.assertEqual(used, 55)
        self.assertEqual(meta["source"], "cache-stale-fallback")

    def test_no_cache_uses_fallback(self) -> None:
        self.set_time(200)

        def fail_remote() -> dict:
            raise TimeoutError("leaf down")

        self.aggregator.read_remote_status = fail_remote

        used, meta = self.aggregator.current_usage()

        self.assertEqual(used, 12)
        self.assertEqual(meta["source"], "fallback")


if __name__ == "__main__":
    unittest.main()
