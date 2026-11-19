"""Agent run 세션 저장소.

RUNS = in-memory dict 대신 SQLite로 영속화. 재시작 후에도 run_id로 조회 가능.
TTL 경과한 세션은 지연 삭제한다 (조회/저장 시).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        s = settings()
        s.session_db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(s.session_db), check_same_thread=False, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runs (
                   run_id TEXT PRIMARY KEY,
                   created_at REAL NOT NULL,
                   parent TEXT,
                   form_json TEXT NOT NULL,
                   report_json TEXT,
                   mode TEXT
               )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at)")
        conn.commit()
        _conn = conn
    return _conn


def _gc(cur: sqlite3.Cursor) -> None:
    ttl = settings().session_ttl_s
    cutoff = time.time() - ttl
    cur.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))


def put_run(run_id: str, form: dict[str, Any], parent: str | None = None) -> None:
    with _lock:
        conn = _connect()
        cur = conn.cursor()
        _gc(cur)
        cur.execute(
            "INSERT OR REPLACE INTO runs(run_id, created_at, parent, form_json) VALUES (?, ?, ?, ?)",
            (run_id, time.time(), parent, json.dumps(form, ensure_ascii=False)),
        )
        conn.commit()


def set_report(run_id: str, report: dict[str, Any], mode: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE runs SET report_json=?, mode=? WHERE run_id=?",
            (json.dumps(report, ensure_ascii=False), mode, run_id),
        )
        conn.commit()


def get_run(run_id: str) -> dict[str, Any] | None:
    with _lock:
        conn = _connect()
        cur = conn.cursor()
        _gc(cur)
        row = cur.execute(
            "SELECT run_id, created_at, parent, form_json, report_json, mode FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "run_id": row[0], "created_at": row[1], "parent": row[2],
        "form": json.loads(row[3]),
        "report": json.loads(row[4]) if row[4] else None,
        "mode": row[5],
    }


def count_recent(seconds: int) -> int:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE created_at > ?", (time.time() - seconds,),
        ).fetchone()
    return int(row[0] if row else 0)
