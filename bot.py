import os
import uuid
import sqlite3
import asyncio
import logging
from pathlib import Path
from typing import List, Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from elevenlabs.client import ElevenLabs
import imageio_ffmpeg

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = "8933394511:AAGS2vZzoGop39HMYQTzn5HppFLeqvs-LEg"
ELEVENLABS_API_KEY = "sk_2645eb8c6ab7457d5661f30bc9935e8107560bec586b14c8"
ADMIN_ID = 7662888182
ADMIN_USERNAME = "Captions_Admin"
ADMIN_PHONE = "+998 (93) 495-10-89"
REQUIRED_CHANNEL = "@Auto_Captions"
CARD_NUMBER = "5614686505428600"
CARD_HOLDER = "Toshpulatov Shoxrux"

MAX_VIDEO_BYTES = 50 * 1024 * 1024
WORK_ROOT = Path("temp_processing")
DB_FILE = Path("database.db")
INITIAL_CREDITS = 1

router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡ Auto Subtitr qo'yish")],
            [KeyboardButton(text="🎨 Subtitr uslublari"), KeyboardButton(text="💳 Balans")],
            [KeyboardButton(text="💎 PRO Tariflar"), KeyboardButton(text="📜 Oferta")],
            [KeyboardButton(text="👨‍💻 Admin bilan bog'lanish")]
        ],
        resize_keyboard=True
    )


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 1,
                is_pro INTEGER DEFAULT 0,
                bot_lang TEXT DEFAULT 'uz',
                terms_accepted INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def get_user_credits(user_id: int, username: str = "") -> int:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "INSERT INTO users (user_id, username, credits, is_pro, bot_lang, terms_accepted) VALUES (?, ?, ?, 0, 'uz', 0)",
                (user_id, username, INITIAL_CREDITS)
            )
            conn.commit()
            return INITIAL_CREDITS
        return row[0]


def is_user_pro(user_id: int) -> bool:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_pro FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return bool(row and row[0] == 1)


