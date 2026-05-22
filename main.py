import asyncio
import aiohttp
import os
import json
import ssl
import pymorphy3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, or_f
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

#опц
TG_TOKEN = "7328048685:AAHe_FsS9bMQFIqyEYSwFCxxqVORR1vrA7Q"
OWM_API_KEY = "2e46c50587f4626dab51eba27fb1778b"
ADMIN_ID = 7787661259  # Твой ID для рассылки
USERS_FILE = "users.txt"
SETTINGS_FILE = "user_settings.json"

bot = Bot(token=TG_TOKEN)
dp = Dispatcher()
morph = pymorphy3.MorphAnalyzer()

#работа с данными

def load_user_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

user_settings = load_user_settings()

def save_user_id(user_id):
    user_id = str(user_id)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f: f.write(user_id + "\n")
        return
    with open(USERS_FILE, "r") as f:
        users = f.read().splitlines()
    if user_id not in users:
        with open(USERS_FILE, "a") as f: f.write(user_id + "\n")

#склонение+кнопки

def main_keyboard(user_id, chat_type):
    if chat_type != "private": return None
    buttons = [
        [KeyboardButton(text="Москва"), KeyboardButton(text="Санкт-Петербург")],
        [KeyboardButton(text="Узнать по геолокации 📍", request_location=True)],
        [KeyboardButton(text="📖 Помощь и команды")]
    ]
    uid = str(user_id)
    if uid in user_settings:
        city = user_settings[uid]
        buttons.insert(0, [KeyboardButton(text=f"🏠 Мой город: {city}")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_city_prepositional(city_name):
    if not city_name: return "этом месте"
    words = str(city_name).split()
    inflected_words = []
    for word in words:
        parsed = morph.parse(word)[0]
        inflected = parsed.inflect({'loct'})
        inflected_words.append(inflected.word.capitalize() if inflected else word.capitalize())
    return " ".join(inflected_words)

#обработчики 

#старт
@dp.message(CommandStart())
async def start_command(message: Message):
    save_user_id(message.from_user.id)
    await message.answer(
        "Привет! Я метео-бот.\nИспользуй `/setcity город`, чтобы я запомнил тебя.",
        reply_markup=main_keyboard(message.from_user.id, message.chat.type),
        parse_mode="Markdown"
    )

#рассылка
@dp.message(Command("send"))
async def admin_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID:
        return #если нету в списке=молчание

    broadcast_text = message.text.replace("/send", "").strip()
    if not broadcast_text:
        await message.answer("⚠️ Ошибка: Введите текст после команды.\nПример: `/send Всем привет!`")
        return

    if not os.path.exists(USERS_FILE):
        await message.answer("❌ База пользователей пуста.")
        return

    with open(USERS_FILE, "r") as f:
        users = f.read().splitlines()

    sent_count = 0
    await message.answer(f"📢 Начинаю рассылку для {len(users)} чел...")

    for uid in users:
        try:
            await bot.send_message(uid, broadcast_text)
            sent_count += 1
            await asyncio.sleep(0.05) # Защита от спам-фильтра
        except:
            pass
    
    await message.answer(f"✅ Рассылка завершена!\nДоставлено: {sent_count}")

#помощь
@dp.message(or_f(Command("help"), F.text == "📖 Помощь и команды"))
async def help_command(message: Message):
    help_text = (
        "📋 **Команды бота:**\n\n"
        "🔹 `/setcity [город]` — сохранить ваш основной город.\n"
        "🔹 `/w [город]` — узнать погоду в любом месте.\n"
        "🔹 `/w` — погода в вашем сохраненном городе.\n"
        "🔹 `/help` — показать это сообщение.\n\n"
        "🏠 В личке можно просто писать название города."
    )
    await message.answer(help_text, parse_mode="Markdown")

#установка города
@dp.message(Command("setcity"))
async def set_city_command(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("⚠️ Напишите город. Пример: `/setcity Москва`")
        return
    await fetch_and_send_weather(message, args[1], is_setting_city=True)

#узнать погоду
@dp.message(Command("w", "weather"))
async def weather_command(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) >= 2:
        await fetch_and_send_weather(message, args[1], is_setting_city=False)
    else:
        uid = str(message.from_user.id)
        if uid in user_settings:
            await fetch_and_send_weather(message, user_settings[uid], is_setting_city=False)
        else:
            await message.reply("🏙 У вас не установлен город. Напишите `/setcity Город`.")

#гео
@dp.message(F.location)
async def weather_by_location(message: Message):
    save_user_id(message.from_user.id)
    lat, lon = message.location.latitude, message.location.longitude
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric&lang=ru"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=15, ssl=ssl_context) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user_settings[str(message.from_user.id)] = data.get("name")
                    save_user_settings(user_settings)
                    await process_weather_data(message, data)
                else:
                    await message.reply("❌ Не удалось определить погоду по локации.")
        except:
            await message.reply("⚠️ Ошибка сервера погоды.")

#конец
@dp.message(F.text)
async def text_handler(message: Message):
    #игнор мусора в группах
    if message.chat.type != "private":
        return
    
    #если текст начинается с / 
    if message.text.startswith("/"):
        return

    #кнопка помощи
    if message.text == "📖 Помощь и команды":
        return

    save_user_id(message.from_user.id)
    city = message.text.replace("🏠 Мой город: ", "")
    await fetch_and_send_weather(message, city, is_setting_city=False)

#мозг запросов

async def fetch_and_send_weather(message: Message, city: str, is_setting_city: bool):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=15, ssl=ssl_context) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    real_name = data.get("name")
                    
                    if is_setting_city:
                        user_settings[str(message.from_user.id)] = real_name
                        save_user_settings(user_settings)
                        await message.reply(f"✅ Город **{real_name}** сохранен!", parse_mode="Markdown")
                    
                    await process_weather_data(message, data)
                else:
                    await message.reply("❌ Город не найден. Проверьте название.")
        except asyncio.TimeoutError:
            await message.reply("⚠️ Сервер погоды не отвечает.")
        except:
            await message.reply("⚠️ Ошибка сети.")

async def process_weather_data(message: Message, data: dict):
    try:
        city_raw = data.get("name", "Неизвестно")
        city_in_case = get_city_prepositional(city_raw)
        temp = round(data["main"]["temp"])
        desc = data["weather"][0]["description"].capitalize()
        wind = data["wind"]["speed"]
        hum = data["main"]["humidity"]

        text = (f"📍 Погода в {city_in_case}:\n"
                f"🌡 Температура: {temp}°C\n"
                f"☁️ На улице: {desc}\n"
                f"💧 Влажность: {hum}%\n"
                f"💨 Ветер: {wind} м/с")
        
        await message.answer(text, reply_markup=main_keyboard(message.from_user.id, message.chat.type))
    except:
        await message.answer("⚠️ Ошибка обработки данных.")

#запуск

async def main():
    print("Метео-бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
