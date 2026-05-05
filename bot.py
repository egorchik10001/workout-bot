import os
import json
import re
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

TOKEN = os.environ.get("BOT_TOKEN", "ВСТАВЬТЕ_ВАШ_ТОКЕН_СЮДА")
DATA_FILE = "data.json"

EXERCISES = {
    "upper-a": {
        "name": "День 1 — Upper A (Грудь + Спина)",
        "exercises": [
            "Жим штанги лёжа",
            "Жим гантелей по наклонной",
            "Разводка гантелей лёжа",
            "Тяга верхнего блока",
            "Тяга Т-грифа / гантели одной рукой",
            "Разведение бабочки",
        ]
    },
    "lower": {
        "name": "День 2 — Lower (Ноги + Пресс)",
        "exercises": [
            "Болгарские сплит-приседания",
            "Жим ногами",
            "Разгибание ног в тренажёре",
            "Румынская тяга с гантелями",
            "Сгибание ног лёжа",
            "Подъём на носки сидя",
            "Скручивания на скамье",
            "Подъём ног в висе",
        ]
    },
    "upper-b": {
        "name": "День 3 — Upper B (Плечи + Руки + Спина)",
        "exercises": [
            "Жим гантелей сидя",
            "Махи гантелей в стороны",
            "Тяга гантели к подбородку",
            "Тяга горизонтального блока",
            "Пуловер с гантелью",
            "Подъём штанги на бицепс",
            "Молотки с гантелями",
            "Разгибание с канатной рукояткой",
            "Французский жим с гантелями",
        ]
    }
}

SETS_INFO = {
    "Жим штанги лёжа": "4 × 6–8",
    "Жим гантелей по наклонной": "3 × 8–10",
    "Разводка гантелей лёжа": "3 × 12",
    "Тяга верхнего блока": "4 × 8–10",
    "Тяга Т-грифа / гантели одной рукой": "4 × 6–8",
    "Разведение бабочки": "3 × 15",
    "Болгарские сплит-приседания": "3 × 8–10 на каждую",
    "Жим ногами": "3 × 10–12",
    "Разгибание ног в тренажёре": "3 × 12–15",
    "Румынская тяга с гантелями": "4 × 8–10",
    "Сгибание ног лёжа": "3 × 12",
    "Подъём на носки сидя": "4 × 15–20",
    "Скручивания на скамье": "3 × 15–20",
    "Подъём ног в висе": "3 × 12–15",
    "Жим гантелей сидя": "4 × 8–10",
    "Махи гантелей в стороны": "3 × 12–15",
    "Тяга гантели к подбородку": "3 × 12",
    "Тяга горизонтального блока": "3 × 12",
    "Пуловер с гантелью": "3 × 12",
    "Подъём штанги на бицепс": "3 × 10",
    "Молотки с гантелями": "3 × 12",
    "Разгибание с канатной рукояткой": "3 × 12",
    "Французский жим с гантелями": "3 × 10–12",
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"session": None, "weights": {}, "history": []}
    return data[uid]

def today_day_name():
    dow = datetime.now().weekday()
    names = {0: "Понедельник", 2: "Среда", 4: "Пятница"}
    return names.get(dow)

def today_day_key():
    dow = datetime.now().weekday()
    keys = {0: "upper-a", 2: "lower", 4: "upper-b"}
    return keys.get(dow)

def get_last_weight(user, exercise_name):
    for entry in reversed(user["history"]):
        if exercise_name in entry.get("weights", {}):
            return entry["weights"][exercise_name], entry["date"]
    return None, None

def make_keyboard(items, cols=2):
    rows = []
    for i in range(0, len(items), cols):
        rows.append([KeyboardButton(x) for x in items[i:i+cols]])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    save_data(data)
    text = (
        "Привет! Я твой тренировочный бот 💪\n\n"
        "Команды:\n"
        "/train — начать тренировку\n"
        "/progress — посмотреть веса\n"
        "/history — история тренировок\n"
        "/plan — план тренировок\n\n"
        "Просто начни тренировку и я буду спрашивать вес по каждому упражнению."
    )
    await update.message.reply_text(text)

