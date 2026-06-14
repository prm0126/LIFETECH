"""
Persistence for user-defined custom reports.

Reports are stored as a small JSON file (path from Config.CUSTOM_STORE_FILE).
Each report: {id, title, type, sql, created}. Writes are atomic + lock-guarded.
"""
import json
import os
import secrets
import threading
import time

from config import Config

_lock = threading.Lock()


def _path():
    return Config.CUSTOM_STORE_FILE


def _read():
    p = _path()
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("queries", [])
    except Exception:  # noqa: BLE001 - corrupt/empty file -> start fresh
        return []


def _write(items):
    p = _path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"queries": items}, f, indent=2)
    os.replace(tmp, p)


def list_all():
    with _lock:
        return _read()


def add(title, qtype, sql):
    item = {
        "id": secrets.token_hex(6),
        "title": title,
        "type": qtype,
        "sql": sql,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _lock:
        items = _read()
        items.append(item)
        _write(items)
    return item


def get(qid):
    with _lock:
        for it in _read():
            if it["id"] == qid:
                return it
    return None


def delete(qid):
    with _lock:
        items = _read()
        kept = [it for it in items if it["id"] != qid]
        _write(kept)
        return len(kept) != len(items)
