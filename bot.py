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

DEFAULT_EXERCISES = {
    "upper-a": {
        "name": "Upper A",
        "sub": "Грудь + Спина",
        "emoji": "💪",
        "sections": [
            {"name": "Грудь", "exs": [
                {"id": "bench",   "name": "Жим штанги лёжа",                  "sets": "4 × 6–8"},
                {"id": "incline", "name": "Жим гантелей по наклонной",        "sets": "3 × 8–10"},
                {"id": "fly",     "name": "Разводка гантелей лёжа",           "sets": "3 × 12"},
            ]},
            {"name": "Спина", "exs": [
                {"id": "lat",  "name": "Тяга верхнего блока",                 "sets": "4 × 8–10"},
                {"id": "tbar", "name": "Тяга Т-грифа / гантели одной рукой",  "sets": "4 × 6–8"},
                {"id": "rear", "name": "Разведение бабочки",                  "sets": "3 × 15"},
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

# ─── data ─────────────────────────────────────────────────────────────────────

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
        data[uid] = {"session": None, "weights": {}, "history": [], "exercises": None}
    if "exercises" not in data[uid]:
        data[uid]["exercises"] = None
    return data[uid]

def get_exercises(user):
    if user.get("exercises"):
        return user["exercises"]
    import copy
    return copy.deepcopy(DEFAULT_EXERCISES)

def all_exs(exercises, day_key):
    exs = []
    for sec in exercises[day_key]["sections"]:
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
    monday = now.replace(day=now.day - now.weekday(), hour=0, minute=0, second=0, microsecond=0)
    count = 0
    for h in user["history"]:
        try:
            d = datetime.strptime(h["date"], "%d.%m.%Y")
            if d >= monday:
                count += 1
        except Exception:
            pass
    return count

def make_ex_id(name):
    import hashlib
    return "custom_" + hashlib.md5(name.encode()).hexdigest()[:8]

# ─── keyboards ────────────────────────────────────────────────────────────────

def tabs_row(active):
    icons  = {"today": "🏠", "plan": "📋", "progress": "📊", "history": "📅"}
    labels = {"today": "Сегодня", "plan": "План", "progress": "Прогресс", "history": "История"}
    row = []
    for key in ["today", "plan", "progress", "history"]:
        label = f"[{icons[key]} {labels[key]}]" if key == active else f"{icons[key]} {labels[key]}"
        row.append(InlineKeyboardButton(label, callback_data=f"tab_{key}"))
    return [row]

def kb_today(day_key=None):
    rows = []
    if day_key:
        day = DEFAULT_EXERCISES[day_key]
        rows.append([InlineKeyboardButton(f"{day['emoji']} Начать — {day['sub']}", callback_data=f"start_{day_key}")])
        rows.append([InlineKeyboardButton("📅 Другой день", callback_data="choose_day")])
    else:
        rows.append([InlineKeyboardButton("📅 Выбрать день тренировки", callback_data="choose_day")])
    rows += tabs_row("today")
    return InlineKeyboardMarkup(rows)

def kb_choose_day():
    rows = []
    for key, day in DEFAULT_EXERCISES.items():
        rows.append([InlineKeyboardButton(f"{day['emoji']}  {day['name']} — {day['sub']}", callback_data=f"start_{key}")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="tab_today")])
    rows += tabs_row("today")
    return InlineKeyboardMarkup(rows)

def kb_plan(day_key, exercises):
    keys = list(exercises.keys())
    idx = keys.index(day_key)
    nav = []
    if idx > 0:
        prev = keys[idx - 1]
        nav.append(InlineKeyboardButton(f"◀ {exercises[prev]['name']}", callback_data=f"plan_{prev}"))
    if idx < len(keys) - 1:
        nxt = keys[idx + 1]
        nav.append(InlineKeyboardButton(f"{exercises[nxt]['name']} ▶", callback_data=f"plan_{nxt}"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("✏️ Редактировать упражнения", callback_data=f"edit_day_{day_key}")])
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
        [InlineKeyboardButton(f"⚖️  {fmt(w)} кг" if w else "⚖️  без веса", callback_data="noop")],
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
        nav.append(InlineKeyboardButton("← Пред.", callback_data="prev_ex"))
    nav.append(InlineKeyboardButton("🚫 Отменить", callback_data="cancel_training"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)

def kb_finish():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏁  Завершить тренировку", callback_data="finish")],
        [InlineKeyboardButton("← Вернуться к упражнениям", callback_data="prev_ex")],
    ])

def kb_summary(day_key, exercises):
    exs = all_exs(exercises, day_key)
    rows = []
    for ex in exs:
        rows.append([InlineKeyboardButton(f"✏️ {ex['name']}", callback_data=f"edit_w_{ex['id']}")])
    rows.append([InlineKeyboardButton("🏁 Сохранить и завершить", callback_data="finish")])
    rows.append([InlineKeyboardButton("← Назад к тренировке",    callback_data="back_to_train")])
    return InlineKeyboardMarkup(rows)

def kb_edit_day(day_key, exercises):
    exs = all_exs(exercises, day_key)
    rows = []
    for ex in exs:
        rows.append([
            InlineKeyboardButton(f"❌ {ex['name']}", callback_data=f"del_ex_{day_key}_{ex['id']}"),
        ])
    rows.append([InlineKeyboardButton(f"➕ Добавить упражнение в {exercises[day_key]['name']}", callback_data=f"add_ex_{day_key}")])
    rows.append([InlineKeyboardButton("← Назад к плану", callback_data=f"plan_{day_key}")])
    return InlineKeyboardMarkup(rows)

def kb_add_ex_day():
    rows = []
    for key, day in DEFAULT_EXERCISES.items():
        rows.append([InlineKeyboardButton(f"{day['emoji']} {day['name']} — {day['sub']}", callback_data=f"add_ex_{key}")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="tab_plan")])
    return InlineKeyboardMarkup(rows)

# ─── text builders ────────────────────────────────────────────────────────────

def text_today(user):
    dk = today_key()
    dn = today_name()
    wk = week_count(user)
    total = len(user["history"])
    if dk:
        day = DEFAULT_EXERCISES[dk]
        header = f"📅 Сегодня *{dn}*\n\n{day['emoji']} *{day['name']} — {day['sub']}*\n\nПо расписанию. Готов начать?"
    else:
        header = "😴 Сегодня *день отдыха*\n\nТренировочные дни: пн, ср, пт\nМожешь выбрать день вручную:"
    footer = f"\n\n━━━━━━━━━━━━━━\n📊 На этой неделе: *{wk}/3*  |  Всего: *{total}*"
    return header + footer

def text_plan(day_key, exercises):
    day = exercises[day_key]
    lines = [f"{day['emoji']} *{day['name']} — {day['sub']}*\n"]
    for sec in day["sections"]:
        lines.append(f"_{sec['name']}_")
        for ex in sec["exs"]:
            lines.append(f"  • {ex['name']} — _{ex['sets']}_")
        lines.append("")
    lines.append("Листай между днями ◀ ▶")
    return "\n".join(lines)

def text_progress(user):
    exercises = get_exercises(user)
    if not user["weights"]:
        return "📊 *Прогресс*\n\nПока нет данных.\nПроведи первую тренировку!"
    lines = ["📊 *Текущие веса*\n"]
    for day_key, day in exercises.items():
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
    exercises = get_exercises(user)
    if not user["history"]:
        return "📅 *История*\n\nПока пусто.\nПроведи первую тренировку!"
    lines = ["📅 *История тренировок*\n"]
    for entry in reversed(user["history"][-15:]):
        day = exercises.get(entry.get("day_key"), {})
        emoji = day.get("emoji", "🏋️")
        sub = day.get("sub", "Тренировка")
        logged = len(entry.get("weights", {}))
        lines.append(f"{emoji} *{entry['date']}* — {sub}")
        lines.append(f"   Упражнений: {logged}")
    return "\n".join(lines)

def text_exercise(user, session, exercises):
    exs = all_exs(exercises, session["day_key"])
    idx = session["ex_idx"]
    ex = exs[idx]
    total = len(exs)
    lw, ld = last_weight(user, ex["id"])
    cur_w = user["weights"].get(ex["id"], 0)
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
    lines.append("")
    lines.append("_Или просто напиши число в чат_")
    return "\n".join(lines)

def text_summary(session, user, exercises):
    day = exercises[session["day_key"]]
    exs = all_exs(exercises, session["day_key"])
    lines = [f"📋 *Итог тренировки*\n{day['emoji']} {day['sub']}\n"]
    for ex in exs:
        w = session["weights"].get(ex["id"])
        lw, _ = last_weight(user, ex["id"])
        if w:
            diff = ""
            if lw and lw != w:
                delta = round(w - lw, 2)
                diff = f"  {'📈 +' if delta > 0 else '📉 '}{delta:g} кг"
            lines.append(f"✅ *{ex['name']}*: {w:g} кг{diff}")
        else:
            lines.append(f"⏭ _{ex['name']}_: пропущено")
    lines.append("\nНажми на упражнение чтобы изменить вес, или завершай тренировку.")
    return "\n".join(lines)

# ─── handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    is_new = len(user["history"]) == 0 and not user["weights"]
    save_data(data)

    if is_new:
        welcome = (
            "👋 Привет! Я твой личный тренировочный бот.\n\n"
            "🗓 *Твой план:* Upper A / Lower / Upper B — 3 дня в неделю (пн, ср, пт)\n\n"
            "💪 *Что я умею:*\n"
            "• Веду тебя по упражнениям шаг за шагом\n"
            "• Показываю вес который ты делал в прошлый раз\n"
            "• Слежу за прогрессом по каждому упражнению\n"
            "• Показываю итог тренировки в конце\n"
            "• Позволяю добавлять и удалять упражнения\n"
            "• Храню всю историю тренировок\n\n"
            "📲 *Как пользоваться:*\n"
            "Нажми «Начать» — бот предложит нужный день по расписанию. "
            "Во время тренировки выбирай вес кнопками или просто пиши число в чат.\n\n"
            "Готов? 🚀"
        )
        await update.message.reply_text(
            welcome,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Начать работу", callback_data="go_home")]
            ])
        )
    else:
        await update.message.reply_text(
            text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key())
        )

