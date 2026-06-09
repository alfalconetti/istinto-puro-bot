#!/usr/bin/env python3
"""
Script di popolamento squadre — eseguilo una volta dopo aver avviato il bot.
Inserisce squadre di Serie A (storiche e attuali), Premier League, e top Europa.
"""

import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "data/instinto.db")

TEAMS = [
    # ── Serie A / Italia ──────────────────────────────────────────────────
    "Juventus",
    "Milan",
    "Inter",
    "Roma",
    "Lazio",
    "Napoli",
    "Fiorentina",
    "Atalanta",
    "Torino",
    "Sampdoria",
    "Genoa",
    "Bologna",
    "Parma",
    "Udinese",
    "Cagliari",
    "Verona",
    "Brescia",
    "Palermo",
    "Catania",
    "Bari",
    "Lecce",
    "Reggina",
    "Siena",
    "Chievo",
    "Venezia",
    "Empoli",
    "Sassuolo",
    "Monza",
    "Frosinone",
    "Spezia",
    "Salernitana",
    "Cremonese",
    "Como",
    # ── Premier League / Inghilterra ──────────────────────────────────────
    "Manchester United",
    "Manchester City",
    "Liverpool",
    "Arsenal",
    "Chelsea",
    "Tottenham",
    "Newcastle",
    "Everton",
    "Aston Villa",
    "West Ham",
    "Leicester",

    # ── Spagna ────────────────────────────────────────────────────────────
    "Real Madrid",
    "Barcellona",
    "Atletico Madrid",
    "Siviglia",
    "Valencia",
    "Villarreal",
    "Athletic Bilbao",
    "Real Sociedad",

    # ── Germania ──────────────────────────────────────────────────────────
    "Bayern Monaco",
    "Borussia Dortmund",
    "Bayer Leverkusen",
    "Schalke 04",
    "Borussia Mönchengladbach",
    "Wolfsburg",
    "Lipsia",

    # ── Francia ───────────────────────────────────────────────────────────
    "PSG",
    "Marsiglia",
    "Lione",
    "Monaco",
    "Lille",
    "Nantes",
    "Lens",
    "Rennes",
    "Nice",

    # ── Portogallo ────────────────────────────────────────────────────────
    "Benfica",
    "Porto",
    "Sporting Lisbona",

    # ── Olanda ────────────────────────────────────────────────────────────
    "Ajax",
    "PSV Eindhoven",
    "Feyenoord",

    # ── Turchia ───────────────────────────────────────────────────────────
    "Galatasaray",
    "Fenerbahçe",
    "Besiktas",

    # ── Russia ────────────────────────────────────────────────────────────
    "CSKA Mosca",
    "Zenit San Pietroburgo",
    "Spartak Mosca",
    "Lokomotiv Mosca",

    # ── Belgio / Resto Europa ─────────────────────────────────────────────
    "Anderlecht",
    "Club Brugge",
    "Shakhtar Donetsk",
    "Dinamo Kiev",
    "Steaua Bucarest",
    "Red Bull Salisburgo",
    "Bruges",
]

# Deduplica mantenendo ordine
seen = set()
TEAMS_DEDUP = []
for t in TEAMS:
    if t.lower() not in seen:
        seen.add(t.lower())
        TEAMS_DEDUP.append(t)


def populate():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    skipped = 0
    for name in TEAMS_DEDUP:
        try:
            conn.execute("INSERT INTO teams (name) VALUES (?)", (name,))
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    conn.close()
    print(f"✅ Inserite: {inserted} squadre")
    if skipped:
        print(f"⚠️  Già presenti (saltate): {skipped}")
    print(f"📋 Totale squadre: {len(TEAMS_DEDUP)}")


if __name__ == "__main__":
    populate()
