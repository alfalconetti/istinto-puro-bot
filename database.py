import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "data/instinto.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection):
    """Migrazioni incrementali dello schema."""

    # Migration 1: stats senza group_id → ricrea con group_id
    cols = [r[1] for r in conn.execute("PRAGMA table_info(stats)").fetchall()]
    if cols and "group_id" not in cols:
        # Salva i dati vecchi (user_id, username, wins) con group_id=0 come placeholder
        conn.executescript("""
            ALTER TABLE stats RENAME TO stats_old;

            CREATE TABLE stats (
                group_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                username TEXT    NOT NULL,
                wins     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (group_id, user_id)
            );

            INSERT INTO stats (group_id, user_id, username, wins)
            SELECT 0, user_id, username, wins FROM stats_old;

            DROP TABLE stats_old;
        """)
        logger.info("Migration completata: stats aggiornata con group_id (righe vecchie → group_id=0)")


def init_db():
    with get_conn() as conn:
        # Crea prima le tabelle, poi migra
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL COLLATE NOCASE
            );

            -- Una partita per gruppo, group_id = chat_id Telegram
            CREATE TABLE IF NOT EXISTS games (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id     INTEGER NOT NULL,
                player1_id   INTEGER NOT NULL,
                player1_name TEXT    NOT NULL,
                player2_id   INTEGER NOT NULL,
                player2_name TEXT    NOT NULL,
                target_score INTEGER NOT NULL DEFAULT 3,
                auto_teams   INTEGER NOT NULL DEFAULT 1,  -- 1=auto, 0=manual
                state        TEXT    NOT NULL DEFAULT 'LOBBY',
                score1       INTEGER NOT NULL DEFAULT 0,
                score2       INTEGER NOT NULL DEFAULT 0,
                started_at   TEXT    NOT NULL,
                ended_at     TEXT
            );

            -- Storico mani
            CREATE TABLE IF NOT EXISTS hands (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id    INTEGER NOT NULL REFERENCES games(id),
                hand_num   INTEGER NOT NULL,
                team_a     TEXT    NOT NULL,
                team_b     TEXT    NOT NULL,
                winner_id  INTEGER,           -- NULL = skip/nessuno
                played_at  TEXT    NOT NULL
            );

            -- Statistiche vittorie per gruppo
            CREATE TABLE IF NOT EXISTS stats (
                group_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                username TEXT    NOT NULL,
                wins     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (group_id, user_id)
            );
        """)
        _migrate(conn)


# ── Teams ──────────────────────────────────────────────────────────────────

def add_team(name: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO teams (name) VALUES (?)", (name.strip(),))
        return True
    except sqlite3.IntegrityError:
        return False


def del_team(name: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM teams WHERE name = ? COLLATE NOCASE", (name.strip(),)
        )
        return cur.rowcount > 0


def get_all_teams() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT name FROM teams ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def get_two_random_teams() -> tuple[str, str] | None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM teams ORDER BY RANDOM() LIMIT 2"
        ).fetchall()
    if len(rows) < 2:
        return None
    return rows[0]["name"], rows[1]["name"]


# ── Games ──────────────────────────────────────────────────────────────────

def save_game(game) -> int:
    """Inserisce o aggiorna la partita. Ritorna l'id del record."""
    now = datetime.utcnow().isoformat()
    p1, p2 = game.players
    with get_conn() as conn:
        if game.db_id is None:
            cur = conn.execute("""
                INSERT INTO games
                    (group_id, player1_id, player1_name, player2_id, player2_name,
                     target_score, auto_teams, state, score1, score2, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                game.chat_id,
                p1.user_id, p1.username,
                p2.user_id, p2.username,
                game.target_score,
                1 if game.auto_teams else 0,
                game.state.name,
                p1.score, p2.score,
                now,
            ))
            return cur.lastrowid
        else:
            conn.execute("""
                UPDATE games
                SET state=?, score1=?, score2=?, ended_at=?
                WHERE id=?
            """, (
                game.state.name,
                p1.score, p2.score,
                now if game.state.name == "GAME_OVER" else None,
                game.db_id,
            ))
            return game.db_id


def save_hand(game_id: int, hand_num: int, team_a: str, team_b: str, winner_id: int | None):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO hands (game_id, hand_num, team_a, team_b, winner_id, played_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (game_id, hand_num, team_a, team_b, winner_id, now))


def load_active_game(group_id: int) -> sqlite3.Row | None:
    """Carica l'ultima partita non terminata per il gruppo."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM games
            WHERE group_id = ? AND state NOT IN ('GAME_OVER')
            ORDER BY id DESC LIMIT 1
        """, (group_id,)).fetchone()


def mark_game_cancelled(db_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE games SET state='CANCELLED', ended_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), db_id)
        )


# ── Stats ──────────────────────────────────────────────────────────────────

def add_win(group_id: int, user_id: int, username: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO stats (group_id, user_id, username, wins)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(group_id, user_id) DO UPDATE SET
                username = excluded.username,
                wins = wins + 1
        """, (group_id, user_id, username))


def get_leaderboard(group_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("""
            SELECT username, wins FROM stats
            WHERE group_id = ?
            ORDER BY wins DESC
        """, (group_id,)).fetchall()
