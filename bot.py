import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

TOKEN = os.environ.get("BOT_TOKEN", "ВСТАВЬТЕ_ВАШ_ТОКЕН_СЮДА")
DATA_FILE = "data.json"

EXERCISES = {
    "upper-a": {
        "name": "Upper A",
        "sub": "Грудь + Спина",
        "emoji": "💪",
        "sections": [
            {"name": "Грудь", "exs": [
                {"id": "bench",   "name": "Жим штанги лёжа",                 "sets": "4 × 6–8"},
                {"id": "incline", "name": "Жим гантелей по наклонной",       "sets": "3 × 8–10"},
                {"id": "fly",     "name": "Разводка гантелей лёжа",          "sets": "3 × 12"},
            ]},
            {"name": "Спина", "exs": [
                {"id": "lat",  "name": "Тяга верхнего блока",                "sets": "4 × 8–10"},
                {"id": "tbar", "name": "Тяга Т-грифа / гантели одной рукой", "sets": "4 × 6–8"},
                {"id": "rear", "name": "Разведение бабочки",                 "sets": "3 × 15"},
            ]},
        ]
    },
    "lower": {
        "name": "Lower",
        "sub": "Ноги + Пресс",
        "emoji": "🦵",
        "sections": [
            {"name": "Квадрицепс и ягодицы", "exs": [
                {"id": "bulgarian", "name": "Болгарские сплит-приседания", "sets": "3 × 8–10"},
                {"id": "legpress",  "name": "Жим ногами",                  "sets": "3 × 10–12"},
                {"id": "legext",    "name": "Разгибание ног в тренажёре",  "sets": "3 × 12–15"},
            ]},
            {"name": "Бицепс бедра", "exs": [
                {"id": "rdl",     "name": "Румынская тяга с гантелями", "sets": "4 × 8–10"},
                {"id": "legcurl", "name": "Сгибание ног лёжа",          "sets": "3 × 12"},
            ]},
            {"name": "Икры и пресс", "exs": [
                {"id": "calfsit",  "name": "Подъём на носки сидя",  "sets": "4 × 15–20"},
                {"id": "crunch",   "name": "Скручивания на скамье", "sets": "3 × 15–20"},
                {"id": "legraise", "name": "Подъём ног в висе",     "sets": "3 × 12–15"},
            ]},
        ]
    },
    "upper-b": {
        "name": "Upper B",
        "sub": "Плечи + Руки + Спина",
        "emoji": "🏋️",
        "sections": [
            {"name": "Плечи", "exs": [
                {"id": "shoulder", "name": "Жим гантелей сидя",         "sets": "4 × 8–10"},
                {"id": "lateral",  "name": "Махи гантелей в стороны",   "sets": "3 × 12–15"},
                {"id": "upright",  "name": "Тяга гантели к подбородку", "sets": "3 × 12"},
            ]},
            {"name": "Спина (добивка)", "exs": [
                {"id": "cable",    "name": "Тяга горизонтального блока", "sets": "3 × 12"},
                {"id": "pullover", "name": "Пуловер с гантелью",         "sets": "3 × 12"},
            ]},
            {"name": "Руки", "exs": [
                {"id": "curl",     "name": "Подъём штанги на бицепс",        "sets": "3 × 10"},
                {"id": "hammer",   "name": "Молотки с гантелями",             "sets": "3 × 12"},
                {"id": "pushdown", "name": "Разгибание с канатной рукояткой", "sets": "3 × 12"},
                {"id": "french",   "name": "Французский жим с гантелями",     "sets": "3 × 10–12"},
            ]},
        ]
    },
}

# ─── data helpers ─────────────────────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, uid):
    uid = str(uid)
    if uid not in data:
        data[uid] = {"session": None, "weights": {}, "history": []}
    return data[uid]

def all_exs(day_key):
    exs = []
    for sec in EXERCISES[day_key]["sections"]:
        exs.extend(sec["exs"])
    return exs

def today_key():
    return {0: "upper-a", 2: "lower", 4: "upper-b"}.get(datetime.now().weekday())

def today_name():
    return {0: "Понедельник", 2: "Среда", 4: "Пятница"}.get(datetime.now().weekday())

