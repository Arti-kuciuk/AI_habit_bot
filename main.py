import os
from aiogram import Bot, Dispatcher, types, F 
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timedelta, UTC, timezone, date
import sqlite3
import httpx


conn = sqlite3.connect("habits.db")
cursor = conn.cursor()


cursor.execute("""
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    habit_name TEXT NOT NULL,
    habit_description TEXT NOT NULL,
    goal TEXT NOT NULL,
    days TEXT NOT NULL,
    timezone_offset INTEGER NOT NULL,
    reminder_time TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
)
""")
conn.commit()

# Новая таблица habit_logs
cursor.execute("""
CREATE TABLE IF NOT EXISTS habit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    habit_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    status TEXT
)
""")
conn.commit()


load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


class HabitStates(StatesGroup):
    CHOOSE_CATEGORY = State()
    ENTER_HABIT_NAME = State()
    ENTER_HABIT_DESCRIPTION = State()
    SET_GOAL = State()
    SELECT_DAYS = State()
    SELECT_TIME = State()
    CONFIRM_HABIT = State()
    AI_CHAT = State()
    CONFIRM_CANCEL = State()


main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📈 My Progress")],
        [KeyboardButton(text="🧠 AI Assistant")],
        [KeyboardButton(text="💪 Motivation")],
        [KeyboardButton(text="❌ Cancel Habit")]
    ],
    resize_keyboard=True
)

ai_chat_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔙 Back")]
    ],
    resize_keyboard=True
)

def get_start_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Start your habit journey", callback_data="start_habit")]
    ])
    return keyboard

# Клавиатура для выбора категории привычки
def new_habit_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🧠 Health", callback_data="category:health")],
    [InlineKeyboardButton(text="📚 Learning", callback_data="category:learning")],
    [InlineKeyboardButton(text="🏃‍♂️ Fitness", callback_data="category:fitness")],
    [InlineKeyboardButton(text="🛏️ Sleep", callback_data="category:sleep")],
    [InlineKeyboardButton(text="✍️ Custom", callback_data="category:custom")]
    ])

    return keyboard


# Клавиатура для выбора дней
def get_days_selection_message(selected_days: list):
    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    buttons = []
    for day in DAYS:
        text = f"✅ {day}" if day in selected_days else day
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"toggle_day:{day}")])
    buttons.append([InlineKeyboardButton(text="✅ Done", callback_data="days_done")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    if not selected_days:
        text = "Select the days for your habit:"
    else:
        text = "You have selected: " + ", ".join(selected_days) + "\nYou can select more or press Done."
    return text, keyboard


# Клавиатура для выбора часового пояса
def get_timezone_keyboard():
    buttons = []
    for offset in range(-12, 13):
        sign = "+" if offset >= 0 else ""
        text = f"UTC{sign}{offset}"
        callback_data = f"timezone:{offset}"
        buttons.append(InlineKeyboardButton(text=text, callback_data=callback_data))

    # Группировка по 3 кнопки в ряд
    keyboard_rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

cancel_habit_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Yes", callback_data="confirm_cancel_habit")],
    [InlineKeyboardButton(text="❌ No", callback_data="cancel_cancel_habit")],
])


# Клавиатура для завершения привычки
completed_habit_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔁 Restart Habit")],
        [KeyboardButton(text="🆕 New Habit")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Подтверждение создания привычки
async def show_confirmation(message_or_callback, data):
    confirmation_text = (
        "🧾 Please confirm your habit setup:\n"
        f"• Category: {data.get('category')}\n"
        f"• Name: {data.get('habit_name')}\n"
        f"• Description: {data.get('habit_description')}\n"
        f"• Goal: {data.get('goal')}\n"
        f"• Days: {', '.join(data.get('selected_days', []))}\n"
        f"• Timezone: UTC{data.get('timezone_offset'):+}\n"
        f"• Reminder Time: {data.get('reminder_time')}"
    )

    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Confirm", callback_data="confirm_habit")],
        [InlineKeyboardButton(text="✏️ Change Name", callback_data="edit:habit_name")],
        [InlineKeyboardButton(text="✏️ Change Description", callback_data="edit:habit_description")],
        [InlineKeyboardButton(text="✏️ Change Goal", callback_data="edit:goal")],
        [InlineKeyboardButton(text="📆 Change Days", callback_data="edit:days")],
        [InlineKeyboardButton(text="🌍 Change Timezone", callback_data="edit:timezone")],
        [InlineKeyboardButton(text="⏰ Change Time", callback_data="edit:time")],
    ])

    await message_or_callback.answer(confirmation_text, reply_markup=confirm_keyboard)

