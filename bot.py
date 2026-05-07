import os
import json
import re
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

TOKEN = os.environ.get("BOT_TOKEN", "ВСТАВЬТЕ_ВАШ_ТОКЕН_СЮДА")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
DATA_FILE = "/data/data.json"

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
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
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
    labels = {"today": "Сегодня", "plan": "План", "progress": "Прогресс", "history": "История"}
    row = []
    for key in ["today", "plan", "progress", "history"]:
        label = f"[ {labels[key]} ]" if key == active else labels[key]
        row.append(InlineKeyboardButton(label, callback_data=f"tab_{key}"))
    return [row]

def kb_today(day_key=None):
    rows = []
    if day_key:
        day = DEFAULT_EXERCISES[day_key]
        rows.append([InlineKeyboardButton(f"Начать тренировку — {day['sub']}", callback_data=f"start_{day_key}")])
        rows.append([InlineKeyboardButton("Выбрать другой день", callback_data="choose_day")])
    else:
        rows.append([InlineKeyboardButton("Выбрать день тренировки", callback_data="choose_day")])
    rows += tabs_row("today")
    return InlineKeyboardMarkup(rows)

def kb_choose_day():
    rows = []
    for key, day in DEFAULT_EXERCISES.items():
        rows.append([InlineKeyboardButton(f"{day['name']} — {day['sub']}", callback_data=f"start_{key}")])
    rows.append([InlineKeyboardButton("Назад", callback_data="tab_today")])
    rows += tabs_row("today")
    return InlineKeyboardMarkup(rows)

def kb_plan(day_key, exercises):
    keys = list(exercises.keys())
    idx = keys.index(day_key)
    nav = []
    if idx > 0:
        prev = keys[idx - 1]
        nav.append(InlineKeyboardButton(f"← {exercises[prev]['name']}", callback_data=f"plan_{prev}"))
    if idx < len(keys) - 1:
        nxt = keys[idx + 1]
        nav.append(InlineKeyboardButton(f"{exercises[nxt]['name']} →", callback_data=f"plan_{nxt}"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("Редактировать упражнения", callback_data=f"edit_day_{day_key}")])
    rows += tabs_row("plan")
    return InlineKeyboardMarkup(rows)

def kb_pick_exercise(day_key, exercises, done_ids):
    exs = all_exs(exercises, day_key)
    rows = []
    for ex in exs:
        done = ex["id"] in done_ids
        label = f"[Сделано] {ex['name']}" if done else ex["name"]
        rows.append([InlineKeyboardButton(label, callback_data=f"pick_{ex['id']}")])
    remaining = [e for e in exs if e["id"] not in done_ids]
    if not remaining:
        rows.append([InlineKeyboardButton("Все сделаны — перейти к итогу", callback_data="show_summary")])
    else:
        rows.append([InlineKeyboardButton("Перейти к итогу и завершить", callback_data="show_summary")])
    rows.append([InlineKeyboardButton("Отменить тренировку", callback_data="cancel_training")])
    return InlineKeyboardMarkup(rows)

def kb_weight(ex_id, w, ex_idx=0):
    w = w or 0
    def fmt(v): return f"{v:g}"
    rows = [
        [
            InlineKeyboardButton("−5 кг",    callback_data=f"w_{ex_id}_-5"),
            InlineKeyboardButton("−2.5 кг",  callback_data=f"w_{ex_id}_-2.5"),
            InlineKeyboardButton("−1.25 кг", callback_data=f"w_{ex_id}_-1.25"),
        ],
        [InlineKeyboardButton(f"Текущий вес: {fmt(w)} кг" if w else "Текущий вес: без веса", callback_data="noop")],
        [
            InlineKeyboardButton("+1.25 кг", callback_data=f"w_{ex_id}_+1.25"),
            InlineKeyboardButton("+2.5 кг",  callback_data=f"w_{ex_id}_+2.5"),
            InlineKeyboardButton("+5 кг",    callback_data=f"w_{ex_id}_+5"),
        ],
        [InlineKeyboardButton("Записать и вернуться к списку", callback_data=f"save_{ex_id}")],
        [InlineKeyboardButton("Пропустить упражнение",         callback_data=f"skip_{ex_id}")],
        [InlineKeyboardButton("Назад к списку упражнений",     callback_data="pick_list")],
    ]
    return InlineKeyboardMarkup(rows)

