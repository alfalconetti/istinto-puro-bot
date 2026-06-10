import asyncio
import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest

import database as db
from game import (
    Game, GameState, Player,
    create_game, get_game, remove_game, restore_game,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID  = int(os.environ["ADMIN_ID"])


# ── Helpers ────────────────────────────────────────────────────────────────

def is_player(game: Game, user_id: int) -> bool:
    return game.get_player(user_id) is not None


async def safe_delete(context: ContextTypes.DEFAULT_TYPE, chat_id: int, msg_id: int | None):
    if msg_id is None:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except BadRequest:
        pass


# ── Game flow ──────────────────────────────────────────────────────────────

async def send_ready_check(game: Game, context: ContextTypes.DEFAULT_TYPE):
    game.state = GameState.READY_CHECK
    game.ready = set()
    db.save_game(game)

    kb = [[InlineKeyboardButton("✅ Sono pronto!", callback_data="ready")]]
    msg = await context.bot.send_message(
        chat_id=game.chat_id,
        text=f"⚽ Mano {game.hand_num} — Premete entrambi per iniziare!\n\n"
             f"{game.players[0].username} — ⏳\n"
             f"{game.players[1].username} — ⏳",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    game.ready_msg_id = msg.message_id


async def start_countdown(game: Game, context: ContextTypes.DEFAULT_TYPE):
    game.state = GameState.COUNTDOWN
    await safe_delete(context, game.chat_id, game.ready_msg_id)

    msg = await context.bot.send_message(chat_id=game.chat_id, text="3️⃣")
    game.countdown_msg_id = msg.message_id

    for digit in ("2️⃣", "1️⃣", "🟢 VIA!"):
        await asyncio.sleep(1)
        try:
            await context.bot.edit_message_text(
                digit, chat_id=game.chat_id, message_id=msg.message_id
            )
        except BadRequest:
            pass

    await start_hand(game, context)


async def start_hand(game: Game, context: ContextTypes.DEFAULT_TYPE):
    if game.auto_teams:
        pair = db.get_two_random_teams()
        if pair is None:
            await context.bot.send_message(
                chat_id=game.chat_id,
                text="❌ Non ci sono abbastanza squadre nel database! Aggiungine con /addteam.",
            )
            remove_game(game.chat_id)
            return

        game.team_a, game.team_b = pair
        game.state = GameState.WAITING_ANSWER
        db.save_game(game)

        await context.bot.send_message(
            chat_id=game.chat_id,
            text=f"🏟 *{game.team_a}* ⚔️ *{game.team_b}*\n\n"
                 f"Dite un calciatore che ha giocato in entrambe!\n\n"
                 f"{game.score_line()}",
            parse_mode="Markdown",
        )
        await asyncio.sleep(15)
        # Controlla che la partita esista ancora e sia nello stesso stato
        # (potrebbe essere stata cancellata nel frattempo)
        current = get_game(game.chat_id)
        if current and current.state == GameState.WAITING_ANSWER:
            await send_judging(game, context)
    else:
        game.team_a = ""
        game.team_b = ""
        game.team_a_owner = ""
        game.state = GameState.WAITING_ANSWER
        db.save_game(game)

        p1, p2 = game.players
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=f"📝 {p1.username} e {p2.username}: scrivete ognuno una squadra!\n\n"
                 f"(Prima uno, poi l'altro)",
        )


async def send_judging(game: Game, context: ContextTypes.DEFAULT_TYPE):
    game.state = GameState.JUDGING
    db.save_game(game)

    p1, p2 = game.players
    kb = [
        [
            InlineKeyboardButton(f"🥇 {p1.username}", callback_data=f"point_{p1.user_id}"),
            InlineKeyboardButton(f"🥇 {p2.username}", callback_data=f"point_{p2.user_id}"),
        ],
        [InlineKeyboardButton("🤝 Nessuno (skip)", callback_data="point_none")],
    ]
    msg = await context.bot.send_message(
        chat_id=game.chat_id,
        text=f"🏟 *{game.team_a}* ⚔️ *{game.team_b}*\n\n"
             f"Chi ha risposto correttamente?\n\n"
             f"{game.score_line()}",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )
    game.judging_msg_id = msg.message_id


async def assign_point(game: Game, context: ContextTypes.DEFAULT_TYPE, winner_id: int | None):
    await safe_delete(context, game.chat_id, game.judging_msg_id)

    # Salva la mano nel DB
    if game.db_id:
        db.save_hand(game.db_id, game.hand_num, game.team_a, game.team_b, winner_id)

    if winner_id is not None:
        player = game.get_player(winner_id)
        player.score += 1
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=f"✅ Punto a *{player.username}*!\n\n{game.score_line()}",
            parse_mode="Markdown",
        )
    else:
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=f"⏭ Mano annullata.\n\n{game.score_line()}",
        )

    winner = game.winner()
    if winner:
        await end_game(game, context, winner)
    else:
        await asyncio.sleep(1)
        game.hand_num += 1
        await send_ready_check(game, context)