# Завершение привычки
def static_congrats_message(done: int) -> str:
    if done >= 18:
        return (
            "🏆 *ABSOLUTE VICTORY!* 🏆\n\n"
            "You stayed strong, consistent, and unstoppable for 21 days — and now, you’ve reached the finish line like a true champion! 🥇\n\n"
            "What you’ve done isn’t just a streak. It’s a transformation. You showed up even when it was hard, and that means everything. 💥\n\n"
            "You’re not the same person who started this journey. You’ve evolved. Grown. You’re proof that with focus and fire, *anything is possible.* 🔥\n\n"
            "Be proud. Be loud. And remember: this is just your beginning. 🌟\n\n"
            "_Ready to conquer the next one?_ 💪"
        )
    elif done >= 14:
        return (
            "🎯 *Great job sticking with it!* 🎯\n\n"
            "You’ve completed a tough 21-day challenge — and while it wasn’t perfect, it was *real*. You showed up, made progress, and pushed forward. That’s what builds strength. 💪\n\n"
            "You may not have hit every target, but the dedication you showed matters *so much more* than perfection.\n\n"
            "Every day you chose to continue built a new part of who you are becoming. Let this momentum carry you to new heights. 🚀\n\n"
            "_Next time? You’ll fly even further._ Keep going! 🌱"
        )
    else:
        return (
            "💡 *You showed courage just by starting.* 💡\n\n"
            "These 21 days may not have gone as planned — but don’t forget what matters: *you showed up*. You tried. You learned. And you’re still here. 💪\n\n"
            "Progress isn’t linear. It’s messy. But it’s *real*. Even the toughest journeys begin with missteps, and this was *not a failure* — it was your first step toward growth. 🌱\n\n"
            "Now it’s time to reflect, reset, and rise again. The next round is yours for the taking. 🔁\n\n"
            "_Fall down seven times, stand up eight._ Let’s go!"
        )
    

