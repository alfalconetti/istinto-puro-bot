# Istinto Puro Bot 🎯⚽

Bot Telegram per giocare a **Istinto Puro** in gruppo — dai due giocatori scelgono (o il bot sceglie) due squadre e devono nominare un calciatore che ha giocato in entrambe.

## Funzionalità

- Partite al meglio di X punti (default 3)
- Squadre automatiche (pescate dal DB) o scelte dai giocatori
- Ready check prima di ogni mano
- Countdown animato
- Arbitraggio con bottoni (tutti vedono, solo i giocatori premono)
- `/resumegame` per riprendere partite interrotte
- Classifica vittorie per gruppo
- Storico completo di ogni mano su SQLite

## Comandi

| Comando | Descrizione |
|---|---|
| `/newgame [punti] [auto\|manual]` | Avvia una nuova partita |
| `/cancelgame` | Annulla la partita in corso |
| `/resumegame` | Riprende una partita interrotta |
| `/stats` | Classifica del gruppo |

### Solo admin bot

| Comando | Descrizione |
|---|---|
| `/addteam <nome>` | Aggiunge una squadra al DB |
| `/delteam <nome>` | Rimuove una squadra dal DB |
| `/listteams` | Lista tutte le squadre |

## Setup

### Requisiti
- Docker + Docker Compose
- Un bot Telegram (crea con [@BotFather](https://t.me/BotFather))
- Il tuo Telegram user ID (es. via [@userinfobot](https://t.me/userinfobot))

### Installazione

```bash
git clone https://github.com/<tuo-user>/istinto-puro-bot
cd istinto-puro-bot

cp .env.example .env
nano .env  # inserisci BOT_TOKEN e ADMIN_ID

sudo mkdir -p /var/lib/instinto-puro-bot
docker compose up -d --build

# Popola il DB con le squadre
docker exec instinto-puro-bot python populate_teams.py
```

### .env

```
BOT_TOKEN=il_tuo_token
ADMIN_ID=il_tuo_user_id
DB_PATH=data/instinto.db
```

## Dati salvati

Il bot salva su SQLite:
- `user_id` e nome (first name Telegram) dei giocatori
- Conteggio vittorie per gruppo
- Storico mani giocate (squadre, vincitore, timestamp)

Nessun dato viene condiviso con terze parti.

## Aggiungere squadre

Il DB viene popolato con ~130 squadre tra Serie A storica, Premier League e top Europa tramite `populate_teams.py`. Puoi aggiungerne altre con `/addteam` o modificando direttamente lo script.
