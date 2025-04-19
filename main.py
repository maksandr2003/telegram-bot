import os
import json
import time
import random
import logging
from dotenv import load_dotenv
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          ContextTypes, TypeHandler)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "mysecret")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

VIDEO_FOLDER = 'videos'
DATABASE_FILE = 'users.json'
TOTAL_LESSONS = 7

logging.basicConfig(level=logging.INFO)

users = {}
if os.path.exists(DATABASE_FILE):
    with open(DATABASE_FILE, 'r') as f:
        users = json.load(f)

def save_users():
    with open(DATABASE_FILE, 'w') as f:
        json.dump(users, f, indent=4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {'registered': False, 'current_lesson': 1, 'course_finished': False}
        save_users()
    keyboard = [[InlineKeyboardButton("🚀 Начать обучение", callback_data='start_registration')]]
    await update.message.reply_text(
        "Привет! 👋 Добро пожаловать в твой персональный путь обучения по ИИ.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Отлично! Давай сначала определим твой пол.")
    keyboard = [[InlineKeyboardButton("Мужчина", callback_data='gender_male')],
                [InlineKeyboardButton("Женщина", callback_data='gender_female')]]
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Пожалуйста, выбери свой пол:",
                                   reply_markup=InlineKeyboardMarkup(keyboard))

async def gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    users[user_id]['gender'] = 'male' if query.data == 'gender_male' else 'female'
    users[user_id]['registered'] = True
    save_users()
    await query.answer()
    await query.edit_message_text("Пол успешно выбран. Приступаем к первому уроку!")
    await send_video(user_id, context)

async def send_video(user_id: str, context: ContextTypes.DEFAULT_TYPE):
    user = users[user_id]
    if not user['registered'] or user['course_finished']:
        return
    lesson = user['current_lesson']
    if lesson > TOTAL_LESSONS:
        user['course_finished'] = True
        save_users()
        await context.bot.send_message(chat_id=int(user_id),
                                       text="🎉 Поздравляю! Ты завершил весь курс!")
        return
    path = os.path.join(VIDEO_FOLDER, f"lesson{lesson}.mp4")
    if os.path.exists(path):
        messages = {
            'male': [f"Брат, готов к новому рывку? Урок №{lesson}!"],
            'female': [f"Ты супер! Вперёд — Урок №{lesson} уже ждёт тебя!"]
        }
        caption = f"Урок {lesson} — поехали!"
        gender = user.get('gender', 'male')
        await context.bot.send_message(chat_id=int(user_id), text=random.choice(messages[gender]))
        with open(path, 'rb') as video:
            await context.bot.send_video(chat_id=int(user_id), video=video, caption=caption)
        user['current_lesson'] += 1
        save_users()

async def webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.update_queue.put(update)
    return web.Response()

app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_start_button, pattern="^start_registration$"))
app.add_handler(CallbackQueryHandler(gender_selected, pattern="^gender_"))

async def start_webhook():
    await app.initialize()
    await app.start()
    await app.bot.set_webhook(f"{WEBHOOK_URL}/{WEBHOOK_SECRET}")
    web_app = web.Application()
    web_app.router.add_post(f"/{WEBHOOK_SECRET}", webhook_handler)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()
    print("Webhook запущен на порту 10000")
    await app.updater.start_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(start_webhook())