def kb_finish():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Завершить тренировку", callback_data="finish")],
        [InlineKeyboardButton("Назад к упражнениям",  callback_data="prev_ex")],
    ])

def kb_summary(day_key, exercises, session):
    exs = all_exs(exercises, day_key)
    rows = []
    for ex in exs:
        w = session["weights"].get(ex["id"])
        if w:
            label = f"Изменить: {ex['name']}"
        else:
            label = f"Добавить: {ex['name']} (пропущено)"
        rows.append([InlineKeyboardButton(label, callback_data=f"edit_w_{ex['id']}")])
    rows.append([InlineKeyboardButton("Записать тренировку", callback_data="finish")])
    rows.append([InlineKeyboardButton("Назад к упражнениям", callback_data="back_to_train")])
    return InlineKeyboardMarkup(rows)

def kb_edit_day(day_key, exercises):
    exs = all_exs(exercises, day_key)
    rows = []
    for ex in exs:
        rows.append([InlineKeyboardButton(f"Удалить: {ex['name']}", callback_data=f"del_ex_{day_key}_{ex['id']}")])
    rows.append([InlineKeyboardButton(f"Добавить упражнение в {exercises[day_key]['name']}", callback_data=f"add_ex_{day_key}")])
    rows.append([InlineKeyboardButton("Назад к плану", callback_data=f"plan_{day_key}")])
    return InlineKeyboardMarkup(rows)

def kb_add_ex_day():
    rows = []
    for key, day in DEFAULT_EXERCISES.items():
        rows.append([InlineKeyboardButton(f"{day['name']} — {day['sub']}", callback_data=f"add_ex_{key}")])
    rows.append([InlineKeyboardButton("Назад", callback_data="tab_plan")])
    return InlineKeyboardMarkup(rows)


# ─── groq ─────────────────────────────────────────────────────────────────────

async def ask_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        return "Groq API ключ не настроен."
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.7,
            }
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]

async def generate_plan_with_groq(profile: dict) -> str:
    goal_map = {"muscle": "набрать мышечную массу", "lose": "похудеть", "tone": "общий тонус и здоровье"}
    level_map = {"beginner": "новичок (нет опыта)", "middle": "средний уровень (1-2 года)", "advanced": "продвинутый (3+ лет)"}
    days_map = {"2": "2 дня", "3": "3 дня", "4": "4 дня"}
    place_map = {"gym": "тренажёрный зал (полное оборудование)", "home": "дома (гантели/турник)", "any": "зал или дома"}

    goal = goal_map.get(profile.get("goal", ""), profile.get("goal", ""))
    level = level_map.get(profile.get("level", ""), profile.get("level", ""))
    days = days_map.get(profile.get("days", ""), profile.get("days", ""))
    place = place_map.get(profile.get("place", ""), profile.get("place", ""))
    injuries = profile.get("injuries", "нет")

    prompt = f"""Ты профессиональный тренер. Составь план тренировок на основе данных пользователя.

Данные:
- Цель: {goal}
- Уровень: {level}
- Дней в неделю: {days}
- Место: {place}
- Травмы/ограничения: {injuries}

Составь чёткий план тренировок. Для каждого дня укажи название и список упражнений с подходами и повторениями.
Формат ответа — только план, без лишних слов. Пиши на русском языке.
Пример формата:
День 1 — Грудь и Спина:
• Жим штанги лёжа — 4 × 6-8
• Тяга верхнего блока — 4 × 8-10

День 2 — Ноги:
• Приседания — 4 × 8
...

В конце добавь 2-3 совета специально под цель этого пользователя."""

    return await ask_groq(prompt)

# ─── onboarding keyboards ──────────────────────────────────────────────────────

def kb_onboard_goal():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Набрать мышцы",  callback_data="ob_goal_muscle")],
        [InlineKeyboardButton("Похудеть",        callback_data="ob_goal_lose")],
        [InlineKeyboardButton("Общий тонус",     callback_data="ob_goal_tone")],
    ])

def kb_onboard_level():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Новичок — первый раз в зале",    callback_data="ob_level_beginner")],
        [InlineKeyboardButton("Средний — занимался раньше",     callback_data="ob_level_middle")],
        [InlineKeyboardButton("Продвинутый — занимаюсь давно", callback_data="ob_level_advanced")],
    ])