async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cb = q.data
    data = load_data()
    user = get_user(data, update.effective_user.id)
    exercises = get_exercises(user)

    # ── welcome → home ────────────────────────────────────────────────────────
    if cb == "go_home":
        await q.edit_message_text(text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key()))
        return

    # ── tabs ──────────────────────────────────────────────────────────────────
    if cb == "tab_today":
        user["session"] = None
        save_data(data)
        await q.edit_message_text(text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key()))
        return

    if cb == "tab_plan":
        dk = today_key() or "upper-a"
        await q.edit_message_text(text_plan(dk, exercises), parse_mode="Markdown", reply_markup=kb_plan(dk, exercises))
        return

    if cb == "tab_progress":
        await q.edit_message_text(text_progress(user), parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(tabs_row("progress")))
        return

    if cb == "tab_history":
        await q.edit_message_text(text_history(user), parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(tabs_row("history")))
        return

    # ── plan nav ──────────────────────────────────────────────────────────────
    if cb.startswith("plan_"):
        dk = cb[5:]
        await q.edit_message_text(text_plan(dk, exercises), parse_mode="Markdown", reply_markup=kb_plan(dk, exercises))
        return

    # ── choose day ────────────────────────────────────────────────────────────
    if cb == "choose_day":
        await q.edit_message_text("Выбери день тренировки:", reply_markup=kb_choose_day())
        return

    # ── start training ────────────────────────────────────────────────────────
    if cb.startswith("start_"):
        day_key = cb[6:]
        day = exercises[day_key]
        user["session"] = {"day_key": day_key, "ex_idx": 0, "weights": {}, "msg_mode": "train"}
        save_data(data)
        ex = all_exs(exercises, day_key)[0]
        cur_w = user["weights"].get(ex["id"], 0)
        txt = f"{day['emoji']} *{day['name']} — {day['sub']}*\n\n" + text_exercise(user, user["session"], exercises)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex["id"], cur_w, ex_idx=0))
        return

    # ── weight adjust buttons ─────────────────────────────────────────────────
    if cb.startswith("w_"):
        parts = cb.split("_")
        ex_id = parts[1]
        delta = float(parts[2])
        cur = user["weights"].get(ex_id, 0) or 0
        new_w = max(0, round(cur + delta, 2))
        user["weights"][ex_id] = new_w
        # also update session weights if active
        session = user.get("session")
        if session and session.get("msg_mode") == "train":
            session["weights"][ex_id] = new_w
        save_data(data)
        if session:
            txt = text_exercise(user, session, exercises)
            await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex_id, new_w, ex_idx=session["ex_idx"]))
        return

    if cb == "noop":
        return

    # ── save and next ─────────────────────────────────────────────────────────
    if cb.startswith("save_"):
        ex_id = cb[5:]
        session = user.get("session")
        if not session:
            return
        w = user["weights"].get(ex_id, 0)
        session["weights"][ex_id] = w
        save_data(data)
        await advance(q, user, data, session, exercises)
        return

    # ── skip ──────────────────────────────────────────────────────────────────
    if cb.startswith("skip_"):
        session = user.get("session")
        if not session:
            return
        save_data(data)
        await advance(q, user, data, session, exercises)
        return

    # ── prev exercise ─────────────────────────────────────────────────────────
    if cb == "prev_ex":
        session = user.get("session")
        if not session:
            await q.edit_message_text(text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key()))
            return
        prev_idx = max(0, session["ex_idx"] - 1)
        session["ex_idx"] = prev_idx
        session["msg_mode"] = "train"
        save_data(data)
        exs = all_exs(exercises, session["day_key"])
        ex = exs[prev_idx]
        txt = text_exercise(user, session, exercises)
        cur_w = user["weights"].get(ex["id"], 0)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex["id"], cur_w, ex_idx=prev_idx))
        return

    # ── back to train (from summary) ──────────────────────────────────────────
    if cb == "back_to_train":
        session = user.get("session")
        if not session:
            await q.edit_message_text(text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key()))
            return
        exs = all_exs(exercises, session["day_key"])
        last_idx = len(exs) - 1
        session["ex_idx"] = last_idx
        session["msg_mode"] = "train"
        save_data(data)
        ex = exs[last_idx]
        txt = text_exercise(user, session, exercises)
        cur_w = user["weights"].get(ex["id"], 0)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex["id"], cur_w, ex_idx=last_idx))
        return

    # ── cancel training ───────────────────────────────────────────────────────
    if cb == "cancel_training":
        user["session"] = None
        save_data(data)
        await q.edit_message_text(
            "❌ Тренировка отменена.\n\nВведённые веса сохранены.",
            parse_mode="Markdown",
            reply_markup=kb_today(today_key())
        )
        return

    # ── show summary ──────────────────────────────────────────────────────────
    if cb == "show_summary":
        session = user.get("session")
        if not session:
            return
        txt = text_summary(session, user, exercises)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_summary(session["day_key"], exercises))
        return

    # ── edit weight from summary ──────────────────────────────────────────────
    if cb.startswith("edit_w_"):
        ex_id = cb[7:]
        session = user.get("session")
        if not session:
            return
        # find ex index
        exs = all_exs(exercises, session["day_key"])
        idx = next((i for i, e in enumerate(exs) if e["id"] == ex_id), 0)
        session["ex_idx"] = idx
        session["msg_mode"] = "edit"
        save_data(data)
        ex = exs[idx]
        cur_w = user["weights"].get(ex_id, 0)
        txt = f"✏️ *Редактирование веса*\n\n*{ex['name']}*\n_{ex['sets']}_\n\n_Или напиши число в чат_"
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight_edit(ex_id, cur_w))
        return

    # ── save edited weight and back to summary ────────────────────────────────
    if cb.startswith("save_edit_"):
        ex_id = cb[10:]
        session = user.get("session")
        if not session:
            return
        w = user["weights"].get(ex_id, 0)
        session["weights"][ex_id] = w
        save_data(data)
        txt = text_summary(session, user, exercises)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_summary(session["day_key"], exercises))
        return

    # ── finish ────────────────────────────────────────────────────────────────
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
        day = exercises[session["day_key"]]
        logged = len(session.get("weights", {}))
        await q.edit_message_text(
            f"🏆 *Тренировка завершена!*\n\n{day['emoji']} {day['sub']}\nЗаписано упражнений: *{logged}*\n\nОтличная работа! 💪",
            parse_mode="Markdown",
            reply_markup=kb_today(today_key())
        )
        return

    # ── edit exercises in plan ────────────────────────────────────────────────
    if cb.startswith("edit_day_"):
        day_key = cb[9:]
        txt = (
            f"✏️ *Редактировать — {exercises[day_key]['name']}*\n\n"
            "Нажми ❌ рядом с упражнением чтобы удалить его.\n"
            "Или добавь новое снизу."
        )
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_edit_day(day_key, exercises))
        return

    # ── delete exercise ───────────────────────────────────────────────────────
    if cb.startswith("del_ex_"):
        parts = cb[7:].split("_", 1)
        day_key = parts[0]
        ex_id = parts[1]
        if user["exercises"] is None:
            import copy
            user["exercises"] = copy.deepcopy(DEFAULT_EXERCISES)
        day = user["exercises"][day_key]
        for sec in day["sections"]:
            sec["exs"] = [e for e in sec["exs"] if e["id"] != ex_id]
        save_data(data)
        exercises = get_exercises(user)
        txt = (
            f"✏️ *Редактировать — {exercises[day_key]['name']}*\n\n"
            "Нажми ❌ рядом с упражнением чтобы удалить его.\n"
            "Или добавь новое снизу."
        )
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_edit_day(day_key, exercises))
        return

    # ── add exercise: choose day ──────────────────────────────────────────────
    if cb.startswith("add_ex_"):
        day_key = cb[7:]
        user["session"] = {"msg_mode": "adding_ex", "target_day": day_key}
        save_data(data)
        await q.edit_message_text(
            f"➕ *Добавить упражнение в {exercises[day_key]['name']}*\n\n"
            "Напиши название упражнения и количество подходов в чат.\n\n"
            "Пример:\n`Подтягивания, 4 × 10`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Отмена", callback_data=f"edit_day_{day_key}")]])
        )
        return

