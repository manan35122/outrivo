"""Postgres connection pool (Supabase / Neon).

- dict_row: rows come back as dicts (also required by the LangGraph checkpointer).
- autocommit: each statement commits on its own; use conn.transaction() for groups.
- prepare_threshold=None: Supabase / Neon poolers (pgbouncer) break server-side
  prepared statements.
"""

import threading

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                if not DATABASE_URL:
                    raise RuntimeError("DATABASE_URL is not set")
                pool = ConnectionPool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    kwargs={
                        "autocommit": True,
                        "row_factory": dict_row,
                        "prepare_threshold": None,
                    },
                    check=ConnectionPool.check_connection,  # drop connections the host closed while idle
                    open=False,
                )
                pool.open()
                _pool = pool
    return _pool