# Генерация мотивации для привычки
async def generate_motivation(habit_name: str, description: str, goal: str, done: int, partial: int, missed: int) -> str:
    total = done + partial + missed
    day = f"{total}/21"

    prompt = (
        f"Habit: {habit_name}\n"
        f"Description: {description}\n"
        f"Goal: {goal}\n"
        f"Today: Day {day}\n"
        f"✅ Completed: {done}\n"
        f"⚠️ Partial: {partial}\n"
        f"❌ Missed: {missed}\n\n"
        "You are a tough but inspiring motivational coach. "
        "Write a short, powerful message to the user. (max 4-6 lines)"
        "Speak directly using 'you'. Be emotional, intense, and encouraging. "
        "Make it clear why giving up is NOT an option. Use strong language and emojis to energize them."
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={"Authorization": f"Bearer {TOGETHER_API_KEY}"},
            json={
                "model": "mistralai/Mistral-7B-Instruct-v0.2",
                "messages": [
                    {"role": "system", "content": "You are a powerful motivational coach who helps people build habits. \
                      Your tone is direct, emotional, and inspiring, but also human and encouraging. \
                      Speak in second person, use emojis, and end with a call to action."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.9,
                "max_tokens": 180
            }
        )

        data = response.json()

        # 🔍 Печатаем весь ответ для отладки
        print("[DEBUG] Together.ai response:")
        print(data)

        if "choices" not in data:
            error_msg = data.get("error", {}).get("message", "Unknown error from Together.ai")
            return f"⚠️ AI error: {error_msg}"

        return data["choices"][0]["message"]["content"].strip()
    

# Генерация совета от AI
async def generate_ai_advice(habit_name: str, description: str, goal: str, done: int, partial: int, missed: int, user_question: str) -> str:
    total = done + partial + missed
    day = f"{total}/21"

    system_prompt = (
        "You are a helpful, supportive and smart AI assistant helping a user stay consistent with their habit. "
        "You understand their goal and progress, and you answer their questions with insight and empathy. "
        "Give specific advice, avoid generic responses, and end with a short encouragement. max 100 words"
    )

    user_prompt = (
        f"Habit: {habit_name}\n"
        f"Description: {description}\n"
        f"Goal: {goal}\n"
        f"Day: {day}\n"
        f"✅ Completed: {done} | ⚠️ Partial: {partial} | ❌ Missed: {missed}\n\n"
        f"Question: {user_question}\n\n"
        "Based on the above, give your best answer."
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={"Authorization": f"Bearer {TOGETHER_API_KEY}"},
            json={
                "model": "mistralai/Mistral-7B-Instruct-v0.2",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.85,
                "max_tokens": 300
            }
        )

        data = response.json()
        print("[DEBUG] AI Assistant response:", data)

        if "choices" not in data:
            error_msg = data.get("error", {}).get("message", "Unknown error from Together.ai")
            return f"⚠️ AI error: {error_msg}"

        return data["choices"][0]["message"]["content"].strip()


@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Welcome to 21Day — your personal habit coach. \nReady to build a new habit?",
        reply_markup=get_start_keyboard()
    )


@dp.callback_query(F.data == "start_habit")
async def process_start_button(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "📂 Choose a category for your habit:",
        reply_markup=new_habit_keyboard()
    )
    await state.set_state(HabitStates.CHOOSE_CATEGORY)


@dp.callback_query(F.data.startswith("category:"), HabitStates.CHOOSE_CATEGORY)
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":")[1]
    await state.update_data(category=category)
    await callback.message.delete()
    await callback.message.answer("✏️ What habit would you like to develop? \nLet's make a name for it!")
    await state.set_state(HabitStates.ENTER_HABIT_NAME)


@dp.message(HabitStates.ENTER_HABIT_NAME)
async def process_habit_name(message: Message, state: FSMContext):
    await state.update_data(habit_name=message.text)
    data = await state.get_data()
    if data.get("category") and data.get("habit_description") and data.get("goal") and data.get("selected_days") and data.get("timezone_offset") and data.get("reminder_time"):
        await show_confirmation(message, data)
        await state.set_state(HabitStates.CONFIRM_HABIT)
    else:
        await message.answer("📝 Describe your habit in a few words:")
        await state.set_state(HabitStates.ENTER_HABIT_DESCRIPTION)


@dp.message(HabitStates.ENTER_HABIT_DESCRIPTION)
async def process_habit_description(message: Message, state: FSMContext):
    await state.update_data(habit_description=message.text)
    data = await state.get_data()
    if data.get("category") and data.get("habit_name") and data.get("goal") and data.get("selected_days") and data.get("timezone_offset") and data.get("reminder_time"):
        await show_confirmation(message, data)
        await state.set_state(HabitStates.CONFIRM_HABIT)
    else:
        await message.answer("Great! Now let's set a goal for the next 21 days ")
        await state.set_state(HabitStates.SET_GOAL)


@dp.message(HabitStates.SET_GOAL)
async def process_goal(message: Message, state: FSMContext):
    await state.update_data(goal=message.text)
    data = await state.get_data()
    if data.get("category") and data.get("habit_name") and data.get("habit_description") and data.get("selected_days") and data.get("timezone_offset") and data.get("reminder_time"):
        await show_confirmation(message, data)
        await state.set_state(HabitStates.CONFIRM_HABIT)
    else:
        await state.update_data(selected_days=[])
        text, keyboard = get_days_selection_message([])
        await message.answer(text, reply_markup=keyboard)
        await state.set_state(HabitStates.SELECT_DAYS)


