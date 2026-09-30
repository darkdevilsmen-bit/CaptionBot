import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Tokeningizni tirnoq ichiga yozing:
TOKEN = "8933394511:AAGDbBpKkvc9FWOBLR3ZZb1SMKpBbYeVxfE" 

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    await message.answer("Captions Pro Bot ishga tushdi!")

async def main():
    logging.info("Captions Pro Bot ishga tushdi!")
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