def deduct_user_credit(user_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET credits = credits - 1 WHERE user_id = ?", (user_id,))
        conn.commit()


async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception:
        pass
    return False


async def burn_subtitles_with_drawtext(input_video: Path, words: List[Any], output_video: Path):
    # FFmpeg drawtext filtrlari orqali har bir so'zni o'z vaqtida ekranning o'rtasiga chiqarish
    filter_parts = []
    
    # Matn vaqtlari bo'yicha filterlarni yig'amiz
    chunk_size = 3
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        if not chunk:
            continue
        start_t = chunk[0].get('start', 0.0) if isinstance(chunk[0], dict) else getattr(chunk[0], 'start', 0.0)
        end_t = chunk[-1].get('end', start_t + 1.5) if isinstance(chunk[-1], dict) else getattr(chunk[-1], 'end', start_t + 1.5)

        text_words = []
        for w in chunk:
            w_text = w.get('word', '').strip() if isinstance(w, dict) else getattr(w, 'word', '').strip()
            if w_text:
                text_words.append(w_text)
        
        line_text = " ".join(text_words).replace("'", "").replace(":", "")
        if not line_text:
            continue

        # drawtext parametrlari: rang sariq, shrift o'lchami 70, pastki qism markazida
        draw = (
            f"drawtext=text='{line_text}':fontcolor=yellow:fontsize=70:"
            f"x=(w-text_w)/2:y=h-300:"
            f"enable='between(t,{start_t},{end_t})'"
        )
        filter_parts.append(draw)

    vf_filter = ",".join(filter_parts) if filter_parts else "null"

    cmd = [
        FFMPEG_PATH, "-y", "-i", str(input_video),
        "-vf", vf_filter,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "copy",  # Asl ovozni o'zgartirmasdan to'g'ridan-to'g'ri ko'chiradi
        str(output_video)
    ]
    
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode != 0:
        log.error(f"FFmpeg error: {stderr.decode('utf-8', errors='ignore')}")
        raise RuntimeError("Videoga subtitr yopishtirishda xatolik yuz berdi.")


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    get_user_credits(user_id, message.from_user.username or "")
    
    if REQUIRED_CHANNEL and not await check_subscription(bot, user_id):
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"))
        builder.row(InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub"))
        await message.answer(f"Botdan foydalanish uchun kanalimizga obuna bo'ling:\n{REQUIRED_CHANNEL}", reply_markup=builder.as_markup())
        return

    await message.answer("Assalomu alaykum! Videongizni yuboring, ovozi va asl o'lchami mutlaqo o'zgarmagan holda subtitr qo'shib beraman.", reply_markup=get_main_keyboard())


@router.message(Command("pro"))
async def cmd_make_pro(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Bu buyruq faqat admin uchun!")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Ishlatish uchun: `/pro USER_ID`", parse_mode="Markdown")
        return
    try:
        target_user_id = int(args[1])
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_pro = 1, credits = 999 WHERE user_id = ?", (target_user_id,))
            if cursor.rowcount == 0:
                cursor.execute("INSERT INTO users (user_id, username, credits, is_pro, bot_lang, terms_accepted) VALUES (?, ?, 999, 1, 'uz', 1)", (target_user_id, ""))
            conn.commit()
        await message.answer(f"Foydalanuvchi ({target_user_id}) PRO qilindi va balansi 999 boldi! ✅")
    except Exception as e:
        await message.answer(f"Xatolik: {e}")


@router.message(F.text == "⚡ Auto Subtitr qo'yish")
async def cmd_auto(message: Message):
    await message.answer("Marhamat, videoni yuboring (MP4, 50MB gacha).")


@router.message(F.video | F.document)
async def handle_video(message: Message, bot: Bot):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    
    if credits <= 0 and not is_user_pro(user_id):
        await message.answer("Balansingizda urinishlar qolmadi. PRO tarifga o'ting!")
        return

    video = message.video or message.document
    if message.document and not message.document.mime_type.startswith('video/'):
        await message.answer("Iltimos, haqiqiy video yuboring!")
        return

    if video.file_size > MAX_VIDEO_BYTES:
        await message.answer("Video hajmi 50 MB dan oshmasligi kerak.")
        return

    status_msg = await message.answer("⏳ Video qabul qilindi. Ovoz va subtitr tayyorlanmoqda...")

    input_video = None
    output_video = None

    try:
        file_info = await bot.get_file(video.file_id)
        uid = str(uuid.uuid4())
        input_video = WORK_ROOT / f"{uid}_in.mp4"
        output_video = WORK_ROOT / f"{uid}_out.mp4"

        await bot.download_file(file_info.file_path, destination=input_video)

        with open(input_video, "rb") as audio_file:
            transcript = el_client.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v2",
                language_code="uz"
            )

        words = []
        if hasattr(transcript, "words") and transcript.words:
            words = transcript.words
        elif isinstance(transcript, dict) and "words" in transcript:
            words = transcript["words"]

        if not words:
            await status_msg.edit_text("❌ Videodan so'zlar aniqlanmadi.")
            return

        await burn_subtitles_with_drawtext(input_video, words, output_video)

        await message.answer_video(video=FSInputFile(str(output_video)), caption="✅ Tayyor! Ovoz va asl o'lcham saqlandi.")
        
        if not is_user_pro(user_id):
            deduct_user_credit(user_id)

        await status_msg.delete()

    except Exception as e:
        log.error(f"Xato: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
    finally:
        for p in [input_video, output_video]:
            if p and p.exists():
                try:
                    p.unlink()
                except:
                    pass


@router.message(F.text == "💳 Balans")
async def cmd_balance(message: Message):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    pro = "Ha (Cheksiz)" if is_user_pro(user_id) else "Yo'q"
    await message.answer(f"ID: {user_id}\nQolgan urinishlar: {credits} ta\nPRO status: {pro}")


@router.message(F.text == "💎 PRO Tariflar")
async def cmd_tariffs(message: Message):
    await message.answer(f"PRO tarif: 49,000 so'm\nKarta: `{CARD_NUMBER}` ({CARD_HOLDER})\nAdminga yozing: @{ADMIN_USERNAME}", parse_mode="Markdown")


@router.message(F.text == "📜 Oferta")
async def cmd_oferta(message: Message):
    await message.answer("Foydalanish shartlari oddiy: xizmat avtomatik subtitr qo'shib beradi.")


@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def cmd_admin(message: Message):
    await message.answer(f"Admin: @{ADMIN_USERNAME}")


async def main():
    if not WORK_ROOT.exists():
        WORK_ROOT.mkdir(parents=True)
    init_db()
    
    bot = Bot(token=BOT_TOKEN, session=AiohttpSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    log.info("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
