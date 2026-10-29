import os
import asyncio
import json
from datetime import datetime, timedelta
from flask import Flask, request, abort
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiohttp

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
JOURNAL_LOGIN = os.getenv("JOURNAL_LOGIN")
JOURNAL_PASSWORD = os.getenv("JOURNAL_PASSWORD")

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# --- ФУНКЦИЯ ПОЛУЧЕНИЯ РАСПИСАНИЯ ---
import aiohttp

async def get_schedule_from_journal(start_date: str, end_date: str):
    """Асинхронно получает расписание из Journal через прямой запрос к API."""
    try:
        # Ключ и базовый URL берем из исходников библиотеки
        APP_KEY = "6a56a5df2667e65aab73ce76d1dd737f7d1faef9c52e8b8c55ac75f565d8e8a6"
        BASE_URL = "https://msapi.top-academy.ru/api/v2"
        
        # Заголовки (в точности как в библиотеке)
        headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": "Bearer null",
            "content-type": "application/json",
            "referer": "https://journal.top-academy.ru/",
            "x-cache-client": "600"
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. Авторизация (как в библиотеке)
            login_url = f"{BASE_URL}/auth/login"
            payload = {
                "application_key": APP_KEY,
                "username": JOURNAL_LOGIN,
                "password": JOURNAL_PASSWORD
            }
            
            async with session.post(login_url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return f"Ошибка авторизации: {resp.status} - {error_text}"
                
                data = await resp.json()
                token = data.get("access_token")
                
                if not token:
                    return "Ошибка авторизации: сервер не выдал токен."
                
                # Обновляем заголовки для дальнейших запросов (добавляем токен)
                session.headers.update({"authorization": f"Bearer {token}"})
            
            # 2. Получение расписания на день (используем правильный эндпоинт)
            schedule_url = f"{BASE_URL}/schedule/operations/get-by-date?date_filter={start_date}"
            
            async with session.get(schedule_url) as resp:
                if resp.status == 200:
                    # Возвращаем сырые данные JSON
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    return f"Ошибка получения расписания: {resp.status} - {error_text}"
                    
    except Exception as e:
        return f"Ошибка при получении данных: {e}"

# --- ФОРМАТИРОВАНИЕ РАСПИСАНИЯ ---
def format_schedule(schedule_data) -> str:
    """Превращает сырые данные в читаемый текст."""
    
    if not schedule_data:
        return "На этот период занятий нет."

    # Если данные пришли как строка (ошибка от сервера), просто возвращаем её
    if isinstance(schedule_data, str):
        return schedule_data

    text = ""
    try:
        # Группируем занятия по датам
        schedule_by_date = {}
        for lesson in schedule_data:
            date = lesson.get('date', 'Дата не указана')
            if date not in schedule_by_date:
                schedule_by_date[date] = []
            schedule_by_date[date].append(lesson)

        # Проходимся по каждой дате
        for date, lessons in sorted(schedule_by_date.items()):
            text += f"📅 **{date}**\n\n"
            
            for lesson in lessons:
                lesson_num = lesson.get('lesson', '-')
                time_start = lesson.get('started_at', '??:??')
                time_end = lesson.get('finished_at', '??:??')
                subject = lesson.get('subject_name', 'Предмет не указан')
                teacher = lesson.get('teacher_name', 'Преподаватель не указан')
                room = lesson.get('room_name', 'Аудитория не указана')
                
                text += f"**{lesson_num} пара** | 🕒 {time_start} - {time_end}\n"
                text += f"📚 {subject}\n"
                text += f"👨‍🏫 {teacher}\n"
                text += f"📍 {room}\n"
                text += "-------------------\n"
            
            text += "\n"
        
        return text
    except Exception as e:
        return f"Ошибка форматирования: {e}\nСырые данные:\n{schedule_data}"

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот для просмотра расписания.\n"
        "Команды:\n"
        "/today - расписание на сегодня\n"
        "/week - расписание на неделю\n"
        "/links - ссылки на онлайн-аудитории"  # Добавили эту строку
    )

@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    await message.answer("⏳ Запрашиваю расписание на сегодня...")
    
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    
    schedule = await get_schedule_from_journal(date_str, date_str)
    formatted_text = format_schedule(schedule)
    
    # Добавляем parse_mode="Markdown", чтобы убрать звездочки
    await message.answer(formatted_text, parse_mode="Markdown")

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    await message.answer("⏳ Запрашиваю расписание на неделю... (это может занять несколько секунд)")
    
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    
    full_week_text = ""
    
    # Проходимся по каждому дню недели (от 0 до 6)
    for i in range(7):
        current_day = start_of_week + timedelta(days=i)
        date_str = current_day.strftime("%Y-%m-%d")
        
        # Запрашиваем расписание на конкретный день
        schedule = await get_schedule_from_journal(date_str, date_str)
        
        # Если на этот день есть пары, добавляем их в общий текст
        if schedule and not isinstance(schedule, str) and len(schedule) > 0:
            formatted_day = format_schedule(schedule)
            full_week_text += formatted_day + "\n"
            
        # Небольшая пауза, чтобы сервер Journal не заблокировал нас за частые запросы
        await asyncio.sleep(0.5) 
    
    if not full_week_text:
        await message.answer("На эту неделю занятий нет.")
    else:
        # Telegram не пропускает сообщения длиннее 4096 символов. 
        # Если неделя слишком длинная, разбиваем её на части.
        if len(full_week_text) > 4000:
            chunks = [full_week_text[i:i+4000] for i in range(0, len(full_week_text), 4000)]
            for chunk in chunks:
                await message.answer(chunk, parse_mode="Markdown")
        else:
            await message.answer(full_week_text, parse_mode="Markdown")

@dp.message(Command("links"))
async def cmd_links(message: types.Message):
    links_text = (
        "🔗**ССЫЛКИ НА ОНЛАЙН АУДИТОРИИ** 🔗\n\n"
        "📍https://telemost.yandex.ru/j/85904888677388 - 👨‍🏫 Сергеев К.В\n"
        "📍https://telemost.yandex.ru/j/29942917633401 - 👨‍🏫 Вострецова Ю.В\n"
        "📍https://telemost.yandex.ru/j/66245557386310 - 👨‍🏫 Пластун А.В\n"
        "📍https://telemost.yandex.ru/j/9393804012 - 👨‍🏫 Агарков А.А."
    )
    # parse_mode="Markdown" сделает заголовок жирным
    await message.answer(links_text, parse_mode="Markdown")


# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    """Этот эндпоинт принимает сообщения от Telegram."""
    if request.headers.get("content-type") != "application/json":
        abort(403)
    
    json_string = request.get_data().decode("utf-8")
    update = types.Update.model_validate_json(json_string)
    
    # Обрабатываем сообщение
    asyncio.run(dp.feed_update(bot, update))
    return "OK", 200

@app.route("/")
def health_check():
    """Этот эндпоинт нужен, чтобы Render видел, что сервис жив."""
    return "Bot is running", 200

# Запуск Flask-сервера (именно он будет работать на Render)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)