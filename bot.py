import asyncio
import logging
import sys
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Tokeningizni yozing (yoki Render Environment'dan o'qish uchun qoldiring)
TOKEN = "8933394511:AAGDbBpKkvc9FWOBLR3ZZb1SMKpBbYeVxfE"  # Kerak bo'lsa o'z tokeningizni yozing

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    await message.answer("Captions Pro Bot ishga tushdi!")

# Render port talab qilgani uchun oddiy veb-server
async def handle(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render beradigan PORT'ni avtomatik ushlaydi
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    logging.info("Captions Pro Bot ishga tushdi!")
    
    # Veb-serverni fonda ishga tushiramiz (port ochish uchun)
    asyncio.create_task(web_server())
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Xatolik: {e}")
        
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")