def last_weight(user, ex_id):
    for entry in reversed(user["history"]):
        if ex_id in entry.get("weights", {}):
            return entry["weights"][ex_id], entry["date"]
    return None, None

def week_count(user):
    now = datetime.now()
    monday = now.replace(
        day=now.day - now.weekday(),
        hour=0, minute=0, second=0, microsecond=0
    )
    count = 0
    for h in user["history"]:
        try:
            d = datetime.strptime(h["date"], "%d.%m.%Y")
            if d >= monday:
                count += 1
        except Exception:
            pass
    return count

# ─── keyboards ────────────────────────────────────────────────────────────────

def tabs_row(active):
    icons = {"today": "🏠", "plan": "📋", "progress": "📊", "history": "📅"}
    labels = {"today": "Сегодня", "plan": "План", "progress": "Прогресс", "history": "История"}
    row = []
    for key in ["today", "plan", "progress", "history"]:
        label = f"[{icons[key]} {labels[key]}]" if key == active else f"{icons[key]} {labels[key]}"
        row.append(InlineKeyboardButton(label, callback_data=f"tab_{key}"))
    return [row]

def kb_today(day_key=None):
    rows = []
    if day_key:
        day = EXERCISES[day_key]
        rows.append([InlineKeyboardButton(
            f"{day['emoji']} Начать — {day['sub']}", callback_data=f"start_{day_key}"
        )])
        rows.append([InlineKeyboardButton("📅 Другой день", callback_data="choose_day")])
    else:
        rows.append([InlineKeyboardButton("📅 Выбрать день тренировки", callback_data="choose_day")])
    rows += tabs_row("today")
    return InlineKeyboardMarkup(rows)

def kb_choose_day():
    rows = []
    for key, day in EXERCISES.items():
        rows.append([InlineKeyboardButton(
            f"{day['emoji']}  {day['name']} — {day['sub']}", callback_data=f"start_{key}"
        )])
    rows.append([InlineKeyboardButton("← Назад", callback_data="tab_today")])
    rows += tabs_row("today")
    return InlineKeyboardMarkup(rows)

def kb_plan(day_key):
    nav = []
    keys = list(EXERCISES.keys())
    idx = keys.index(day_key)
    if idx > 0:
        prev = keys[idx - 1]
        nav.append(InlineKeyboardButton(f"◀ {EXERCISES[prev]['name']}", callback_data=f"plan_{prev}"))
    if idx < len(keys) - 1:
        nxt = keys[idx + 1]
        nav.append(InlineKeyboardButton(f"{EXERCISES[nxt]['name']} ▶", callback_data=f"plan_{nxt}"))
    rows = []
    if nav:
        rows.append(nav)
    rows += tabs_row("plan")
    return InlineKeyboardMarkup(rows)

def kb_weight(ex_id, w, ex_idx=0):
    w = w or 0
    def fmt(v): return f"{v:g}"
    rows = [
        [
            InlineKeyboardButton("−5",    callback_data=f"w_{ex_id}_-5"),
            InlineKeyboardButton("−2.5",  callback_data=f"w_{ex_id}_-2.5"),
            InlineKeyboardButton("−1.25", callback_data=f"w_{ex_id}_-1.25"),
        ],
        [
            InlineKeyboardButton(f"⚖️  {fmt(w)} кг" if w else "⚖️  без веса", callback_data="noop"),
        ],
        [
            InlineKeyboardButton("+1.25", callback_data=f"w_{ex_id}_+1.25"),
            InlineKeyboardButton("+2.5",  callback_data=f"w_{ex_id}_+2.5"),
            InlineKeyboardButton("+5",    callback_data=f"w_{ex_id}_+5"),
        ],
        [InlineKeyboardButton("✅  Записать и следующее", callback_data=f"save_{ex_id}")],
        [InlineKeyboardButton("⏭  Пропустить",           callback_data=f"skip_{ex_id}")],
    ]
    nav = []
    if ex_idx > 0:
        nav.append(InlineKeyboardButton("← Пред. упражнение", callback_data="prev_ex"))
    nav.append(InlineKeyboardButton("🚫 Завершить тренировку", callback_data="cancel_training"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)

def kb_finish():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏁  Завершить тренировку", callback_data="finish")],
        [InlineKeyboardButton("← Вернуться к упражнениям", callback_data="prev_ex")],
    ])