# ─── weight keyboard for edit mode ───────────────────────────────────────────

def kb_weight_edit(ex_id, w):
    w = w or 0
    def fmt(v): return f"{v:g}"
    rows = [
        [
            InlineKeyboardButton("−5",    callback_data=f"w_{ex_id}_-5"),
            InlineKeyboardButton("−2.5",  callback_data=f"w_{ex_id}_-2.5"),
            InlineKeyboardButton("−1.25", callback_data=f"w_{ex_id}_-1.25"),
        ],
        [InlineKeyboardButton(f"⚖️  {fmt(w)} кг" if w else "⚖️  без веса", callback_data="noop")],
        [
            InlineKeyboardButton("+1.25", callback_data=f"w_{ex_id}_+1.25"),
            InlineKeyboardButton("+2.5",  callback_data=f"w_{ex_id}_+2.5"),
            InlineKeyboardButton("+5",    callback_data=f"w_{ex_id}_+5"),
        ],
        [InlineKeyboardButton("✅ Сохранить и вернуться к итогу", callback_data=f"save_edit_{ex_id}")],
    ]
    return InlineKeyboardMarkup(rows)

# ─── advance ─────────────────────────────────────────────────────────────────

async def advance(q, user, data, session, exercises):
    exs = all_exs(exercises, session["day_key"])
    next_idx = session["ex_idx"] + 1
    if next_idx >= len(exs):
        session["msg_mode"] = "summary"
        save_data(data)
        txt = text_summary(session, user, exercises)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_summary(session["day_key"], exercises))
        return
    session["ex_idx"] = next_idx
    session["msg_mode"] = "train"
    save_data(data)
    ex = exs[next_idx]
    txt = text_exercise(user, session, exercises)
    cur_w = user["weights"].get(ex["id"], 0)
    await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex["id"], cur_w, ex_idx=next_idx))

