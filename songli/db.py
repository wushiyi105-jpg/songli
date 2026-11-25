"""SQLite persistence for gift history."""

import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get("SONGLI_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "songli.db")
_LOCK = threading.Lock()
_LOCAL = threading.local()


def use(path):
    global DB_PATH
    if path:
        DB_PATH = path
        _LOCAL.conn = None


def connect():
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS gifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT, occasion TEXT, relation TEXT, name TEXT,
            price INTEGER, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()
        _LOCAL.conn = conn
    return conn


def record(recipient, occasion, relation, name, price=None, note=None):
    with _LOCK:
        conn = connect()
        cur = conn.execute(
            "INSERT INTO gifts(recipient, occasion, relation, name, price, note) VALUES (?,?,?,?,?,?)",
            (recipient, occasion, relation, name, price, note))
        conn.commit()
        return cur.lastrowid


def history(recipient=None, limit=50):
    with _LOCK:
        if recipient:
            rows = connect().execute(
                "SELECT * FROM gifts WHERE recipient = ? ORDER BY id DESC LIMIT ?",
                (recipient, limit)).fetchall()
        else:
            rows = connect().execute("SELECT * FROM gifts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def sent_names(recipient):
    with _LOCK:
        rows = connect().execute("SELECT name FROM gifts WHERE recipient = ?", (recipient,)).fetchall()
    return [r["name"] for r in rows]


def save_plan(result, recipient=None):
    with _LOCK:
        conn = connect()
        conn.execute("INSERT INTO plans(recipient, detail) VALUES (?,?)",
                     (recipient, json.dumps(result, ensure_ascii=False)))
        conn.commit()


def plans(limit=10):
    with _LOCK:
        try:
            rows = connect().execute(
                "SELECT id, recipient, created_at FROM plans ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(r) for r in rows]