def kb_onboard_days():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("2 дня в неделю", callback_data="ob_days_2"),
         InlineKeyboardButton("3 дня в неделю", callback_data="ob_days_3"),
         InlineKeyboardButton("4 дня в неделю", callback_data="ob_days_4")],
    ])

def kb_onboard_place():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Тренажёрный зал",    callback_data="ob_place_gym")],
        [InlineKeyboardButton("Дома (гантели/турник)", callback_data="ob_place_home")],
        [InlineKeyboardButton("Зал или дома",        callback_data="ob_place_any")],
    ])

def kb_onboard_injuries():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Нет ограничений",        callback_data="ob_inj_none")],
        [InlineKeyboardButton("Есть — напишу в чат",    callback_data="ob_inj_type")],
    ])

def kb_plan_accept():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Принять этот план и начать", callback_data="ob_accept")],
        [InlineKeyboardButton("Использовать стандартный план", callback_data="ob_default")],
    ])



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
    lines = ["📊 *Текущие веса*\n", "_Нажми ❌ рядом с упражнением чтобы сбросить вес_\n"]
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

def kb_progress(user):
    exercises = get_exercises(user)
    rows = []
    for day_key, day in exercises.items():
        for sec in day["sections"]:
            for ex in sec["exs"]:
                w = user["weights"].get(ex["id"])
                if w:
                    rows.append([InlineKeyboardButton(
                        f"Сбросить вес: {ex['name']} — {w:g} кг",
                        callback_data=f"del_weight_{ex['id']}"
                    )])
    rows += tabs_row("progress")
    return InlineKeyboardMarkup(rows)

def text_history(user):
    exercises = get_exercises(user)
    if not user["history"]:
        return "📅 *История тренировок*\n\nПока пусто.\nПроведи первую тренировку!"
    lines = ["📅 *История тренировок*\n", "_Нажми ❌ чтобы удалить запись_\n"]
    history = user["history"][-15:]
    for i, entry in enumerate(reversed(history)):
        real_idx = len(history) - 1 - i
        day = exercises.get(entry.get("day_key"), {})
        emoji = day.get("emoji", "🏋️")
        sub = day.get("sub", "Тренировка")
        logged = len(entry.get("weights", {}))
        lines.append(f"{emoji} *{entry['date']}* — {sub}  |  упражнений: {logged}")
    return "\n".join(lines)

def kb_history(user):
    exercises = get_exercises(user)
    history = user["history"][-15:]
    rows = []
    for i, entry in enumerate(reversed(history)):
        real_idx = len(user["history"]) - 1 - i
        day = exercises.get(entry.get("day_key"), {})
        sub = day.get("sub", "Тренировка")
        rows.append([InlineKeyboardButton(
            f"Удалить: {entry['date']} — {sub}",
            callback_data=f"del_hist_{real_idx}"
        )])
    rows += tabs_row("history")
    return InlineKeyboardMarkup(rows)

def text_exercise(user, session, exercises):
    exs = all_exs(exercises, session["day_key"])
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
    lines.append("")
    lines.append("_Или просто напиши число в чат_")
    lines.append("")
    lines.append("💡 _Не переживай — в конце тренировки можно изменить вес, подходы и повторения_")
    return "\n".join(lines)

def text_summary(session, user, exercises):
    day = exercises[session["day_key"]]
    exs = all_exs(exercises, session["day_key"])
    lines = [
        f"📋 *Проверьте результаты тренировки*",
        f"{day['emoji']} {day['sub']}",
        "",
        "Всё верно? Нажми на упражнение чтобы изменить вес, подходы или повторения.\n",
    ]
    for ex in exs:
        w = session["weights"].get(ex["id"])
        sets_done = session.get("sets_done", {}).get(ex["id"], ex["sets"])
        lw, _ = last_weight(user, ex["id"])
        if w:
            diff = ""
            if lw and lw != w:
                delta = round(w - lw, 2)
                diff = f"  {'📈 +' if delta > 0 else '📉 '}{delta:g} кг"
            lines.append(f"✅ *{ex['name']}*")
            lines.append(f"   ⚖️ {w:g} кг  |  🔢 {sets_done}{diff}")
        else:
            lines.append(f"⏭ _{ex['name']}_: пропущено")
    lines.append("")
    lines.append("Когда всё проверено — нажми *«Записать тренировку»*")
    return "\n".join(lines)

