"""
populate_leagues.py — Aggiorna la colonna league per le squadre esistenti.
Esegui dentro il container:
    docker exec instinto-puro-bot python populate_leagues.py
"""
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "data/instinto.db")

LEAGUES = {
    # Serie A
    "Atalanta":      "Serie A",
    "Bologna":       "Serie A",
    "Cagliari":      "Serie A",
    "Empoli":        "Serie A",
    "Fiorentina":    "Serie A",
    "Frosinone":     "Serie A",
    "Genoa":         "Serie A",
    "Inter":         "Serie A",
    "Juventus":      "Serie A",
    "Lazio":         "Serie A",
    "Lecce":         "Serie A",
    "Milan":         "Serie A",
    "Monza":         "Serie A",
    "Napoli":        "Serie A",
    "Parma":         "Serie A",
    "Roma":          "Serie A",
    "Sampdoria":     "Serie A",
    "Sassuolo":      "Serie A",
    "Torino":        "Serie A",
    "Udinese":       "Serie A",
    "Venezia":       "Serie A",
    "Verona":        "Serie A",

    # Premier League
    "Arsenal":           "Premier League",
    "Aston Villa":       "Premier League",
    "Chelsea":           "Premier League",
    "Everton":           "Premier League",
    "Leicester":         "Premier League",
    "Liverpool":         "Premier League",
    "Manchester City":   "Premier League",
    "Manchester United": "Premier League",
    "Newcastle":         "Premier League",
    "Tottenham":         "Premier League",
    "West Ham":          "Premier League",

    # La Liga
    "Atletico Madrid": "La Liga",
    "Barcellona":      "La Liga",
    "Real Madrid":     "La Liga",
    "Siviglia":        "La Liga",
    "Valencia":        "La Liga",
    "Villarreal":      "La Liga",

    # Bundesliga
    "Bayer Leverkusen":          "Bundesliga",
    "Bayern Monaco":             "Bundesliga",
    "Borussia Dortmund":         "Bundesliga",
    "Borussia Mönchengladbach":  "Bundesliga",
    "Schalke 04":                "Bundesliga",
    "Wolfsburg":                 "Bundesliga",
    "Lipsia":                    "Bundesliga",

    # Ligue 1
    "Lens":      "Ligue 1",
    "Lille":     "Ligue 1",
    "Lione":     "Ligue 1",
    "Marsiglia": "Ligue 1",
    "Monaco":    "Ligue 1",
    "Nice":      "Ligue 1",
    "PSG":       "Ligue 1",
    "Rennes":    "Ligue 1",

    # Eredivisie
    "Ajax":         "Eredivisie",
    "Feyenoord":    "Eredivisie",
    "PSV Eindhoven":"Eredivisie",

    # Primeira Liga
    "Benfica":          "Primeira Liga",
    "Porto":            "Primeira Liga",
    "Sporting Lisbona": "Primeira Liga",

    # Süper Lig
    "Fenerbahçe":  "Süper Lig",
    "Galatasaray": "Süper Lig",

    # Altre
    "Club Brugge":       "Pro League",
    "Shakhtar Donetsk":  "Premier Liga",
    "Zenit San Pietroburgo": "RPL",
}


def main():
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    not_found = []

    for name, league in LEAGUES.items():
        cur = conn.execute(
            "UPDATE teams SET league = ? WHERE name = ? COLLATE NOCASE",
            (league, name)
        )
        if cur.rowcount > 0:
            updated += 1
        else:
            not_found.append(name)

    conn.commit()
    conn.close()

    print(f"✅ Aggiornate: {updated} squadre")
    if not_found:
        print(f"⚠️  Non trovate nel DB ({len(not_found)}):")
        for n in not_found:
            print(f"   • {n}")


if __name__ == "__main__":
    main()
