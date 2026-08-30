# -*- coding: utf-8 -*-
"""Contract and deviation tests for the KV store facade.

Runs the same behavioral contract against the diskcache wrapper and the
SQLite-backed implementation, plus backend-specific deviation tests
(JSON-only values, key-length limit, expired-key iteration/purge) and
bounded thread-race coverage.
"""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from zopyx.surveyjs.kv import DiskCacheStore, SQLKVStore, get_kv_store
from zopyx.surveyjs.storage import SQLResultStorage


class KVStoreContractBase:
    """Common behavioral contract; concrete backend classes combine this
    mixin with ``unittest.TestCase`` so the base itself is never collected
    by the test runner."""

    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.store = self.make_store()
        self.addCleanup(self._close_store)

    def _close_store(self):
        try:
            self.store.close()
        except Exception:
            pass
        # Dispose the (per-test, cached) engine so the SQLAlchemy pool
        # releases its sqlite3 handles (no ResourceWarning noise).
        engine = getattr(self.store, "_engine", None)
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass
        self.tmpdir.cleanup()

    def _wait_until_expired(self, key, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.store.get(key) is None:
                return True
            time.sleep(0.02)
        return self.store.get(key) is None

    # -- set/get --------------------------------------------------------

    def test_string_roundtrip(self):
        self.store.set("k1", "v1")
        self.assertEqual(self.store.get("k1"), "v1")

    def test_nested_dict_roundtrip(self):
        value = {"a": [1, 2, {"b": None}], "c": {"d": "δ-🚴"}}
        self.store.set("k1", value)
        self.assertEqual(self.store.get("k1"), value)

    def test_missing_with_and_without_default(self):
        self.assertIsNone(self.store.get("missing"))
        self.assertEqual(self.store.get("missing", {"d": 1}), {"d": 1})

    def test_set_overwrites(self):
        self.store.set("k1", 1)
        self.store.set("k1", 2)
        self.assertEqual(self.store.get("k1"), 2)

    def test_unicode_key_roundtrip(self):
        self.store.set("schlüssel-🚴-δ", {"ok": True})
        self.assertEqual(self.store.get("schlüssel-🚴-δ"), {"ok": True})

    # -- add ------------------------------------------------------------

    def test_add_once_preserves_first_value(self):
        self.assertTrue(self.store.add("k1", "first"))
        self.assertFalse(self.store.add("k1", "second"))
        self.assertEqual(self.store.get("k1"), "first")

    def test_add_after_delete(self):
        self.assertTrue(self.store.add("k1", "v1"))
        self.store.delete("k1")
        self.assertTrue(self.store.add("k1", "v2"))
        self.assertEqual(self.store.get("k1"), "v2")

    def test_expired_key_can_be_added_again(self):
        self.store.set("k1", "old", expire=0.05)
        self.assertTrue(self._wait_until_expired("k1"))
        self.assertTrue(self.store.add("k1", "new"))
        self.assertEqual(self.store.get("k1"), "new")

    # -- delete ---------------------------------------------------------

    def test_delete_idempotent(self):
        self.store.set("k1", "v1")
        self.store.delete("k1")
        self.store.delete("k1")  # must not raise
        self.assertIsNone(self.store.get("k1"))

    # -- iterkeys -------------------------------------------------------

    def test_iterkeys_all_live_keys_and_prefix_filter(self):
        self.store.set("sub:1", 1)
        self.store.set("sub:2", 2)
        self.store.set("form:1", 3)
        self.assertEqual(
            sorted(self.store.iterkeys()), ["form:1", "sub:1", "sub:2"]
        )
        self.assertEqual(
            sorted(k for k in self.store.iterkeys() if k.startswith("sub:")),
            ["sub:1", "sub:2"],
        )

    # -- TTL ------------------------------------------------------------

    def test_expire_none_persists(self):
        self.store.set("k1", "v1")
        self.assertEqual(self.store.get("k1"), "v1")

    def test_zero_and_negative_expiry_missing(self):
        self.store.set("z", "v", expire=0)
        self.assertIsNone(self.store.get("z"))
        self.store.set("n", "v", expire=-1)
        self.assertIsNone(self.store.get("n"))

    def test_short_positive_expiry_expires(self):
        self.store.set("k1", "v1", expire=0.1)
        self.assertEqual(self.store.get("k1"), "v1")
        self.assertTrue(self._wait_until_expired("k1"))
        self.assertIsNone(self.store.get("k1"))

    def test_set_refreshes_expiry(self):
        self.store.set("k1", "v1", expire=0.05)
        self.store.set("k1", "v2", expire=60)
        time.sleep(0.1)
        self.assertEqual(self.store.get("k1"), "v2")

    def test_set_removes_expiry_with_none(self):
        self.store.set("k1", "v1", expire=0.05)
        self.store.set("k1", "v2")
        time.sleep(0.1)
        self.assertEqual(self.store.get("k1"), "v2")

    # -- value fidelity ------------------------------------------------

    def test_value_fidelity(self):
        cases = [
            None,
            True,
            1,
            {},
            [],
            "",
            "unicode-δ-🚴",
            {"nested": {"a": [1, 2, {"b": None}]}},
        ]
        for index, value in enumerate(cases):
            key = f"v{index}"
            self.store.set(key, value)
            self.assertEqual(self.store.get(key), value)

    def test_bool_and_int_stay_distinct(self):
        self.store.set("b", True)
        self.store.set("i", 1)
        self.assertIs(self.store.get("b"), True)
        self.assertEqual(self.store.get("i"), 1)

    def test_large_payload_roundtrip(self):
        payload = {"data": "x" * 100_000}
        self.store.set("big", payload)
        self.assertEqual(self.store.get("big"), payload)


class DiskCacheStoreTests(KVStoreContractBase, unittest.TestCase):
    """The diskcache wrapper must preserve diskcache behavior."""

    def make_store(self):
        return DiskCacheStore(f"{self.tmpdir.name}/cache.db")


class SQLKVStoreTests(KVStoreContractBase, unittest.TestCase):
    """SQLite-backed store: common contract plus SQL deviations."""

    def make_store(self):
        return SQLKVStore(f"sqlite:///{self.tmpdir.name}/kv.db")

    # -- SQL-specific edge cases ---------------------------------------

    def test_key_exactly_255_chars(self):
        key = "k" * 255
        self.store.set(key, "v")
        self.assertEqual(self.store.get(key), "v")

    def test_overlong_key_rejected_by_all_methods(self):
        key = "k" * 256
        with self.assertRaises(ValueError):
            self.store.set(key, "v")
        with self.assertRaises(ValueError):
            self.store.add(key, "v")
        with self.assertRaises(ValueError):
            self.store.get(key)
        with self.assertRaises(ValueError):
            self.store.delete(key)

    def test_unsupported_value_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.store.set("k1", object())

    def test_rejects_non_sqlite_uri(self):
        with self.assertRaises(ValueError):
            SQLKVStore("postgresql://user:pass@localhost:5432/db")

    def test_engine_cached_by_result_storage_is_reused(self):
        """Regression: an engine cached before the KV table existed must
        still get the KV table created (explicit create_all on init)."""
        uri = f"sqlite:///{self.tmpdir.name}/regress.db"
        SQLResultStorage(uri)  # constructs+caches the engine, create_all
        kv = SQLKVStore(uri)
        kv.set("k1", {"ok": True})
        self.assertEqual(kv.get("k1"), {"ok": True})

    def test_iterkeys_excludes_expired_rows(self):
        self.store.set("old", "v", expire=-1)
        self.store.set("new", "v", expire=60)
        self.assertEqual(sorted(self.store.iterkeys()), ["new"])


class KVStoreConcurrencyBase:
    """Bounded thread-race coverage for the atomic add() primitive.

    Mixin only; concrete backend classes combine it with
    ``unittest.TestCase`` so the base is never collected.
    """

    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.store = self.make_store()
        self.addCleanup(self._close_store)

    def _close_store(self):
        try:
            self.store.close()
        except Exception:
            pass
        # Dispose the (per-test, cached) engine so the SQLAlchemy pool
        # releases its sqlite3 handles (no ResourceWarning noise).
        engine = getattr(self.store, "_engine", None)
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass
        self.tmpdir.cleanup()

    def test_add_race_exactly_one_winner(self):
        results = []
        errors = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)

        def worker(index):
            try:
                barrier.wait(timeout=5)
                ok = self.store.add("race", index)
                with lock:
                    results.append((index, ok))
            except Exception as exc:  # noqa: BLE001 - collected for assertion
                with lock:
                    errors.append(exc)
            finally:
                # diskcache keeps a per-thread connection; each thread that
                # accesses the cache must close it (diskcache usage contract).
                try:
                    self.store.close()
                except Exception:
                    pass

        threads = [
            threading.Thread(target=worker, args=(index,)) for index in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        winners = [index for index, ok in results if ok]
        self.assertEqual(len(winners), 1)
        stored = self.store.get("race")
        self.assertIn(stored, [index for index, _ in results])

    def test_concurrent_independent_keys(self):
        errors = []

        def worker(base):
            try:
                for index in range(25):
                    key = f"{base}:{index}"
                    self.store.set(key, index)
                    if self.store.get(key) != index:
                        raise AssertionError(f"roundtrip failed for {key}")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                # diskcache keeps a per-thread connection; each thread that
                # accesses the cache must close it (diskcache usage contract).
                try:
                    self.store.close()
                except Exception:
                    pass

        threads = [
            threading.Thread(target=worker, args=(f"t{n}",)) for n in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [])


class DiskCacheStoreConcurrencyTests(KVStoreConcurrencyBase, unittest.TestCase):
    def make_store(self):
        return DiskCacheStore(f"{self.tmpdir.name}/cache.db")


class SQLKVStoreConcurrencyTests(KVStoreConcurrencyBase, unittest.TestCase):
    def make_store(self):
        return SQLKVStore(f"sqlite:///{self.tmpdir.name}/kv.db")


class FactoryTests(unittest.TestCase):
    def test_diskcache_factory(self):
        with TemporaryDirectory() as td:
            store = get_kv_store("diskcache", f"{td}/c.db")
            self.assertIsInstance(store, DiskCacheStore)
            store.set("k1", "v1")
            self.assertEqual(store.get("k1"), "v1")
            store.close()

    def test_sqlite_factory(self):
        with TemporaryDirectory() as td:
            store = get_kv_store("sqlite", f"sqlite:///{td}/kv.db")
            self.assertIsInstance(store, SQLKVStore)
            store.set("k1", "v1")
            self.assertEqual(store.get("k1"), "v1")
            store.close()
            engine = getattr(store, "_engine", None)
            if engine is not None:
                engine.dispose()

    def test_unknown_backend_raises(self):
        with self.assertRaises(ValueError):
            get_kv_store("redis", "/tmp/x.db")

    def test_empty_location_raises(self):
        with self.assertRaises(ValueError):
            get_kv_store("diskcache", "")

    def test_timeout_zero_reaches_diskcache_unchanged(self):
        with patch("zopyx.surveyjs.kv.diskcache.Cache") as mock_cache:
            get_kv_store("diskcache", "/tmp/x.db", timeout=0)
            mock_cache.assert_called_once_with("/tmp/x.db", timeout=0)