@dp.callback_query(F.data.startswith("toggle_day:"), HabitStates.SELECT_DAYS)
async def toggle_day(callback: CallbackQuery, state: FSMContext):
    day = callback.data.split(":")[1]
    data = await state.get_data()
    selected_days = data.get("selected_days", [])
    if day in selected_days:
        selected_days.remove(day)
    else:
        selected_days.append(day)
    await state.update_data(selected_days=selected_days)
    text, keyboard = get_days_selection_message(selected_days)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        try:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        except Exception as e2:
            print(f"[DEBUG] error at edit_reply_markup: {e2}")
    await callback.answer()


@dp.callback_query(F.data == "days_done", HabitStates.SELECT_DAYS)
async def days_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_days = data.get("selected_days", [])
    if not selected_days:
        await callback.answer("Please select at least one day.", show_alert=True)
        return
    await state.update_data(selected_days=selected_days)
    data = await state.get_data()
    if data.get("category") and data.get("habit_name") and data.get("habit_description") and data.get("goal") and data.get("timezone_offset") and data.get("reminder_time"):
        await callback.message.delete()
        await show_confirmation(callback.message, data)
        await state.set_state(HabitStates.CONFIRM_HABIT)
    else:
        await callback.message.edit_text("🌍 Select your timezone:", reply_markup=get_timezone_keyboard())
        await state.set_state(HabitStates.SELECT_TIME)


# Handler for timezone selection
@dp.callback_query(F.data.startswith("timezone:"), HabitStates.SELECT_TIME)
async def process_timezone(callback: CallbackQuery, state: FSMContext):
    offset = int(callback.data.split(":")[1])
    await state.update_data(timezone_offset=offset)
    data = await state.get_data()
    if data.get("category") and data.get("habit_name") and data.get("habit_description") and data.get("goal") and data.get("selected_days") and data.get("reminder_time"):
        await callback.message.delete()
        await show_confirmation(callback.message, data)
        await state.set_state(HabitStates.CONFIRM_HABIT)
    else:
        await callback.message.delete()
        await callback.message.answer("⏰ Now enter the time for the reminder (e.g. 07:00):")


# Handler for time input
@dp.message(HabitStates.SELECT_TIME)
async def process_time(message: Message, state: FSMContext):
    time_text = message.text.strip()

    try:
        # Преобразуем в объект времени
        time_obj = datetime.strptime(time_text, "%H:%M").time()

        # Сохраняем форматированную строку с ведущими нулями (HH:MM)
        formatted_time = time_obj.strftime("%H:%M")
    except ValueError:
        await message.answer("❌ Invalid time format. Please enter time as HH:MM.")
        return

    await state.update_data(reminder_time=formatted_time)

    data = await state.get_data()
    if data.get("category") and data.get("habit_name") and data.get("habit_description") and data.get("goal") and data.get("selected_days") and data.get("timezone_offset"):
        await show_confirmation(message, data)
        await state.set_state(HabitStates.CONFIRM_HABIT)
    else:
        await message.answer("⚠️ Not all fields are filled. Please continue setup.")


@dp.callback_query(F.data == "edit:habit_name", HabitStates.CONFIRM_HABIT)
async def edit_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("✏️ Enter a new name for your habit:")
    await state.set_state(HabitStates.ENTER_HABIT_NAME)


