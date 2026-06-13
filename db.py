"""
Oracle connectivity for the LIFETECH dashboard.

Uses python-oracledb with a small connection pool. Thick mode is enabled by
default (the Oracle client is installed on this server); set ORACLE_THICK_MODE=0
to fall back to the pure-python thin driver.
"""
import logging
from contextlib import contextmanager

import oracledb

from config import Config

log = logging.getLogger(__name__)

_pool = None
_thick_initialized = False


def _init_thick_mode():
    global _thick_initialized
    if _thick_initialized or not Config.ORACLE_THICK_MODE:
        return
    try:
        if Config.ORACLE_CLIENT_LIB_DIR:
            oracledb.init_oracle_client(lib_dir=Config.ORACLE_CLIENT_LIB_DIR)
        else:
            oracledb.init_oracle_client()
        _thick_initialized = True
        log.info("Oracle client initialized (thick mode).")
    except Exception as exc:  # noqa: BLE001
        # Already initialized, or client not found -> continue (thin mode).
        log.warning("Could not init Oracle thick client (%s). Using thin mode.", exc)


def get_pool():
    """Lazily create and return the shared connection pool."""
    global _pool
    if _pool is None:
        _init_thick_mode()
        _pool = oracledb.create_pool(
            user=Config.ORACLE_USER,
            password=Config.ORACLE_PASSWORD,
            dsn=Config.dsn(),
            min=Config.POOL_MIN,
            max=Config.POOL_MAX,
            increment=Config.POOL_INCREMENT,
        )
        log.info("Oracle connection pool created.")
    return _pool


@contextmanager
def get_connection():
    pool = get_pool()
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)


def query_all(sql, params=None):
    """Run a SELECT and return a list of dicts keyed by lowercased column name."""
    params = params or {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [c[0].lower() for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def query_one(sql, params=None):
    rows = query_all(sql, params)
    return rows[0] if rows else None


def ping():
    """Return True if the database is reachable."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM DUAL")
                cur.fetchone()
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Database ping failed: %s", exc)
        return False
