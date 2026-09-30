import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Bot tokeningizni shu yerga yozasiz (yoki Render Environment'dan o'qiydi)
TOKEN = os.getenv("8933394511:AAF1-V046gT-ohnnh6Z0_weaLItustLEbhs") # Kerak bo'lsa tokeningizni tirnoq ichiga yozib qo'ying

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    await message.answer("Captions Pro Bot ishga tushdi!")

async def main():
    logging.info("Captions Pro Bot ishga tushdi!")
    logging.info("Start polling")
    
    # MUHIM: Eski seanslar va konfliktlarni majburan uzib yuboruvchi buyruq:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi!")