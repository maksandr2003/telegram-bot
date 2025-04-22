import os
import json
import time
import logging
import asyncio
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiohttp import web
from telegram import (Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, ChatPermissions)
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
SEND_HOUR = 10  # Устанавливаем время отправки (10:00 утра)

logging.basicConfig(level=logging.INFO)

users = {}
application = None

def load_users():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(DATABASE_FILE, 'w') as f:
        json.dump(users, f, indent=4)

users = load_users()

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

async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Отлично! Давай сначала определим твой пол.")
    await gender(update, context)

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

async def send_video_to_user(user_id, context):
    user_data = users.get(user_id)
    if not user_data or not user_data['registered'] or user_data.get('course_finished'):
        return

    # Проверка времени отправки
    now = datetime.now()
    if now.hour != SEND_HOUR:
        return

    # Проверка, был ли урок отправлен сегодня
    last_sent = datetime.fromtimestamp(user_data['last_sent']) if user_data['last_sent'] else None
    if last_sent and last_sent.date() == now.date():
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
                await context.bot.send_video(chat_id=int(user_id), video=video, caption=caption,
                                             supports_streaming=True, allow_sending_without_reply=True)
            users[user_id]['current_lesson'] += 1
            users[user_id]['last_sent'] = int(time.time())
            save_users(users)
        except Exception as e:
            logging.error(f"Ошибка при отправке видео: {e}")
    else:
        logging.error(f"Файл не найден: {video_path}")

async def webhook_handler(request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        logging.info("Webhook получил новое обновление!")
        await application.update_queue.put(update)
        return web.Response()
    except Exception as e:
        logging.error(f"Ошибка в webhook_handler: {e}")
        return web.Response(status=500)

async def set_bot_commands(app):
    await app.bot.set_my_commands([])  # Удаляем всё меню

async def restrict_saving_permissions(user_id, context):
    try:
        await context.bot.restrict_chat_member(
            chat_id=user_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )
    except Exception as e:
        logging.warning(f"Не удалось ограничить права пользователя {user_id}: {e}")

async def init():
    global application
    application = Application.builder().token(BOT_TOKEN).rate_limiter(AIORateLimiter()).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_start_button, pattern="^start_registration$"))
    application.add_handler(CallbackQueryHandler(gender_selected, pattern="^gender_"))

    await application.bot.delete_webhook()
    await set_bot_commands(application)
    await application.bot.set_webhook(WEBHOOK_URL)

    web_app = web.Application()
    web_app.router.add_post("/webhook", webhook_handler)
    web_app.router.add_get("/", lambda request: web.Response(text="Бот работает!"))

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logging.info(f"\u2705 Бот Telegram запущен на порту {port}, webhook активен.")

    await application.initialize()
    await application.start()

def run():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init())
    loop.run_forever()

if __name__ == "__main__":
    run()
