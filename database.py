import sqlite3
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "data/instinto.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection):
    # Migration 1: stats senza group_id
    cols = [r[1] for r in conn.execute("PRAGMA table_info(stats)").fetchall()]
    if cols and "group_id" not in cols:
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
        logger.info("Migration: stats aggiornata con group_id")


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL COLLATE NOCASE
            );

            CREATE TABLE IF NOT EXISTS games (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id     INTEGER NOT NULL,
                player1_id   INTEGER NOT NULL,
                player1_name TEXT    NOT NULL,
                player2_id   INTEGER NOT NULL,
                player2_name TEXT    NOT NULL,
                target_score INTEGER NOT NULL DEFAULT 3,
                auto_teams   INTEGER NOT NULL DEFAULT 1,
                state        TEXT    NOT NULL DEFAULT 'LOBBY',
                score1       INTEGER NOT NULL DEFAULT 0,
                score2       INTEGER NOT NULL DEFAULT 0,
                started_at   TEXT    NOT NULL,
                ended_at     TEXT
            );

            CREATE TABLE IF NOT EXISTS hands (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id    INTEGER NOT NULL REFERENCES games(id),
                hand_num   INTEGER NOT NULL,
                team_a     TEXT    NOT NULL,
                team_b     TEXT    NOT NULL,
                winner_id  INTEGER,
                played_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stats (
                group_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                username TEXT    NOT NULL,
                wins     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (group_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS invite_codes (
                code        TEXT    PRIMARY KEY,
                creator_id  INTEGER NOT NULL,
                target_score INTEGER NOT NULL DEFAULT 3,
                auto_teams  INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT    NOT NULL,
                expires_at  TEXT    NOT NULL
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
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM games
            WHERE group_id = ? AND state NOT IN ('GAME_OVER', 'CANCELLED')
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


# ── Invite codes ───────────────────────────────────────────────────────────

INVITE_TTL_MINUTES = 15


def save_invite_code(code: str, creator_id: int, target_score: int, auto_teams: bool):
    now = datetime.utcnow()
    expires = now + timedelta(minutes=INVITE_TTL_MINUTES)
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO invite_codes
                (code, creator_id, target_score, auto_teams, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            code, creator_id, target_score,
            1 if auto_teams else 0,
            now.isoformat(), expires.isoformat(),
        ))


def get_invite_code(code: str) -> sqlite3.Row | None:
    cleanup_expired_codes()
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM invite_codes WHERE code = ?", (code.upper(),)
        ).fetchone()


def delete_invite_code(code: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM invite_codes WHERE code = ?", (code.upper(),))


def cleanup_expired_codes():
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM invite_codes WHERE expires_at < ?", (now,))


# ── Win% stats ─────────────────────────────────────────────────────────────

def get_games_played(group_id: int, user_id: int) -> int:
    """Conta le partite completate (GAME_OVER) in cui l'utente era player1 o player2."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as c FROM games
            WHERE group_id = ?
              AND state = 'GAME_OVER'
              AND (player1_id = ? OR player2_id = ?)
        """, (group_id, user_id, user_id)).fetchone()
    return row["c"] if row else 0


def get_leaderboard_with_winpct(group_id: int) -> list[dict]:
    """
    Restituisce la classifica ordinata per win%, poi win assolute come tiebreaker.
    Ogni elemento: {username, wins, played, win_pct}
    """
    with get_conn() as conn:
        stats = conn.execute("""
            SELECT user_id, username, wins FROM stats
            WHERE group_id = ?
        """, (group_id,)).fetchall()

    result = []
    for s in stats:
        played = get_games_played(group_id, s["user_id"])
        win_pct = (s["wins"] / played * 100) if played > 0 else 0.0
        result.append({
            "username": s["username"],
            "wins":     s["wins"],
            "played":   played,
            "win_pct":  win_pct,
        })

    result.sort(key=lambda x: (x["win_pct"], x["wins"]), reverse=True)
    return result


def get_games_played(group_id: int, user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as c FROM games
            WHERE group_id = ?
              AND state = 'GAME_OVER'
              AND (player1_id = ? OR player2_id = ?)
        """, (group_id, user_id, user_id)).fetchone()
    return row["c"] if row else 0


def get_leaderboard_with_winpct(group_id: int) -> list[dict]:
    with get_conn() as conn:
        stats = conn.execute("""
            SELECT user_id, username, wins FROM stats
            WHERE group_id = ?
        """, (group_id,)).fetchall()

    result = []
    for s in stats:
        played = get_games_played(group_id, s["user_id"])
        win_pct = (s["wins"] / played * 100) if played > 0 else 0.0
        result.append({
            "username": s["username"],
            "wins":     s["wins"],
            "played":   played,
            "win_pct":  win_pct,
        })

    result.sort(key=lambda x: (x["win_pct"], x["wins"]), reverse=True)
    return result
