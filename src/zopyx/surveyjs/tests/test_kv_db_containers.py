# -*- coding: utf-8 -*-
"""PostgreSQL and MySQL contract runs for the KV store facade.

Reuses the shared contract, SQL edge-case and concurrency mixins from
``test_kv`` against real database servers started via testcontainers
(Docker). Every class here is skipped unless ``RUN_DB_CONTAINER_TESTS=1``
so the suite never fails on machines without Docker.

Note: zope.testrunner does not call ``setUpClass``/``tearDownClass``, so
the shared store is created lazily in ``make_store`` (class attribute) and
containers are reaped by testcontainers' ryuk on process exit.

CI (``.github/workflows/tests.yml``) sets the env var and pre-pulls the
images; locally run with::

    RUN_DB_CONTAINER_TESTS=1 bin/test -s zopyx.surveyjs -t test_kv_db_containers
"""

from __future__ import annotations

import os
import unittest

from sqlalchemy import delete

from zopyx.surveyjs.kv import KVEntry, SQLKVStore

from .test_kv import (
    KVStoreConcurrencyBase,
    KVStoreContractBase,
    SQLBackendPurgeMixin,
    SQLContractMixin,
)

RUN_CONTAINER_TESTS = os.environ.get("RUN_DB_CONTAINER_TESTS") == "1"

_POSTGRES_URI = None
_MYSQL_URI = None


def _get_postgres_uri() -> str:
    global _POSTGRES_URI
    if _POSTGRES_URI is None:
        from testcontainers.community.postgres import PostgresContainer

        _POSTGRES_URI = PostgresContainer("postgres:16").start().get_connection_url()
    return _POSTGRES_URI


def _get_mysql_uri() -> str:
    global _MYSQL_URI
    if _MYSQL_URI is None:
        from testcontainers.community.mysql import MySqlContainer

        container = MySqlContainer("mysql:8").start()
        _MYSQL_URI = (
            f"mysql+pymysql://{container.username}:{container.password}@"
            f"{container.get_container_host_ip()}:{container.get_exposed_port(3306)}/"
            f"{container.dbname}"
        )
    return _MYSQL_URI


def _purge_store(store) -> None:
    with store._session() as session:
        session.execute(delete(KVEntry))
        session.commit()


@unittest.skipUnless(RUN_CONTAINER_TESTS, "RUN_DB_CONTAINER_TESTS=1 required")
class PostgresKVStoreTests(
    SQLBackendPurgeMixin, SQLContractMixin, KVStoreContractBase, unittest.TestCase
):
    _shared = None

    def make_store(self):
        if type(self)._shared is None:
            type(self)._shared = SQLKVStore(_get_postgres_uri())
        return type(self)._shared


@unittest.skipUnless(RUN_CONTAINER_TESTS, "RUN_DB_CONTAINER_TESTS=1 required")
class MySqlKVStoreTests(
    SQLBackendPurgeMixin, SQLContractMixin, KVStoreContractBase, unittest.TestCase
):
    _shared = None

    def make_store(self):
        if type(self)._shared is None:
            type(self)._shared = SQLKVStore(_get_mysql_uri())
        return type(self)._shared


@unittest.skipUnless(RUN_CONTAINER_TESTS, "RUN_DB_CONTAINER_TESTS=1 required")
class PostgresKVStoreConcurrencyTests(KVStoreConcurrencyBase, unittest.TestCase):
    _shared = None

    def make_store(self):
        if type(self)._shared is None:
            type(self)._shared = SQLKVStore(_get_postgres_uri())
        return type(self)._shared


@unittest.skipUnless(RUN_CONTAINER_TESTS, "RUN_DB_CONTAINER_TESTS=1 required")
class MySqlKVStoreConcurrencyTests(KVStoreConcurrencyBase, unittest.TestCase):
    _shared = None

    def make_store(self):
        if type(self)._shared is None:
            type(self)._shared = SQLKVStore(_get_mysql_uri())
        return type(self)._shared