def text_edit_ex_summary(ex, session):
    w = session["weights"].get(ex["id"], 0)
    sets_done = session.get("sets_done", {}).get(ex["id"], ex["sets"])
    lines = [
        f"✏️ *Редактирование — {ex['name']}*",
        "",
        f"Текущий вес: *{w:g} кг*" if w else "Текущий вес: *без веса*",
        f"Подходы/повторения: *{sets_done}*",
        "",
        "_Измени вес кнопками или напиши число в чат_",
        "_Для изменения подходов напиши например:_ `4 × 8`",
    ]
    return "\n".join(lines)

# ─── handlers ─────────────────────────────────────────────────────────────────

async def generate_and_show_plan(q, user, data):
    session = user.get("session") or {}
    profile = session.get("profile", {})
    try:
        plan_text = await generate_plan_with_groq(profile)
    except Exception as e:
        plan_text = f"Не удалось получить ответ от ИИ: {e}"

    user["session"] = {"msg_mode": "onboarding_review", "profile": profile, "ai_plan": plan_text}
    save_data(data)

    await q.edit_message_text(
        f"*Вот твой персональный план:*\n\n{plan_text}\n\n"
        "─────────────────\n"
        "Принять этот план или использовать стандартный?",
        parse_mode="Markdown",
        reply_markup=kb_plan_accept()
    )


    data = load_data()
    user = get_user(data, update.effective_user.id)
    is_new = len(user["history"]) == 0 and not user["weights"] and not user.get("onboarded")
    save_data(data)

    if is_new:
        user["session"] = {"msg_mode": "onboarding", "profile": {}}
        save_data(data)
        await update.message.reply_text(
            "👋 Привет! Я твой личный тренировочный бот.\n\n"
            "Прежде чем начать, давай составим план *именно под тебя*. "
            "Отвечай на вопросы кнопками — займёт меньше минуты.\n\n"
            "*Какова твоя цель?*",
            parse_mode="Markdown",
            reply_markup=kb_onboard_goal()
        )
    else:
        await update.message.reply_text(
            text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key())
        )

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    is_new = len(user["history"]) == 0 and not user["weights"] and not user.get("onboarded")
    save_data(data)

    if is_new:
        user["session"] = {"msg_mode": "onboarding", "profile": {}}
        save_data(data)
        await update.message.reply_text(
            "👋 Привет! Я твой личный тренировочный бот.\n\n"
            "Прежде чем начать, давай составим план *именно под тебя*. "
            "Отвечай на вопросы кнопками — займёт меньше минуты.\n\n"
            "*Какова твоя цель?*",
            parse_mode="Markdown",
            reply_markup=kb_onboard_goal()
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

    # ── onboarding ────────────────────────────────────────────────────────────
    if cb.startswith("ob_goal_"):
        goal = cb[8:]
        session = user.get("session") or {"msg_mode": "onboarding", "profile": {}}
        session["profile"]["goal"] = goal
        user["session"] = session
        save_data(data)
        await q.edit_message_text(
            "Отлично! Теперь скажи — *какой у тебя уровень подготовки?*",
            parse_mode="Markdown",
            reply_markup=kb_onboard_level()
        )
        return

    if cb.startswith("ob_level_"):
        level = cb[9:]
        session = user.get("session") or {"msg_mode": "onboarding", "profile": {}}
        session["profile"]["level"] = level
        user["session"] = session
        save_data(data)
        await q.edit_message_text(
            "Понял! *Сколько дней в неделю готов тренироваться?*",
            parse_mode="Markdown",
            reply_markup=kb_onboard_days()
        )
        return

    if cb.startswith("ob_days_"):
        days = cb[8:]
        session = user.get("session") or {"msg_mode": "onboarding", "profile": {}}
        session["profile"]["days"] = days
        user["session"] = session
        save_data(data)
        await q.edit_message_text(
            "Хорошо! *Где планируешь тренироваться?*",
            parse_mode="Markdown",
            reply_markup=kb_onboard_place()
        )
        return

    if cb.startswith("ob_place_"):
        place = cb[9:]
        session = user.get("session") or {"msg_mode": "onboarding", "profile": {}}
        session["profile"]["place"] = place
        user["session"] = session
        save_data(data)
        await q.edit_message_text(
            "Почти готово! *Есть ли травмы или ограничения которые нужно учесть?*",
            parse_mode="Markdown",
            reply_markup=kb_onboard_injuries()
        )
        return

    if cb == "ob_inj_none":
        session = user.get("session") or {"msg_mode": "onboarding", "profile": {}}
        session["profile"]["injuries"] = "нет"
        user["session"] = session
        save_data(data)
        await q.edit_message_text(
            "Составляю твой персональный план тренировок...\n\n_Это займёт несколько секунд_ ⏳",
            parse_mode="Markdown"
        )
        await generate_and_show_plan(q, user, data)
        return

    if cb == "ob_inj_type":
        session = user.get("session") or {"msg_mode": "onboarding", "profile": {}}
        session["msg_mode"] = "onboarding_injuries"
        user["session"] = session
        save_data(data)
        await q.edit_message_text(
            "Напиши в чат какие есть травмы или ограничения.\n\n_Например: болит колено, проблемы с поясницей_",
            parse_mode="Markdown"
        )
        return

    if cb == "ob_accept":
        user["onboarded"] = True
        user["session"] = None
        save_data(data)
        await q.edit_message_text(
            "Отлично! План сохранён. Можешь в любой момент изменить упражнения во вкладке «План».\n\n"
            "Удачных тренировок! 💪",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Перейти к тренировкам", callback_data="go_home")]])
        )
        return

    if cb == "ob_default":
        user["onboarded"] = True
        user["session"] = None
        save_data(data)
        await q.edit_message_text(
            "Хорошо, используем стандартный план Upper A / Lower / Upper B.\n\n"
            "Можешь настроить упражнения во вкладке «План». Удачи! 💪",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Перейти к тренировкам", callback_data="go_home")]])
        )
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
        if user["weights"]:
            await q.edit_message_text(text_progress(user), parse_mode="Markdown",
                                       reply_markup=kb_progress(user))
        else:
            await q.edit_message_text(text_progress(user), parse_mode="Markdown",
                                       reply_markup=InlineKeyboardMarkup(tabs_row("progress")))
        return

    # ── delete weight for exercise ────────────────────────────────────────────
    if cb.startswith("del_weight_"):
        ex_id = cb[11:]
        exercises = get_exercises(user)
        ex_name = next(
            (e["name"] for dk in exercises for sec in exercises[dk]["sections"] for e in sec["exs"] if e["id"] == ex_id),
            ex_id
        )
        user["weights"].pop(ex_id, None)
        save_data(data)
        await q.answer(f"Сброшено: {ex_name}", show_alert=False)
        if user["weights"]:
            await q.edit_message_text(text_progress(user), parse_mode="Markdown",
                                       reply_markup=kb_progress(user))
        else:
            await q.edit_message_text(
                "📊 *Прогресс*\n\nПока нет данных.\nПроведи первую тренировку!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(tabs_row("progress"))
            )
        return

    if cb == "tab_history":
        await q.edit_message_text(text_history(user), parse_mode="Markdown",
                                   reply_markup=kb_history(user))
        return

    # ── delete history entry ──────────────────────────────────────────────────
    if cb.startswith("del_hist_"):
        idx = int(cb[9:])
        if 0 <= idx < len(user["history"]):
            deleted = user["history"].pop(idx)
            save_data(data)
            day = get_exercises(user).get(deleted.get("day_key"), {})
            sub = day.get("sub", "тренировка")
            await q.answer(f"Удалено: {deleted['date']} — {sub}", show_alert=False)
        if user["history"]:
            await q.edit_message_text(text_history(user), parse_mode="Markdown",
                                       reply_markup=kb_history(user))
        else:
            await q.edit_message_text(
                "📅 *История тренировок*\n\nПока пусто.\nПроведи первую тренировку!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(tabs_row("history"))
            )
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
        user["session"] = {"day_key": day_key, "ex_idx": 0, "weights": {}, "msg_mode": "pick"}
        save_data(data)
        done_ids = set()
        txt = (
            f"{day['emoji']} *{day['name']} — {day['sub']}*\n\n"
            "Выбери упражнение которое хочешь сделать сейчас.\n"
            "Можешь делать в любом порядке 👇"
        )
        await q.edit_message_text(txt, parse_mode="Markdown",
                                   reply_markup=kb_pick_exercise(day_key, exercises, done_ids))
        return

    # ── pick list (back to exercise picker) ───────────────────────────────────
    if cb == "pick_list":
        session = user.get("session")
        if not session:
            await q.edit_message_text(text_today(user), parse_mode="Markdown", reply_markup=kb_today(today_key()))
            return
        day_key = session["day_key"]
        day = exercises[day_key]
        done_ids = set(session.get("weights", {}).keys())
        txt = (
            f"{day['emoji']} *{day['name']} — {day['sub']}*\n\n"
            "Выбери следующее упражнение 👇"
        )
        await q.edit_message_text(txt, parse_mode="Markdown",
                                   reply_markup=kb_pick_exercise(day_key, exercises, done_ids))
        return

    # ── pick specific exercise ────────────────────────────────────────────────
    if cb.startswith("pick_"):
        ex_id = cb[5:]
        session = user.get("session")
        if not session:
            return
        exs = all_exs(exercises, session["day_key"])
        idx = next((i for i, e in enumerate(exs) if e["id"] == ex_id), 0)
        session["ex_idx"] = idx
        session["msg_mode"] = "train"
        save_data(data)
        ex = exs[idx]
        cur_w = user["weights"].get(ex["id"], 0)
        txt = text_exercise(user, session, exercises)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight(ex["id"], cur_w, ex_idx=idx))
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
        day_key = session["day_key"]
        day = exercises[day_key]
        done_ids = set(session.get("weights", {}).keys())
        session["msg_mode"] = "pick"
        save_data(data)
        txt = (
            f"{day['emoji']} *{day['name']} — {day['sub']}*\n\n"
            "Выбери упражнение 👇"
        )
        await q.edit_message_text(txt, parse_mode="Markdown",
                                   reply_markup=kb_pick_exercise(day_key, exercises, done_ids))
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
        session["msg_mode"] = "summary"
        save_data(data)
        txt = text_summary(session, user, exercises)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_summary(session["day_key"], exercises, session))
        return

    # ── edit weight/sets from summary ─────────────────────────────────────────
    if cb.startswith("edit_w_"):
        ex_id = cb[7:]
        session = user.get("session")
        if not session:
            return
        exs = all_exs(exercises, session["day_key"])
        idx = next((i for i, e in enumerate(exs) if e["id"] == ex_id), 0)
        session["ex_idx"] = idx
        session["msg_mode"] = "edit"
        save_data(data)
        ex = exs[idx]
        cur_w = session["weights"].get(ex_id, 0) or user["weights"].get(ex_id, 0)
        txt = text_edit_ex_summary(ex, session)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight_edit(ex_id, cur_w))
        return

    # ── weight adjust in edit mode (we_ prefix) ───────────────────────────────
    if cb.startswith("we_"):
        parts = cb.split("_")
        ex_id = parts[1]
        delta = float(parts[2])
        session = user.get("session")
        if not session:
            return
        cur = session["weights"].get(ex_id, 0) or user["weights"].get(ex_id, 0) or 0
        new_w = max(0, round(cur + delta, 2))
        session["weights"][ex_id] = new_w
        user["weights"][ex_id] = new_w
        save_data(data)
        exs = all_exs(exercises, session["day_key"])
        ex = next((e for e in exs if e["id"] == ex_id), None)
        if ex:
            txt = text_edit_ex_summary(ex, session)
            await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_weight_edit(ex_id, new_w))
        return

    # ── save edited weight and back to summary ────────────────────────────────
    if cb.startswith("save_edit_"):
        ex_id = cb[10:]
        session = user.get("session")
        if not session:
            return
        w = session["weights"].get(ex_id, 0)
        user["weights"][ex_id] = w
        save_data(data)
        txt = text_summary(session, user, exercises)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_summary(session["day_key"], exercises, session))
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
            "weights": session.get("weights", {}),
            "sets_done": session.get("sets_done", {}),
        })
        user["session"] = None
        save_data(data)
        day = exercises[session["day_key"]]
        logged = len(session.get("weights", {}))
        await q.edit_message_text(
            f"🏆 *Тренировка записана!*\n\n{day['emoji']} {day['sub']}\nЗаписано упражнений: *{logged}*\n\nОтличная работа! 💪",
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
            InlineKeyboardButton("−5 кг",    callback_data=f"we_{ex_id}_-5"),
            InlineKeyboardButton("−2.5 кг",  callback_data=f"we_{ex_id}_-2.5"),
            InlineKeyboardButton("−1.25 кг", callback_data=f"we_{ex_id}_-1.25"),
        ],
        [InlineKeyboardButton(f"Текущий вес: {fmt(w)} кг" if w else "Текущий вес: без веса", callback_data="noop")],
        [
            InlineKeyboardButton("+1.25 кг", callback_data=f"we_{ex_id}_+1.25"),
            InlineKeyboardButton("+2.5 кг",  callback_data=f"we_{ex_id}_+2.5"),
            InlineKeyboardButton("+5 кг",    callback_data=f"we_{ex_id}_+5"),
        ],
        [InlineKeyboardButton("Сохранить и вернуться к итогу", callback_data=f"save_edit_{ex_id}")],
        [InlineKeyboardButton("Назад к итогу без изменений",   callback_data="show_summary")],
    ]
    return InlineKeyboardMarkup(rows)