# ─── text builders ────────────────────────────────────────────────────────────

def text_today(user):
    dk = today_key()
    dn = today_name()
    wk = week_count(user)
    total = len(user["history"])

    if dk:
        day = EXERCISES[dk]
        header = f"📅 Сегодня *{dn}*\n\n{day['emoji']} *{day['name']} — {day['sub']}*\n\nПо расписанию. Готов начать?"
    else:
        header = "😴 Сегодня *день отдыха*\n\nТренировочные дни: пн, ср, пт\nМожешь выбрать день вручную:"

    footer = f"\n\n━━━━━━━━━━━━━━\n📊 На этой неделе: *{wk}/3*  |  Всего тренировок: *{total}*"
    return header + footer

def text_plan(day_key):
    day = EXERCISES[day_key]
    lines = [f"{day['emoji']} *{day['name']} — {day['sub']}*\n"]
    for sec in day["sections"]:
        lines.append(f"_{sec['name']}_")
        for ex in sec["exs"]:
            lines.append(f"  • {ex['name']} — _{ex['sets']}_")
        lines.append("")
    lines.append("Листай между днями ◀ ▶")
    return "\n".join(lines)

def text_progress(user):
    if not user["weights"]:
        return "📊 *Прогресс*\n\nПока нет данных.\nПроведи первую тренировку!"
    lines = ["📊 *Текущие веса*\n"]
    for day_key, day in EXERCISES.items():
        day_lines = []
        for sec in day["sections"]:
            for ex in sec["exs"]:
                w = user["weights"].get(ex["id"])
                if w:
                    day_lines.append(f"  • {ex['name']}: *{w:g} кг*")
        if day_lines:
            lines.append(f"{day['emoji']} _{day['sub']}_")
            lines.extend(day_lines)
            lines.append("")
    return "\n".join(lines)

def text_history(user):
    if not user["history"]:
        return "📅 *История*\n\nПока пусто.\nПроведи первую тренировку!"
    lines = ["📅 *История тренировок*\n"]
    for entry in reversed(user["history"][-15:]):
        day = EXERCISES.get(entry.get("day_key"), {})
        emoji = day.get("emoji", "🏋️")
        sub = day.get("sub", "Тренировка")
        logged = len(entry.get("weights", {}))
        lines.append(f"{emoji} *{entry['date']}* — {sub}")
        lines.append(f"   Упражнений записано: {logged}")
    return "\n".join(lines)

def text_exercise(user, session):
    exs = all_exs(session["day_key"])
    idx = session["ex_idx"]
    ex = exs[idx]
    total = len(exs)
    lw, ld = last_weight(user, ex["id"])

    lines = [
        f"*{ex['name']}*",
        f"_{ex['sets']}_",
        "",
        f"Упражнение {idx + 1} из {total}",
    ]
    if lw:
        lines.append(f"В прошлый раз: *{lw:g} кг* ({ld})")
    else:
        lines.append("Первый раз — выбери вес ниже")
    return "\n".join(lines)

# ─── handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    save_data(data)
    await update.message.reply_text(
        text_today(user),
        parse_mode="Markdown",
        reply_markup=kb_today(today_key())
    )

