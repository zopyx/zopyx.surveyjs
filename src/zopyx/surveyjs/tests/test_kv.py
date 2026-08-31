# -*- coding: utf-8 -*-
"""Contract and deviation tests for the KV store facade.

Runs the same behavioral contract against the diskcache wrapper and every
SQL backend (SQLite, DuckDB; PostgreSQL/MySQL live in
``test_kv_db_containers.py`` and reuse the same mixins), plus
backend-specific deviation tests (JSON-only values, key-length limit,
expired-key iteration/purge) and bounded thread-race coverage.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import delete

from zopyx.surveyjs.kv import (
    DiskCacheStore,
    KVEntry,
    SQLKVStore,
    get_kv_store,
)
from zopyx.surveyjs.storage import SQLResultStorage


class KVStoreContractBase:
    """Common behavioral contract shared by every backend.

    Mixin only: concrete backend classes combine it with
    ``unittest.TestCase`` so the base is never collected by the runner.
    """

    def make_store(self):
        raise NotImplementedError

    def _purge(self):
        """Reset the store so each test starts from an empty state."""

    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.store = self.make_store()
        self._purge()
        self.addCleanup(self._close_store)

    def _close_store(self):
        try:
            self.store.close()
        except Exception:
            pass
        # Dispose the (per-test, cached) engine so the SQLAlchemy pool
        # releases its handles (no ResourceWarning noise).
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

    # -- edge keys / values --------------------------------------------

    def test_empty_string_key(self):
        self.store.set("", "v")
        self.assertEqual(self.store.get(""), "v")
        self.store.delete("")
        self.assertIsNone(self.store.get(""))

    def test_float_precision_fidelity(self):
        value = 0.1 + 0.2
        self.store.set("f", value)
        self.assertEqual(self.store.get("f"), value)

    # -- lifecycle ------------------------------------------------------

    def make_second_store(self):
        """Return a NEW store on the same location as the current one."""
        raise NotImplementedError

    def test_persistence_across_reopen(self):
        self.store.set("k1", "v1")
        self.store.set("k2", {"nested": [1, True, None]})
        self.store.set("ttl", "soon", expire=60)
        self.store.close()
        store2 = self.make_second_store()
        self.store = store2
        self.assertEqual(store2.get("k1"), "v1")
        self.assertEqual(store2.get("k2"), {"nested": [1, True, None]})
        self.assertEqual(store2.get("ttl"), "soon")

    def test_expired_value_gone_after_reopen(self):
        self.store.set("gone", "x", expire=-1)
        self.store.set("live", "y", expire=60)
        self.store.close()
        store2 = self.make_second_store()
        self.store = store2
        self.assertIsNone(store2.get("gone"))
        self.assertEqual(store2.get("live"), "y")

    def test_ops_after_close_still_work(self):
        # Verified diskcache 5.6.3 behavior: close() lazily reopens, ops
        # keep working; SQLKVStore.close() is a documented no-op.
        self.store.close()
        self.store.set("k1", "v1")
        self.assertEqual(self.store.get("k1"), "v1")

    def test_double_close(self):
        self.store.close()
        self.store.close()  # must not raise on either backend


class SQLBackendPurgeMixin:
    """Reset the SQL table before each test (shared-DB isolation)."""

    def _purge(self):
        with self.store._session() as session:
            session.execute(delete(KVEntry))
            session.commit()


class SQLContractMixin:
    """SQL-backend edge cases shared by every SQL dialect."""

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

    def test_unsupported_uri_backend_rejected(self):
        with self.assertRaises(ValueError):
            SQLKVStore("mssql://user:pass@localhost/db")

    def test_iterkeys_excludes_expired_rows(self):
        self.store.set("old", "v", expire=-1)
        self.store.set("new", "v", expire=60)
        self.assertEqual(sorted(self.store.iterkeys()), ["new"])


class DiskCacheStoreTests(KVStoreContractBase, unittest.TestCase):
    """The diskcache wrapper must preserve diskcache behavior."""

    def make_store(self):
        return DiskCacheStore(f"{self.tmpdir.name}/cache.db")

    def make_second_store(self):
        return DiskCacheStore(f"{self.tmpdir.name}/cache.db")

    def _purge(self):
        self.store._cache.clear()


class SQLiteKVStoreTests(
    SQLBackendPurgeMixin, SQLContractMixin, KVStoreContractBase, unittest.TestCase
):
    def make_store(self):
        return SQLKVStore(f"sqlite:///{self.tmpdir.name}/kv.db")

    def make_second_store(self):
        return SQLKVStore(f"sqlite:///{self.tmpdir.name}/kv.db")

    def test_engine_cached_by_result_storage_is_reused(self):
        """Regression: an engine cached before the KV table existed must
        still get the KV table created (explicit create_all on init)."""
        uri = f"sqlite:///{self.tmpdir.name}/regress.db"
        SQLResultStorage(uri)  # constructs+caches the engine, create_all
        kv = SQLKVStore(uri)
        kv.set("k1", {"ok": True})
        self.assertEqual(kv.get("k1"), {"ok": True})
        kv.close()
        engine = getattr(kv, "_engine", None)
        if engine is not None:
            engine.dispose()


class DuckDBKVStoreTests(
    SQLBackendPurgeMixin, SQLContractMixin, KVStoreContractBase, unittest.TestCase
):
    def make_store(self):
        return SQLKVStore(f"duckdb:///{self.tmpdir.name}/kv.duckdb")

    def make_second_store(self):
        return SQLKVStore(f"duckdb:///{self.tmpdir.name}/kv.duckdb")


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


class SQLiteKVStoreConcurrencyTests(KVStoreConcurrencyBase, unittest.TestCase):
    def make_store(self):
        return SQLKVStore(f"sqlite:///{self.tmpdir.name}/kv.db")


class DuckDBKVStoreConcurrencyTests(KVStoreConcurrencyBase, unittest.TestCase):
    def make_store(self):
        return SQLKVStore(f"duckdb:///{self.tmpdir.name}/kv.duckdb")


class SubprocessAddRaceTests(unittest.TestCase):
    """Same-file multi-process add() race (the ZEO shape).

    Three interpreter processes race on one SQLite file / diskcache
    directory; add() must return True for exactly one of them. Gated on
    ``RUN_PROCESS_TESTS=1`` — subprocess tests inside zope.testrunner are
    deliberately not part of the default run.
    """

    _SCRIPT = (
        "from zopyx.surveyjs.kv import DiskCacheStore, SQLKVStore\n"
        "store = SQLKVStore({location!r}) if {backend!r} == 'sqlite' "
        "else DiskCacheStore({location!r})\n"
        "ok = store.add('race', 1)\n"
        "store.close()\n"
        "import sys\n"
        "sys.stdout.write('1' if ok else '0')\n"
    )

    def _run_workers(self, backend, location, count=3):
        # Use the buildout console script as interpreter: a bare python
        # lacks the egg paths bin/test injects at startup, so zope imports
        # would fail. bin/zopepy injects the full buildout egg path.
        repo_root = Path(__file__).resolve().parents[4]
        interpreter = str(repo_root / "bin" / "zopepy")
        src_dir = str(Path(__file__).resolve().parents[3])
        env = dict(os.environ)
        env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
        procs = [
            subprocess.Popen(
                [interpreter, "-c", self._SCRIPT.format(backend=backend, location=location)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            for _ in range(count)
        ]
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, err.decode())
            results.append(out.decode().strip())
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
        return results

    @unittest.skipUnless(
        os.environ.get("RUN_PROCESS_TESTS") == "1", "RUN_PROCESS_TESTS=1 required"
    )
    def test_sqlite_subprocess_add_race(self):
        with TemporaryDirectory() as td:
            uri = f"sqlite:///{td}/race.db"
            # Prime the table in-process so the subprocesses' create_all
            # finds it and cannot race CREATE TABLE.
            SQLKVStore(uri).close()
            results = self._run_workers("sqlite", uri)
            self.assertEqual(results.count("1"), 1, results)

    @unittest.skipUnless(
        os.environ.get("RUN_PROCESS_TESTS") == "1", "RUN_PROCESS_TESTS=1 required"
    )
    def test_diskcache_subprocess_add_race(self):
        with TemporaryDirectory() as td:
            path = f"{td}/cache.db"
            DiskCacheStore(path).close()
            results = self._run_workers("diskcache", path)
            self.assertEqual(results.count("1"), 1, results)


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

    def test_duckdb_factory(self):
        with TemporaryDirectory() as td:
            store = get_kv_store("duckdb", f"duckdb:///{td}/kv.duckdb")
            self.assertIsInstance(store, SQLKVStore)
            store.set("k1", "v1")
            self.assertEqual(store.get("k1"), "v1")
            store.close()
            engine = getattr(store, "_engine", None)
            if engine is not None:
                engine.dispose()

    def test_postgresql_factory(self):
        # Construction must not require a live server.
        with patch("zopyx.surveyjs.kv._get_engine") as mock_engine, patch(
            "zopyx.surveyjs.kv.SQLModel.metadata.create_all"
        ):
            mock_engine.return_value = object()
            store = get_kv_store(
                "postgresql", "postgresql://user:pass@localhost:5432/db"
            )
            self.assertIsInstance(store, SQLKVStore)

    def test_mysql_factory(self):
        with patch("zopyx.surveyjs.kv._get_engine") as mock_engine, patch(
            "zopyx.surveyjs.kv.SQLModel.metadata.create_all"
        ):
            mock_engine.return_value = object()
            store = get_kv_store("mysql", "mysql+pymysql://user:pass@localhost/db")
            self.assertIsInstance(store, SQLKVStore)

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