async def end_game(game: Game, context: ContextTypes.DEFAULT_TYPE, winner: Player):
    game.state = GameState.GAME_OVER
    db.save_game(game)
    db.add_win(game.chat_id, winner.user_id, winner.username)

    lb = db.get_leaderboard(game.chat_id)
    lb_text = "\n".join(
        f"{'🥇' if i == 0 else '🥈' if i == 1 else '🥉' if i == 2 else '▫️'} "
        f"{r['username']}: {r['wins']} vitt."
        for i, r in enumerate(lb)
    )

    await context.bot.send_message(
        chat_id=game.chat_id,
        text=f"🏆 *{winner.username} ha vinto la partita!*\n\n"
             f"{game.score_line()}\n\n"
             f"📊 *Classifica del gruppo:*\n{lb_text}",
        parse_mode="Markdown",
    )
    remove_game(game.chat_id)


# ── Command handlers ───────────────────────────────────────────────────────

async def cmd_newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if get_game(chat_id):
        await update.message.reply_text(
            "⚠️ C'è già una partita in corso! Usa /cancelgame per annullarla."
        )
        return

    target_score = 3
    auto_teams   = True

    for arg in (context.args or []):
        if arg.isdigit():
            target_score = max(1, int(arg))
        elif arg.lower() == "manual":
            auto_teams = False
        elif arg.lower() == "auto":
            auto_teams = True

    game = create_game(chat_id, target_score, auto_teams)

    mode_label = "🎲 Squadre automatiche" if auto_teams else "✍️ Squadre scelte dai giocatori"
    kb = [[InlineKeyboardButton("⚽ Unisciti!", callback_data="join")]]
    msg = await update.message.reply_text(
        f"🆕 *Nuova partita — Istinto Puro!*\n\n"
        f"🏆 Punti per vincere: *{target_score}*\n"
        f"{mode_label}\n\n"
        f"In attesa di 2 giocatori... (0/2)",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )
    game.lobby_msg_id = msg.message_id


async def cmd_cancelgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    if not game:
        await update.message.reply_text("Nessuna partita in corso.")
        return
    if game.db_id:
        db.mark_game_cancelled(game.db_id)
    remove_game(chat_id)
    await update.message.reply_text("❌ Partita annullata.")


async def cmd_resumegame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    #if get_game(chat_id):
    #   await update.message.reply_text(
    #       "⚠️ C'è già una partita attiva in memoria. Usa /cancelgame prima se vuoi ricominciare."
    #    )
    #   return

    row = db.load_active_game(chat_id)
    if not row:
        await update.message.reply_text("Nessuna partita da riprendere per questo gruppo.")
        return

    # Ricostruisce l'oggetto Game dal DB
    p1 = Player(user_id=row["player1_id"], username=row["player1_name"], score=row["score1"])
    p2 = Player(user_id=row["player2_id"], username=row["player2_name"], score=row["score2"])

    game = Game(
        chat_id=chat_id,
        target_score=row["target_score"],
        auto_teams=bool(row["auto_teams"]),
        players=[p1, p2],
        db_id=row["id"],
    )
    # Calcola hand_num dal numero di mani già giocate
    with db.get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as c FROM hands WHERE game_id=?", (row["id"],)
        ).fetchone()["c"]
    game.hand_num = count + 1

    restore_game(chat_id, game)

    await update.message.reply_text(
        f"♻️ *Partita ripresa!*\n\n"
        f"⚽ {p1.username} vs {p2.username}\n"
        f"{game.score_line()}\n\n"
        f"Ripartiamo dalla mano {game.hand_num}...",
        parse_mode="Markdown",
    )
    await asyncio.sleep(1)
    await send_ready_check(game, context)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lb = db.get_leaderboard(chat_id)
    if not lb:
        await update.message.reply_text("Nessuna statistica ancora per questo gruppo.")
        return
    text = "📊 *Classifica del gruppo:*\n\n"
    for i, r in enumerate(lb):
        emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "▫️"
        text += f"{emoji} {r['username']}: {r['wins']} vitt.\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_addteam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Uso: /addteam <nome squadra>")
        return
    name = " ".join(context.args)
    if db.add_team(name):
        await update.message.reply_text(f"✅ Squadra aggiunta: *{name}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ *{name}* è già nel database.", parse_mode="Markdown")


async def cmd_delteam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Uso: /delteam <nome squadra>")
        return
    name = " ".join(context.args)
    if db.del_team(name):
        await update.message.reply_text(f"🗑 Squadra rimossa: *{name}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Squadra non trovata: *{name}*", parse_mode="Markdown")


async def cmd_listteams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    teams = db.get_all_teams()
    if not teams:
        await update.message.reply_text("Nessuna squadra nel database.")
        return
    text = "🏟 *Squadre nel database:*\n\n" + "\n".join(f"• {t}" for t in teams)
    await update.message.reply_text(text, parse_mode="Markdown")


# ── Callback handlers ──────────────────────────────────────────────────────