async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cb = q.data

    data = load_data()
    user = get_user(data, update.effective_user.id)

    # tabs
    if cb == "tab_today":
        await q.edit_message_text(text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key()))
        return
    if cb == "tab_plan":
        dk = today_key() or "upper-a"
        await q.edit_message_text(text_plan(dk), parse_mode="Markdown", reply_markup=kb_plan(dk))
        return
    if cb == "tab_progress":
        await q.edit_message_text(text_progress(user), parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(tabs_row("progress")))
        return
    if cb == "tab_history":
        await q.edit_message_text(text_history(user), parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(tabs_row("history")))
        return

    # plan nav
    if cb.startswith("plan_"):
        dk = cb[5:]
        await q.edit_message_text(text_plan(dk), parse_mode="Markdown", reply_markup=kb_plan(dk))
        return

    # day choice
    if cb == "choose_day":
        await q.edit_message_text("Выбери день тренировки:", reply_markup=kb_choose_day())
        return

    # start training
    if cb.startswith("start_"):
        day_key = cb[6:]
        day = EXERCISES[day_key]
        user["session"] = {"day_key": day_key, "ex_idx": 0, "weights": {}}
        save_data(data)
        ex = all_exs(day_key)[0]
        cur_w = user["weights"].get(ex["id"], 0)
        txt = f"{day['emoji']} *{day['name']} — {day['sub']}*\n\n" + text_exercise(user, user["session"])
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex["id"], cur_w, ex_idx=0))
        return

    # weight adjust
    if cb.startswith("w_"):
        parts = cb.split("_")
        ex_id = parts[1]
        delta = float(parts[2])
        cur = user["weights"].get(ex_id, 0) or 0
        new_w = max(0, round(cur + delta, 2))
        user["weights"][ex_id] = new_w
        save_data(data)
        session = user.get("session")
        if session:
            txt = text_exercise(user, session)
            await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex_id, new_w, ex_idx=session["ex_idx"]))
        return

    if cb == "noop":
        return

    # save and next
    if cb.startswith("save_"):
        ex_id = cb[5:]
        session = user.get("session")
        if not session:
            return
        w = user["weights"].get(ex_id, 0)
        session["weights"][ex_id] = w
        save_data(data)
        await advance(q, user, data, session)
        return

    # skip
    if cb.startswith("skip_"):
        session = user.get("session")
        if not session:
            return
        await advance(q, user, data, session)
        return

    # prev exercise
    if cb == "prev_ex":
        session = user.get("session")
        if not session:
            await q.edit_message_text(text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key()))
            return
        prev_idx = max(0, session["ex_idx"] - 1)
        session["ex_idx"] = prev_idx
        save_data(data)
        exs = all_exs(session["day_key"])
        ex = exs[prev_idx]
        txt = text_exercise(user, session)
        cur_w = user["weights"].get(ex["id"], 0)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex["id"], cur_w, ex_idx=prev_idx))
        return

    # cancel training
    if cb == "cancel_training":
        user["session"] = None
        save_data(data)
        await q.edit_message_text(
            "❌ Тренировка отменена.\n\nВеса которые ты уже ввёл — сохранены.",
            parse_mode="Markdown",
            reply_markup=kb_today(today_key())
        )
        return

    # finish
    if cb == "finish":
        session = user.get("session")
        if not session:
            return
        date_str = datetime.now().strftime("%d.%m.%Y")
        user["history"].append({
            "date": date_str,
            "day_key": session["day_key"],
            "weights": session.get("weights", {})
        })
        user["session"] = None
        save_data(data)
        day = EXERCISES[session["day_key"]]
        logged = len(session.get("weights", {}))
        await q.edit_message_text(
            f"🏆 *Тренировка завершена!*\n\n{day['emoji']} {day['sub']}\nЗаписано упражнений: *{logged}*\n\nОтличная работа! 💪",
            parse_mode="Markdown",
            reply_markup=kb_today(today_key())
        )
        return

async def advance(q, user, data, session):
    exs = all_exs(session["day_key"])
    next_idx = session["ex_idx"] + 1
    if next_idx >= len(exs):
        save_data(data)
        await q.edit_message_text("✅ *Все упражнения пройдены!*\n\nЗавершить тренировку?",
                                   parse_mode="Markdown", reply_markup=kb_finish())
        return
    session["ex_idx"] = next_idx
    save_data(data)
    ex = exs[next_idx]
    txt = text_exercise(user, session)
    cur_w = user["weights"].get(ex["id"], 0)
    await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex["id"], cur_w, ex_idx=next_idx))

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    session = user.get("session")
    text = update.message.text.strip()
    if session:
        try:
            w = float(text.replace(",", "."))
            exs = all_exs(session["day_key"])
            ex = exs[session["ex_idx"]]
            user["weights"][ex["id"]] = w
            session["weights"][ex["id"]] = w
            save_data(data)
            await update.message.reply_text(
                f"✅ *{ex['name']}*: {w:g} кг записано\n\nНажми кнопку на предыдущем сообщении 👆",
                parse_mode="Markdown"
            )
            return
        except Exception:
            pass
    await update.message.reply_text("Напиши /start чтобы открыть меню 👇")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