async def cmd_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["📋 *Твой план тренировок*\n"]
    for key, day in EXERCISES.items():
        lines.append(f"*{day['name']}*")
        for ex in day["exercises"]:
            sets = SETS_INFO.get(ex, "")
            lines.append(f"  • {ex} — {sets}")
        lines.append("")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_train(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)

    day_key = today_day_key()
    day_name = today_day_name()

    if day_key:
        day = EXERCISES[day_key]
        keyboard = make_keyboard(
            [f"Да, {day_name}!", "Выбрать другой день"]
        )
        user["session"] = {"step": "confirm_day", "suggested_key": day_key}
        save_data(data)
        await update.message.reply_text(
            f"Сегодня {day_name} — по расписанию:\n*{day['name']}*\n\nНачинаем?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await show_day_choice(update, user, data)

async def show_day_choice(update, user, data):
    options = [EXERCISES[k]["name"] for k in EXERCISES]
    keyboard = make_keyboard(options, cols=1)
    user["session"] = {"step": "choose_day"}
    save_data(data)
    await update.message.reply_text(
        "Выбери день тренировки:", reply_markup=keyboard
    )

async def cmd_progress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)

    if not user["weights"]:
        await update.message.reply_text("Пока нет данных. Проведи первую тренировку!")
        return

    lines = ["📊 *Твои текущие веса*\n"]
    for day_key, day in EXERCISES.items():
        day_lines = []
        for ex in day["exercises"]:
            w = user["weights"].get(ex)
            if w:
                day_lines.append(f"  • {ex}: *{w} кг*")
        if day_lines:
            lines.append(f"_{day['name']}_")
            lines.extend(day_lines)
            lines.append("")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)

    if not user["history"]:
        await update.message.reply_text("История пуста. Проведи первую тренировку!")
        return

    lines = ["📅 *История тренировок*\n"]
    for entry in reversed(user["history"][-10:]):
        day = EXERCISES.get(entry["day_key"], {})
        lines.append(f"*{entry['date']}* — {day.get('name', entry['day_key'])}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    text = update.message.text.strip()
    session = user.get("session")

    if not session:
        await update.message.reply_text(
            "Напиши /train чтобы начать тренировку, или /help для списка команд."
        )
        return

    step = session.get("step")

    if step == "confirm_day":
        if text.startswith("Да"):
            await start_training(update, user, data, session["suggested_key"])
        else:
            await show_day_choice(update, user, data)
        return

    if step == "choose_day":
        chosen_key = None
        for k, v in EXERCISES.items():
            if v["name"] == text:
                chosen_key = k
                break
        if not chosen_key:
            await update.message.reply_text("Выбери день из списка 👇")
            return
        await start_training(update, user, data, chosen_key)
        return

    if step == "log_weight":
        ex_name = session["current_exercise"]
        ex_index = session["exercise_index"]
        exercises = EXERCISES[session["day_key"]]["exercises"]

        weight_match = re.search(r"(\d+(?:[.,]\d+)?)", text)
        if not weight_match and text.lower() not in ["пропустить", "—", "-"]:
            await update.message.reply_text(
                f"Напиши вес в кг, например: *80* или *12.5*\nИли напиши *пропустить*",
                parse_mode="Markdown"
            )
            return

        if weight_match:
            weight = float(weight_match.group(1).replace(",", "."))
            user["weights"][ex_name] = weight
            if "weights" not in session:
                session["weights"] = {}
            session["weights"][ex_name] = weight

        next_index = ex_index + 1
        if next_index >= len(exercises):
            await finish_training(update, user, data, session)
        else:
            session["exercise_index"] = next_index
            session["current_exercise"] = exercises[next_index]
            save_data(data)
            await ask_exercise(update, user, session, exercises[next_index])
        return

async def start_training(update, user, data, day_key):
    day = EXERCISES[day_key]
    exercises = day["exercises"]
    first_ex = exercises[0]

    user["session"] = {
        "step": "log_weight",
        "day_key": day_key,
        "exercise_index": 0,
        "current_exercise": first_ex,
        "weights": {},
        "start_time": datetime.now().isoformat()
    }
    save_data(data)

    await update.message.reply_text(
        f"Начинаем *{day['name']}* 💪\n\nБуду спрашивать вес по каждому упражнению. Напиши *пропустить* если упражнение без веса.",
        parse_mode="Markdown"
    )
    await ask_exercise(update, user, user["session"], first_ex)

async def ask_exercise(update, user, session, ex_name):
    sets = SETS_INFO.get(ex_name, "")
    last_w, last_date = get_last_weight(user, ex_name)

    lines = [f"*{ex_name}*", f"_{sets}_", ""]

    if last_w:
        day_str = last_date if last_date else "прошлый раз"
        lines.append(f"В прошлый раз: *{last_w} кг* ({day_str})")
        lines.append("")

    lines.append("Сколько кг сегодня? (или *пропустить*)")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=make_keyboard(["пропустить"])
    )

async def finish_training(update, user, data, session):
    date_str = datetime.now().strftime("%d.%m.%Y")
    entry = {
        "date": date_str,
        "day_key": session["day_key"],
        "weights": session.get("weights", {})
    }
    user["history"].append(entry)
    user["session"] = None
    save_data(data)

    day_name = EXERCISES[session["day_key"]]["name"]
    logged = len(session.get("weights", {}))

    await update.message.reply_text(
        f"Тренировка завершена! 🏆\n\n*{day_name}*\nЗаписано упражнений: {logged}\n\nОтличная работа! До следующего раза 💪",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("train", cmd_train))
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