# ─── advance ─────────────────────────────────────────────────────────────────

async def advance(q, user, data, session, exercises):
    day_key = session["day_key"]
    exs = all_exs(exercises, day_key)
    done_ids = set(session.get("weights", {}).keys())
    remaining = [e for e in exs if e["id"] not in done_ids]

    if not remaining:
        session["msg_mode"] = "summary"
        save_data(data)
        txt = text_summary(session, user, exercises)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_summary(day_key, exercises, session))
        return

    session["msg_mode"] = "pick"
    save_data(data)
    day = exercises[day_key]
    done_count = len(done_ids)
    total = len(exs)
    txt = (
        f"{day['emoji']} *{day['name']} — {day['sub']}*\n\n"
        f"Сделано: {done_count}/{total}\n\n"
        "Выбери следующее упражнение 👇"
    )
    await q.edit_message_text(txt, parse_mode="Markdown",
                               reply_markup=kb_pick_exercise(day_key, exercises, done_ids))


# ─── text handler ─────────────────────────────────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    exercises = get_exercises(user)
    session = user.get("session")
    text = update.message.text.strip()

    # onboarding — typing injuries
    if session and session.get("msg_mode") == "onboarding_injuries":
        session["profile"]["injuries"] = text
        session["msg_mode"] = "onboarding"
        user["session"] = session
        save_data(data)
        msg = await update.message.reply_text(
            "Составляю твой персональный план тренировок...\n\n_Это займёт несколько секунд_ ⏳",
            parse_mode="Markdown"
        )

        profile = session.get("profile", {})
        try:
            plan_text = await generate_plan_with_groq(profile)
        except Exception as e:
            plan_text = f"Не удалось получить ответ от ИИ: {e}"

        user["session"] = {"msg_mode": "onboarding_review", "profile": profile, "ai_plan": plan_text}
        save_data(data)

        await msg.edit_text(
            f"*Вот твой персональный план:*\n\n{plan_text}\n\n"
            "─────────────────\n"
            "Принять этот план или использовать стандартный?",
            parse_mode="Markdown",
            reply_markup=kb_plan_accept()
        )
        return


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

    # manual weight or sets input during training or edit
    if session and session.get("msg_mode") in ("train", "edit"):
        exs = all_exs(exercises, session["day_key"])
        ex = exs[session["ex_idx"]]

        # check if it's a sets pattern like "4 × 8" or "4x8" or "3 × 10-12"
        sets_pattern = re.match(r"^(\d+\s*[x×хХ]\s*[\d\-–]+)$", text.strip())
        if sets_pattern and session.get("msg_mode") == "edit":
            if "sets_done" not in session:
                session["sets_done"] = {}
            session["sets_done"][ex["id"]] = text.strip()
            save_data(data)
            await update.message.reply_text(
                f"✅ *{ex['name']}*: подходы обновлены на *{text.strip()}*\n\nНажми «Сохранить» выше 👆",
                parse_mode="Markdown"
            )
            return

        # otherwise try parsing as weight
        try:
            w = float(text.replace(",", "."))
            user["weights"][ex["id"]] = w
            session["weights"][ex["id"]] = w
            save_data(data)
            if session.get("msg_mode") == "edit":
                await update.message.reply_text(
                    f"✅ *{ex['name']}*: {w:g} кг сохранено\n\nНажми «Сохранить» выше 👆",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"✅ *{ex['name']}*: {w:g} кг\n\nНажми *«Записать»* выше 👆",
                    parse_mode="Markdown"
                )
            return
        except Exception:
            pass

        await update.message.reply_text(
            "Напиши вес числом (например *80*) или подходы (например *4 × 8*)",
            parse_mode="Markdown"
        )
        return

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
