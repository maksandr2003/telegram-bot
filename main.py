import os
import json
import time
import logging
import asyncio
import random
import nest_asyncio
nest_asyncio.apply()

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import schedule
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

# --- Настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("Error: BOT_TOKEN is missing!")
    exit()

VIDEO_FOLDER = 'videos'
DATABASE_FILE = 'users.json'
LESSON_INTERVAL = 24 * 60 * 60  # Интервал между уроками (1 день)
TOTAL_LESSONS = 7

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Работа с пользователями ---
def load_users():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(DATABASE_FILE, 'w') as f:
        json.dump(users, f, indent=4)

users = load_users()

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {'registered': False, 'current_lesson': 1, 'last_sent': 0, 'course_finished': False}
        save_users(users)

    keyboard = [[InlineKeyboardButton("🚀 Начать обучение", callback_data='start_registration')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! 👋 Добро пожаловать в твой персональный путь обучения по ИИ.\n\n"
        "Хочешь расти и учиться — нажми на кнопку ниже, и мы начнём! 💡",
        reply_markup=reply_markup
    )

# --- Обработка нажатия на кнопку "Начать обучение" ---
async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Отлично! Давай сначала определим твой пол.")
    await gender(update, context)

# --- Запрос пола ---
async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("Мужчина", callback_data='gender_male')],
        [InlineKeyboardButton("Женщина", callback_data='gender_female')]
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Пожалуйста, выбери свой пол:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    gender_value = 'male' if query.data == 'gender_male' else 'female'
    users[user_id]['gender'] = gender_value
    users[user_id]['registered'] = True
    save_users(users)

    await query.answer()
    await query.edit_message_text("Пол успешно выбран. Приступаем к первому уроку!")
    await send_video_to_user(user_id, context)

# --- Отправка видео одному пользователю ---
async def send_video_to_user(user_id, context):
    user_data = users.get(user_id)
    if not user_data or not user_data['registered'] or user_data.get('course_finished'):
        return

    lesson_number = user_data['current_lesson']
    if lesson_number > TOTAL_LESSONS:
        users[user_id]['course_finished'] = True
        save_users(users)
        await context.bot.send_message(chat_id=int(user_id), text=
            "🎉 Поздравляю! Ты завершил весь курс. Это только начало большого пути! 🚀")
        return

    video_path = os.path.join(VIDEO_FOLDER, f"lesson{lesson_number}.mp4")
    if os.path.exists(video_path):
        try:
            gender = user_data.get('gender', 'male')

            # Сообщения перед видео
            messages_male = [
                f"Брат, готов к новому рывку? Урок №{lesson_number} уже в пути!",
                f"Ты справляешься отлично! Вот тебе следующий шаг — Урок №{lesson_number}.",
                f"Надеюсь, ты освоил прошлый материал. Держи Урок №{lesson_number}."
            ]
            messages_female = [
                f"Ты супер! Вперёд к новым знаниям — Урок №{lesson_number} уже ждёт тебя!",
                f"Ты молодец! Пора двигаться дальше — держи Урок №{lesson_number}.",
                f"Надеюсь, прошлый урок был полезным. А вот и следующий — Урок №{lesson_number}."
            ]
            messages = messages_female if gender == 'female' else messages_male
            message_text = random.choice(messages)

            # Подписи к видео
            captions = [
                f"Урок {lesson_number} — поехали!",
                f"Вперёд! Урок {lesson_number} уже здесь.",
                f"Урок {lesson_number}. Новый уровень знаний!"
            ]
            caption_text = random.choice(captions)

            await context.bot.send_message(chat_id=int(user_id), text=message_text)
            with open(video_path, 'rb') as video:
                await context.bot.send_video(chat_id=int(user_id), video=video, caption=caption_text)

            users[user_id]['current_lesson'] += 1
            users[user_id]['last_sent'] = int(time.time())
            save_users(users)

        except Exception as e:
            logging.error(f"Ошибка при отправке видео: {e}")
    else:
        logging.error(f"Файл не найден: {video_path}")

# --- Отправка видео всем ---
async def send_daily_video(context: ContextTypes.DEFAULT_TYPE):
    for user_id in users:
        await send_video_to_user(user_id, context)

# --- Планировщик ---
async def run_schedule(app):
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

# --- Основной запуск ---
async def main():
    if not os.path.exists(VIDEO_FOLDER):
        os.makedirs(VIDEO_FOLDER)
        print(f"Создана папка '{VIDEO_FOLDER}'. Добавьте уроки в формате lesson1.mp4 и т.д.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_start_button, pattern="^start_registration$"))
    app.add_handler(CallbackQueryHandler(gender_selected, pattern="^gender_"))

    schedule.every().day.at("10:00").do(lambda: asyncio.create_task(send_daily_video(context=app.bot)))
    asyncio.create_task(run_schedule(app))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
свcd