@dp.callback_query(F.data == "edit:habit_description", HabitStates.CONFIRM_HABIT)
async def edit_description(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("✏️ Enter a new description for your habit:")
    await state.set_state(HabitStates.ENTER_HABIT_DESCRIPTION)


@dp.callback_query(F.data == "edit:goal", HabitStates.CONFIRM_HABIT)
async def edit_goal(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("✏️ Enter a new goal for your habit:")
    await state.set_state(HabitStates.SET_GOAL)


@dp.callback_query(F.data == "edit:days", HabitStates.CONFIRM_HABIT)
async def edit_days(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_days = data.get("selected_days", [])
    await callback.message.delete()
    text, keyboard = get_days_selection_message(selected_days)
    await callback.message.answer(text, reply_markup=keyboard)
    await state.set_state(HabitStates.SELECT_DAYS)


@dp.callback_query(F.data == "edit:timezone", HabitStates.CONFIRM_HABIT)
async def edit_timezone(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("🌍 Select your timezone:", reply_markup=get_timezone_keyboard())
    await state.set_state(HabitStates.SELECT_TIME)


@dp.callback_query(F.data == "edit:time", HabitStates.CONFIRM_HABIT)
async def edit_time(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("⏰ Enter a new time for the reminder (e.g. 07:00):")
    await state.set_state(HabitStates.SELECT_TIME)


@dp.callback_query(F.data == "confirm_habit", HabitStates.CONFIRM_HABIT)
async def confirm_habit(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()

    data = await state.get_data()
    user_id = callback.from_user.id
    category = data.get("category")
    habit_name = data.get("habit_name")
    habit_description = data.get("habit_description")
    goal = data.get("goal")
    days = data.get("selected_days")
    timezone_offset = data.get("timezone_offset")
    reminder_time = data.get("reminder_time")

    days_str = ",".join(days)  # превращает список в строку


    cursor.execute("""
    INSERT INTO habits (user_id, category, habit_name, habit_description, goal, days, timezone_offset, reminder_time, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, category, habit_name, habit_description, goal, days_str, timezone_offset, reminder_time, 1))

    await callback.message.answer("🎉 Your habit has been successfully created!")
    await callback.message.answer("💬 Here's what you can do next:", reply_markup=main_menu_keyboard)

    conn.commit()

    await state.clear()


async def reminder_scheduler():
    while True:
        now = datetime.now(UTC)
        current_time = now.strftime("%H:%M")
        current_weekday = now.strftime("%A")

        cursor.execute("SELECT * FROM habits")
        habits = cursor.fetchall()

        for habit in habits:
            (
                habit_id,
                user_id,
                category,
                habit_name,
                habit_description,
                goal,
                days,
                timezone_offset,
                reminder_time,
                is_active
            ) = habit

            if is_active == 0:
                continue

            # Получаем прогресс по привычке
            cursor.execute("SELECT status FROM habit_logs WHERE user_id = ? AND habit_id = ?", (user_id, habit_id))
            logs = cursor.fetchall()

            done = sum(1 for (status,) in logs if status == "done")
            partial = sum(1 for (status,) in logs if status == "partial")
            missed = sum(1 for (status,) in logs if status == "missed")
            completed_days = done + partial + missed

            # Завершение привычки после 21 дня
            if completed_days >= 21:
                cursor.execute("UPDATE habits SET is_active = 0 WHERE id = ?", (habit_id,))
                conn.commit()

                congrats = static_congrats_message(done)
                await bot.send_message(user_id, f"🎉 {congrats}")
                await bot.send_message(user_id, "💬 Here's what you can do next:", reply_markup=completed_habit_keyboard)
                continue

            # Корректировка времени с учётом таймзоны
            user_hour = (now.hour + timezone_offset) % 24
            user_time = f"{user_hour:02d}:{now.strftime('%M')}"

            habit_days = [d.strip() for d in days.split(",")]
            if reminder_time == user_time and current_weekday in habit_days:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Done", callback_data=f"done:{habit_id}"),
                        InlineKeyboardButton(text="⚠️ Partially", callback_data=f"partial:{habit_id}"),
                        InlineKeyboardButton(text="❌ Missed", callback_data=f"missed:{habit_id}")
                    ]
                ])
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"🕘 Day {completed_days + 1}/21\n*{habit_name}*\n{goal}\nHow is it going?",
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"[ERROR] Failed to send reminder to user {user_id}: {e}")

        await asyncio.sleep(60)


@dp.callback_query(F.data.startswith("done:"))
async def handle_done(callback: CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Проверка: уже есть лог на сегодня?
    cursor.execute("""
        SELECT id FROM habit_logs
        WHERE user_id = ? AND habit_id = ? AND date = ?
    """, (user_id, habit_id, today))
    exists = cursor.fetchone()

    if not exists:
        cursor.execute("""
            INSERT INTO habit_logs (user_id, habit_id, date, status)
            VALUES (?, ?, ?, ?)
        """, (user_id, habit_id, today, "done"))
        conn.commit()

    await callback.message.edit_text("🎉 Great! I've added it to your journal as 'done'.")
    await callback.answer()


@dp.callback_query(F.data.startswith("partial:")) 
async def handle_done(callback: CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT id FROM habit_logs
        WHERE user_id = ? AND habit_id = ? AND date = ?
    """, (user_id, habit_id, today))
    exists = cursor.fetchone()

    if not exists:
        cursor.execute("""
            INSERT INTO habit_logs (user_id, habit_id, date, status)
            VALUES (?, ?, ?, ?)
        """, (user_id, habit_id, today, "partial"))
        conn.commit()

    await callback.message.edit_text("👌 Good, partially — it's still a result!")
    await callback.answer()


@dp.callback_query(F.data.startswith("missed:")) 
async def handle_done(callback: CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT id FROM habit_logs
        WHERE user_id = ? AND habit_id = ? AND date = ?
    """, (user_id, habit_id, today))
    exists = cursor.fetchone()

    if not exists:
        cursor.execute("""
            INSERT INTO habit_logs (user_id, habit_id, date, status)
            VALUES (?, ?, ?, ?)
        """, (user_id, habit_id, today, "missed"))
        conn.commit()

    await callback.message.edit_text("😕 Sad, hope tomorrow will be better!")
    await callback.answer()


@dp.message(F.text == "📈 My Progress")
async def show_progress(message: Message):
    user_id = message.from_user.id

    cursor.execute("""
        SELECT id, habit_name FROM habits
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    habit_id, habit_name = cursor.fetchone()

    cursor.execute("""
        SELECT status FROM habit_logs
        WHERE user_id = ? AND habit_id = ?
    """, (user_id, habit_id))
    logs = cursor.fetchall()

    done = sum(1 for (status,) in logs if status == "done")
    partial = sum(1 for (status,) in logs if status == "partial")
    missed = sum(1 for (status,) in logs if status == "missed")
    total = done + partial + missed

    text = (
        f"📊 {habit_name}\n"
        f"📅 Day {total}/21\n"
        f"✅ Done: {done}\n"
        f"⚠️ Partial: {partial}\n"
        f"❌ Missed: {missed}"
    )

    await message.answer(text)


@dp.message(F.text == "💪 Motivation")
async def show_motivation(message: Message):
    user_id = message.from_user.id

    # Получаем привычку
    cursor.execute("""
        SELECT id, habit_name, habit_description, goal FROM habits
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    habit = cursor.fetchone()

    if not habit:
        await message.answer("❌ You don't have an active habit.")
        return

    habit_id, habit_name, habit_description, goal = habit

    # Получаем логи
    cursor.execute("""
        SELECT status FROM habit_logs
        WHERE user_id = ? AND habit_id = ?
    """, (user_id, habit_id))
    logs = cursor.fetchall()

    done = sum(1 for (status,) in logs if status == "done")
    partial = sum(1 for (status,) in logs if status == "partial")
    missed = sum(1 for (status,) in logs if status == "missed")

    # Генерируем мотивацию
    await message.answer("🧠 Thinking of something powerful...")
    motivation = await generate_motivation(habit_name, habit_description, goal, done, partial, missed)

    await message.answer(f"🔥 {motivation}")


@dp.message(F.text == "🧠 AI Assistant")
async def ai_assistant_entry(message: Message, state: FSMContext):
    await message.answer("🧠 Ask your question about your habit. I’ll do my best to help you!", reply_markup=ai_chat_keyboard)
    await state.set_state(HabitStates.AI_CHAT)


@dp.message(HabitStates.AI_CHAT)
async def handle_ai_chat(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_question = message.text

    # Получаем активную привычку
    cursor.execute("""
        SELECT id, habit_name, habit_description, goal FROM habits
        WHERE user_id = ? ORDER BY id DESC LIMIT 1
    """, (user_id,))
    habit = cursor.fetchone()

    if not habit:
        await message.answer("❌ You don't have an active habit.")
        await state.clear()
        return

    habit_id, habit_name, description, goal = habit

    # Прогресс
    cursor.execute("""
        SELECT status FROM habit_logs
        WHERE user_id = ? AND habit_id = ?
    """, (user_id, habit_id))
    logs = cursor.fetchall()

    done = sum(1 for (status,) in logs if status == "done")
    partial = sum(1 for (status,) in logs if status == "partial")
    missed = sum(1 for (status,) in logs if status == "missed")

    await message.answer("💬 Thinking...")

    response = await generate_ai_advice(habit_name, description, goal, done, partial, missed, user_question)

    await message.answer(response) 


@dp.message(HabitStates.AI_CHAT, F.text == "🔙 Back")
async def exit_ai_chat(message: Message, state: FSMContext):
    await message.answer("📋 Back to main menu.", reply_markup=main_menu_keyboard)
    await state.clear()


@dp.message(F.text == "❌ Cancel Habit")
async def cancel_habit(message: Message, state: FSMContext):
    await message.answer("Are you sure you want to cancel your habit?", reply_markup=cancel_habit_keyboard)
    
    await state.set_state(HabitStates.CONFIRM_CANCEL)

@dp.callback_query(F.data == "confirm_cancel_habit", HabitStates.CONFIRM_CANCEL)
async def confirm_cancel(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    cursor.execute("DELETE FROM habits WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM habit_logs WHERE user_id = ?", (user_id,))
    conn.commit()
    
    await callback.message.edit_text("Your habit has been canceled.")
    await callback.message.answer("Have a good day!", reply_markup=ReplyKeyboardRemove())
    await callback.message.answer(
        "Want to start a new journey?",
        reply_markup=get_start_keyboard()
    )
    await state.clear()

@dp.callback_query(F.data == "cancel_cancel_habit", HabitStates.CONFIRM_CANCEL)
async def cancel_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Habit not cancelled.")
    await callback.message.answer("keep up your habit and don't give up!", reply_markup=main_menu_keyboard)
    await state.clear()


@dp.message(F.text == "🔁 Restart Habit")
async def handle_restart_habit(message: Message):
    user_id = message.from_user.id

    cursor.execute("""
        SELECT id FROM habits 
        WHERE user_id = ? AND is_active = 0
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    result = cursor.fetchone()

    if result:
        habit_id = result[0]
        cursor.execute("UPDATE habits SET is_active = 1 WHERE id = ?", (habit_id,))
        cursor.execute("DELETE FROM habit_logs WHERE habit_id = ? AND user_id = ?", (habit_id, user_id))
        conn.commit()

        await message.answer("🔁 Your habit has been restarted! Let’s go again! 💪", reply_markup=main_menu_keyboard)
    else:
        await message.answer("⚠️ No completed habit found to restart.")


@dp.message(F.text == "🆕 New Habit")
async def handle_new_habit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🆕 Let’s start a new habit!")
    await message.answer("📂 Choose a category:", reply_markup=new_habit_keyboard())
    await state.set_state(HabitStates.CHOOSE_CATEGORY)



async def main():
    print("Bot started...")
    asyncio.create_task(reminder_scheduler())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


