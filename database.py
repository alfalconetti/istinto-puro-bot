import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "data/instinto.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL COLLATE NOCASE
            );

            CREATE TABLE IF NOT EXISTS stats (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                wins INTEGER NOT NULL DEFAULT 0
            );
        """)


# ── Teams ──────────────────────────────────────────────────────────────────

def add_team(name: str) -> bool:
    """Returns True if inserted, False if already exists."""
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO teams (name) VALUES (?)", (name.strip(),))
        return True
    except sqlite3.IntegrityError:
        return False


def del_team(name: str) -> bool:
    """Returns True if deleted, False if not found."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM teams WHERE name = ? COLLATE NOCASE", (name.strip(),))
        return cur.rowcount > 0


def get_all_teams() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT name FROM teams ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def get_two_random_teams() -> tuple[str, str] | None:
    with get_conn() as conn:
        rows = conn.execute("SELECT name FROM teams ORDER BY RANDOM() LIMIT 2").fetchall()
    if len(rows) < 2:
        return None
    return rows[0]["name"], rows[1]["name"]


# ── Stats ──────────────────────────────────────────────────────────────────

def add_win(user_id: int, username: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO stats (user_id, username, wins)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                wins = wins + 1
        """, (user_id, username))


def get_leaderboard() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT username, wins FROM stats ORDER BY wins DESC"
        ).fetchall()
