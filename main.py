import os
import json
import time
import logging
import asyncio
import random
from dotenv import load_dotenv
from aiohttp import web
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    AIORateLimiter,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
VIDEO_FOLDER = "videos"
DATABASE_FILE = "users.json"
TOTAL_LESSONS = 7

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {'registered': False, 'current_lesson': 1, 'last_sent': 0, 'course_finished': False}
        save_users(users)

    keyboard = [[InlineKeyboardButton("\ud83d\ude80 Начать обучение", callback_data='start_registration')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! \ud83d\udc4b Добро пожаловать в твой персональный путь обучения по ИИ.\n\n"
        "Хочешь расти и учиться — нажми на кнопку ниже, и мы начнём! \ud83d\udca1",
        reply_markup=reply_markup
    )

# --- Кнопка "Начать обучение" ---
async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Отлично! Давай сначала определим твой пол.")
    await gender(update, context)

# --- Запрос пола ---
async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Мужчина", callback_data='gender_male')],
        [InlineKeyboardButton("Женщина", callback_data='gender_female')]
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Пожалуйста, выбери свой пол:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Обработка выбора пола ---
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
        await context.bot.send_message(chat_id=int(user_id),
            text="\ud83c\udf89 Поздравляю! Ты завершил весь курс. Это только начало большого пути! \ud83d\ude80")
        return

    video_path = os.path.join(VIDEO_FOLDER, f"lesson{lesson_number}.mp4")
    if os.path.exists(video_path):
        try:
            gender = user_data.get('gender', 'male')
            messages = [
                f"Урок №{lesson_number} уже в пути!",
                f"Ты справляешься отлично! Урок №{lesson_number}.",
                f"Вот и следующий — Урок №{lesson_number}."
            ]
            if gender == 'female':
                messages = [
                    f"Ты супер! Урок №{lesson_number} уже ждёт тебя!",
                    f"Ты молодец! Пора дальше — Урок №{lesson_number}.",
                    f"Вот и следующий — Урок №{lesson_number}."
                ]
            caption = f"Урок {lesson_number} — поехали!"
            await context.bot.send_message(chat_id=int(user_id), text=random.choice(messages))
            with open(video_path, 'rb') as video:
                await context.bot.send_video(chat_id=int(user_id), video=video, caption=caption)
            users[user_id]['current_lesson'] += 1
            users[user_id]['last_sent'] = int(time.time())
            save_users(users)
        except Exception as e:
            logging.error(f"Ошибка при отправке видео: {e}")
    else:
        logging.error(f"Файл не найден: {video_path}")

# --- Обработка Telegram webhook запросов ---
async def webhook_handler(request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot.bot)
        await bot.process_update(update)
        return web.Response()
    except Exception as e:
        logging.error(f"Ошибка в webhook_handler: {e}")
        return web.Response(status=500)

# --- Запуск ---
async def main():
    global bot
    bot = Application.builder().token(BOT_TOKEN).rate_limiter(AIORateLimiter()).build()

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CallbackQueryHandler(handle_start_button, pattern="^start_registration$"))
    bot.add_handler(CallbackQueryHandler(gender_selected, pattern="^gender_"))

    await bot.initialize()
    await bot.start()
    await bot.bot.delete_webhook()
    await bot.bot.set_webhook(WEBHOOK_URL)

    web_app = web.Application()
    web_app.router.add_post("/webhook", webhook_handler)
    web_app.router.add_get("/", lambda request: web.Response(text="Бот работает!"))

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"✅ Бот Telegram запущен на порту {port}, webhook активен.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
