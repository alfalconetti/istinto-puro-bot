# Istinto Puro Bot 🎯⚽

Bot Telegram per giocare a **Istinto Puro** in gruppo — due giocatori trovano un calciatore che ha giocato in entrambe le squadre sorteggiate.

## Funzionalità

- Partite al meglio di X punti (default 3)
- Squadre sorteggiate automaticamente o scelte dai giocatori
- Sorteggio intelligente: favorisce coppie dello stesso campionato
- Pool di squadre personalizzabile per ogni gruppo
- Ready check prima di ogni mano con countdown animato
- Arbitraggio a fiducia con bottoni (solo i giocatori possono votare)
- `/resumegame` per riprendere partite interrotte dopo un riavvio
- Classifica per win% con win assolute come tiebreaker
- Storico completo di ogni mano su SQLite

## Arbitraggio

La validazione delle risposte è **manuale e a fiducia**. Non esiste un sistema automatico per verificare se un calciatore ha davvero giocato in entrambe le squadre — gestire varianti di nomi, prestiti, carriere storiche e dati aggiornati richiederebbe un'integrazione con database esterni costantemente aggiornati, con margini di errore comunque elevati.

I giocatori arbitrano da soli tramite bottoni inline: assegnano il punto a chi ha risposto correttamente o skippano la mano se nessuno ha risposto bene. Il sistema funziona sulla fiducia tra i giocatori.

## Comandi

| Comando | Descrizione |
|---|---|
| `/newgame [punti]` | Avvia una nuova partita (default 3 punti) |
| `/cancelgame` | Annulla la partita in corso |
| `/resumegame` | Riprende una partita interrotta |
| `/stats` | Classifica del gruppo per win% |

### Admin del gruppo

| Comando | Descrizione |
|---|---|
| `/addteam <nome>` | Aggiunge una squadra al pool del gruppo |
| `/delteam <nome>` | Esclude una squadra dal pool del gruppo |
| `/listteams` | Mostra il pool attivo e le modifiche rispetto al globale |

### Solo admin bot

| Comando | Descrizione |
|---|---|
| `/adminaddteam <nome> \| <campionato>` | Aggiunge una squadra al DB globale |
| `/admindelteam <nome>` | Rimuove una squadra dal DB globale |
| `/adminlistteams` | Lista tutte le squadre globali per campionato |

## Setup

### Requisiti
- Docker + Docker Compose
- Un bot Telegram (crea con [@BotFather](https://t.me/BotFather))
- Il tuo Telegram user ID (es. via [@userinfobot](https://t.me/userinfobot))

### Installazione

```bash
git clone https://github.com/alfalconetti/istinto-puro-bot
cd istinto-puro-bot

cp .env.example .env
nano .env  # inserisci BOT_TOKEN e ADMIN_ID

sudo mkdir -p /var/lib/instinto-puro-bot
docker compose up -d --build

# Popola il DB con le squadre
docker exec instinto-puro-bot python populate_teams.py

# Assegna i campionati alle squadre
docker exec instinto-puro-bot python populate_leagues.py
```

### .env

```
BOT_TOKEN=il_tuo_token
ADMIN_ID=il_tuo_user_id
DB_PATH=data/instinto.db
```

## Pool squadre

Il DB parte con ~70 squadre tra Serie A, Premier League, La Liga, Bundesliga, Ligue 1 e altri campionati europei. Ogni gruppo può personalizzare il proprio pool aggiungendo o escludendo squadre tramite `/addteam` e `/delteam` senza toccare il DB globale.

## Dati salvati

Il bot salva su SQLite:
- `user_id` e nome dei giocatori
- Storico partite e mani giocate (squadre, vincitore, timestamp)
- Vittorie per gruppo per la classifica

Nessun dato viene condiviso con terze parti.