# ─── text handler ─────────────────────────────────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    exercises = get_exercises(user)
    session = user.get("session")
    text = update.message.text.strip()

    # adding new exercise
    if session and session.get("msg_mode") == "adding_ex":
        day_key = session["target_day"]
        parts = [p.strip() for p in text.split(",", 1)]
        ex_name = parts[0]
        ex_sets = parts[1] if len(parts) > 1 else "3 × 10"
        ex_id = make_ex_id(ex_name)

        if user["exercises"] is None:
            import copy
            user["exercises"] = copy.deepcopy(DEFAULT_EXERCISES)

        # add to last section
        new_ex = {"id": ex_id, "name": ex_name, "sets": ex_sets}
        user["exercises"][day_key]["sections"][-1]["exs"].append(new_ex)
        user["session"] = None
        save_data(data)
        exercises = get_exercises(user)
        await update.message.reply_text(
            f"✅ Упражнение *{ex_name}* добавлено в {exercises[day_key]['name']}!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"← Назад к плану", callback_data=f"plan_{day_key}")]
            ])
        )
        return

    # manual weight input during training or edit
    if session and session.get("msg_mode") in ("train", "edit"):
        try:
            w = float(text.replace(",", "."))
            exs = all_exs(exercises, session["day_key"])
            ex = exs[session["ex_idx"]]
            user["weights"][ex["id"]] = w
            session["weights"][ex["id"]] = w
            save_data(data)

            if session.get("msg_mode") == "edit":
                await update.message.reply_text(
                    f"✅ *{ex['name']}*: {w:g} кг сохранено\n\nНажми кнопку выше 👆",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"✅ *{ex['name']}*: {w:g} кг записано\n\nНажми *«Записать и следующее»* выше 👆",
                    parse_mode="Markdown"
                )
            return
        except Exception:
            pass

    await update.message.reply_text("Напиши /start чтобы открыть меню 👇")

# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