async def cb_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user    = query.from_user
    chat_id = query.message.chat_id
    game    = get_game(chat_id)

    if not game or game.state != GameState.LOBBY:
        return
    if game.get_player(user.id):
        await query.answer("Sei già nella partita!", show_alert=True)
        return
    if game.is_full:
        await query.answer("Partita già piena!", show_alert=True)
        return

    game.players.append(Player(user_id=user.id, username=user.first_name))

    if game.is_full:
        # Salva la partita nel DB ora che abbiamo entrambi i giocatori
        game.db_id = db.save_game(game)
        game.hand_num = 1

        await safe_delete(context, chat_id, game.lobby_msg_id)
        p1, p2 = game.players
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Giocatori pronti:\n⚽ {p1.username} vs {p2.username}\n\nInizio tra poco...",
        )
        await asyncio.sleep(1)
        await send_ready_check(game, context)
    else:
        kb = [[InlineKeyboardButton("⚽ Unisciti!", callback_data="join")]]
        try:
            await query.edit_message_text(
                f"🆕 *Nuova partita — Istinto Puro!*\n\n"
                f"🏆 Punti per vincere: *{game.target_score}*\n"
                f"{'🎲 Squadre automatiche' if game.auto_teams else '✍️ Squadre manuali'}\n\n"
                f"✅ {game.players[0].username} si è unito!\n"
                f"In attesa di un altro giocatore... (1/2)",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown",
            )
        except BadRequest:
            pass


async def cb_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user    = query.from_user
    chat_id = query.message.chat_id
    game    = get_game(chat_id)

    if not game or game.state != GameState.READY_CHECK:
        return
    if not is_player(game, user.id):
        await query.answer("Non sei un giocatore in questa partita!", show_alert=True)
        return

    game.ready.add(user.id)

    p1, p2 = game.players
    kb = [[InlineKeyboardButton("✅ Sono pronto!", callback_data="ready")]]
    try:
        await query.edit_message_text(
            f"⚽ Mano {game.hand_num} — Premete entrambi per iniziare!\n\n"
            f"{p1.username} — {'✅' if p1.user_id in game.ready else '⏳'}\n"
            f"{p2.username} — {'✅' if p2.user_id in game.ready else '⏳'}",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    except BadRequest:
        pass

    if game.both_ready:
        await asyncio.sleep(0.5)
        await start_countdown(game, context)


async def cb_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user    = query.from_user
    chat_id = query.message.chat_id
    game    = get_game(chat_id)

    if not game or game.state != GameState.JUDGING:
        return
    if not is_player(game, user.id):
        await query.answer("Solo i giocatori possono assegnare i punti!", show_alert=True)
        return

    data = query.data
    if data == "point_none":
        await assign_point(game, context, winner_id=None)
    else:
        winner_id = int(data.split("_")[1])
        if game.get_player(winner_id) is None:
            return
        await assign_point(game, context, winner_id=winner_id)


# ── Message handler (squadre in modalità manual) ───────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game    = get_game(chat_id)

    if not game or game.state != GameState.WAITING_ANSWER or game.auto_teams:
        return
    if not is_player(game, update.effective_user.id):
        return

    text = update.message.text.strip()

    if not game.team_a:
        game.team_a       = text
        game.team_a_owner = update.effective_user.first_name
        await update.message.reply_text(
            f"✅ Prima squadra: *{text}*\nOra l'altro giocatore scriva la sua!",
            parse_mode="Markdown",
        )
    elif not game.team_b:
        # Solo l'altro giocatore può scrivere la seconda squadra
        owner_id = next(
            p.user_id for p in game.players if p.username == game.team_a_owner
        )
        if update.effective_user.id == owner_id:
            await update.message.reply_text("Aspetta che l'altro giocatore scriva la sua squadra!")
            return

        game.team_b = text
        await update.message.reply_text(
            f"🏟 *{game.team_a}* ⚔️ *{game.team_b}*\n\n"
            f"Dite un calciatore che ha giocato in entrambe!\n\n"
            f"{game.score_line()}",
            parse_mode="Markdown",
        )
        await asyncio.sleep(15)
        current = get_game(chat_id)
        if current and current.state == GameState.WAITING_ANSWER:
            await send_judging(game, context)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("newgame",    cmd_newgame))
    app.add_handler(CommandHandler("cancelgame", cmd_cancelgame))
    app.add_handler(CommandHandler("resumegame", cmd_resumegame))
    app.add_handler(CommandHandler("stats",      cmd_stats))
    app.add_handler(CommandHandler("addteam",    cmd_addteam))
    app.add_handler(CommandHandler("delteam",    cmd_delteam))
    app.add_handler(CommandHandler("listteams",  cmd_listteams))

    app.add_handler(CallbackQueryHandler(cb_join,  pattern="^join$"))
    app.add_handler(CallbackQueryHandler(cb_ready, pattern="^ready$"))
    app.add_handler(CallbackQueryHandler(cb_point, pattern="^point_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Instinto Puro bot avviato.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
