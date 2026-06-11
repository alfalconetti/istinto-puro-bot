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
        logger.info("Migration 1: stats aggiornata con group_id")

    # Migration 2: colonna league su teams
    team_cols = [r[1] for r in conn.execute("PRAGMA table_info(teams)").fetchall()]
    if team_cols and "league" not in team_cols:
        conn.execute("ALTER TABLE teams ADD COLUMN league TEXT")
        logger.info("Migration 2: teams aggiornata con colonna league")

    # Migration 3: colonna league su group_team_overrides
    ov_cols = [r[1] for r in conn.execute("PRAGMA table_info(group_team_overrides)").fetchall()]
    if ov_cols and "league" not in ov_cols:
        conn.execute("ALTER TABLE group_team_overrides ADD COLUMN league TEXT")
        logger.info("Migration 3: group_team_overrides aggiornata con colonna league")


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name   TEXT UNIQUE NOT NULL COLLATE NOCASE,
                league TEXT
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

            -- Sovrascritture per-gruppo: action = 'add' o 'exclude'
            CREATE TABLE IF NOT EXISTS group_team_overrides (
                group_id  INTEGER NOT NULL,
                team_name TEXT    NOT NULL COLLATE NOCASE,
                action    TEXT    NOT NULL CHECK(action IN ('add', 'exclude')),
                league    TEXT,
                PRIMARY KEY (group_id, team_name)
            );
        """)
        _migrate(conn)


# ── Teams (globali, solo ADMIN_ID) ────────────────────────────────────────

def admin_add_team(name: str, league: str | None = None) -> bool:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO teams (name, league) VALUES (?, ?)",
                (name.strip(), league)
            )
        return True
    except sqlite3.IntegrityError:
        return False


def admin_del_team(name: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM teams WHERE name = ? COLLATE NOCASE", (name.strip(),)
        )
        return cur.rowcount > 0


def admin_get_all_teams() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT name, league FROM teams ORDER BY league, name"
        ).fetchall()


# ── Team overrides per gruppo ─────────────────────────────────────────────

def get_leagues() -> list[str]:
    """Restituisce le league distinte presenti nel DB, ordinate."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT league FROM teams WHERE league IS NOT NULL ORDER BY league"
        ).fetchall()
    return [r["league"] for r in rows]


def group_add_team(group_id: int, name: str, league: str | None = None) -> bool:
    """Aggiunge una squadra extra per il gruppo."""
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO group_team_overrides (group_id, team_name, action, league)
                VALUES (?, ?, 'add', ?)
                ON CONFLICT(group_id, team_name) DO UPDATE SET action = 'add', league = excluded.league
            """, (group_id, name.strip(), league))
        return True
    except sqlite3.IntegrityError:
        return False


def group_exclude_team(group_id: int, name: str) -> bool:
    """Esclude una squadra globale per il gruppo."""
    with get_conn() as conn:
        # Controlla che la squadra esista globalmente o come add locale
        exists_global = conn.execute(
            "SELECT 1 FROM teams WHERE name = ? COLLATE NOCASE", (name.strip(),)
        ).fetchone()
        exists_local = conn.execute("""
            SELECT 1 FROM group_team_overrides
            WHERE group_id = ? AND team_name = ? COLLATE NOCASE AND action = 'add'
        """, (group_id, name.strip())).fetchone()

        if not exists_global and not exists_local:
            return False

        conn.execute("""
            INSERT INTO group_team_overrides (group_id, team_name, action)
            VALUES (?, ?, 'exclude')
            ON CONFLICT(group_id, team_name) DO UPDATE SET action = 'exclude'
        """, (group_id, name.strip()))
        return True


def group_restore_team(group_id: int, name: str) -> bool:
    """Rimuove l'override per il gruppo (ripristina comportamento globale)."""
    with get_conn() as conn:
        cur = conn.execute("""
            DELETE FROM group_team_overrides
            WHERE group_id = ? AND team_name = ? COLLATE NOCASE
        """, (group_id, name.strip()))
        return cur.rowcount > 0


def group_get_team_list(group_id: int) -> dict:
    """
    Ritorna il pool effettivo di squadre per il gruppo.
    {name: league} — globali - exclude + add locali.
    """
    with get_conn() as conn:
        globals_ = conn.execute(
            "SELECT name, league FROM teams"
        ).fetchall()
        overrides = conn.execute("""
            SELECT team_name, action, league FROM group_team_overrides
            WHERE group_id = ?
        """, (group_id,)).fetchall()

    excludes = {r["team_name"].lower() for r in overrides if r["action"] == "exclude"}
    adds     = {r["team_name"]: r["league"] for r in overrides if r["action"] == "add"}

    pool = {r["name"]: r["league"] for r in globals_ if r["name"].lower() not in excludes}
    for name, league in adds.items():
        if name.lower() not in {k.lower() for k in pool}:
            pool[name] = league

    return pool


def get_two_random_teams(group_id: int) -> tuple[str, str] | None:
    import random
    pool = group_get_team_list(group_id)  # {name: league}
    if len(pool) < 2:
        return None

    names  = list(pool.keys())
    team_a = random.choice(names)
    league_a = pool[team_a]

    # Costruisci pesi per team_b: doppio se stessa league (e league non è None)
    remaining = [n for n in names if n != team_a]
    if league_a:
        weights = [2 if pool[n] == league_a else 1 for n in remaining]
    else:
        weights = [1] * len(remaining)

    team_b = random.choices(remaining, weights=weights, k=1)[0]
    return team_a, team_b


def group_list_overrides(group_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("""
            SELECT team_name, action FROM group_team_overrides
            WHERE group_id = ? ORDER BY action, team_name
        """, (group_id,)).fetchall()


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
        played  = get_games_played(group_id, s["user_id"])
        win_pct = (s["wins"] / played * 100) if played > 0 else 0.0
        result.append({
            "username": s["username"],
            "wins":     s["wins"],
            "played":   played,
            "win_pct":  win_pct,
        })

    result.sort(key=lambda x: (x["win_pct"], x["wins"]), reverse=True)
    return result
