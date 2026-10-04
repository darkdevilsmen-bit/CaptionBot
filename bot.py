import os
import sys
import time
import uuid
import shutil
import sqlite3
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from elevenlabs.client import ElevenLabs
import imageio_ffmpeg

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# --- SOZLAMALAR ---
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
FONTS_DIR = Path(".")
DB_FILE = Path("database.db")
INITIAL_CREDITS = 0  # Boshlang'ich balans 0 ta video

VIDEO_LANGS = {
    "uz": "🇺🇿 O'zbekcha",
    "ru": "🇷🇺 Ruscha",
    "en": "🇬🇧 Inglizcha",
}

ANIMATION_STYLES = {
    "mrbeast_style": "🟢 Komika Axis Pop-up (MrBeast)",
    "smooth_tracking": "✨ Smooth Text Tracking (Fade)",
    "active_bold_regular": "🔥 Active Bold / Regular",
    "active_word_box": "⬛ Active Word Highlight (Box)"
}

TEXT_COLORS = {
    "yellow": ("🟡 Sariq (Yorqin)", "&H0000FFFF"),
    "white": ("⚪ Oq (Klassik)", "&H00FFFFFF"),
    "green": ("🟢 Yashil (Neon)", "&H0000FF00"),
    "cyan": ("🔵 Havorang", "&H00FFFF00")
}

FONT_SIZES = {
    "small": ("🔽 Kichik (70)", 70),
    "normal": ("📱 Normal (85)", 85),
    "large": ("📈 Katta (100)", 100),
    "xlarge": ("🔥 Juda katta (115)", 115)
}

router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

USER_SESSIONS: Dict[int, Dict[str, Any]] = {}


def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="⚡ Auto Subtitr qo'yish")],
        [KeyboardButton(text="🎨 Subtitr uslublari"), KeyboardButton(text="💳 Balans")],
        [KeyboardButton(text="💎 PRO Tariflar"), KeyboardButton(text="📜 Oferta")],
        [KeyboardButton(text="👨‍💻 Admin bilan bog'lanish")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 0,
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
                "INSERT OR IGNORE INTO users (user_id, username, credits, is_pro, bot_lang, terms_accepted) VALUES (?, ?, ?, 0, 'uz', 0)",
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


def deduct_user_credit(user_id: int) -> bool:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] > 0:
            cursor.execute("UPDATE users SET credits = credits - 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            return True
        return False


async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        log.error(f"Obunani tekshirishda xatolik: {e}")
    return False


def format_ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{mins:02d}:{secs:02d}.{centis:02d}"


def generate_word_by_word_ass(words: List[Any], ass_path: Path, anim_style: str, text_color_hex: str, font_size: int) -> int:
    header = f"""[Script Info]
ScriptType: v4.00+
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},{text_color_hex},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,10,10,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues = []
    chunk_size = 5
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        if not chunk:
            continue
        
        first_w = chunk[0]
        start_t = first_w.start if hasattr(first_w, 'start') else first_w.get('start', 0.0)
        
        last_w = chunk[-1]
        end_t = last_w.end if hasattr(last_w, 'end') else last_w.get('end', start_t + 1.0)

        line_parts = []
        for j, w in enumerate(chunk):
            w_text = w.word if hasattr(w, 'word') else w.get('word', '')
            w_text = w_text.strip()
            if not w_text:
                continue
            
            highlighted_word = f"{{\\c&H0000FFFF&}}{w_text}{{\\c{text_color_hex}&}}"
            
            if anim_style == "mrbeast_style":
                animated_word = f"{{\\t(0,100,\\fscx120\\fscy120)\\t(100,200,\\fscx100\\fscy100)}}{highlighted_word}"
            else:
                animated_word = highlighted_word
            line_parts.append(animated_word)

        text_content = " ".join(line_parts)
        if text_content:
            dialogues.append(f"Dialogue: 0,{format_ass_time(start_t)},{format_ass_time(end_t)},Default,,0,0,0,,{text_content}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(dialogues) + "\n")
    return len(dialogues)


async def burn_subtitles_to_video(input_video: Path, ass_path: Path, output_video: Path):
    vf_filter = "subtitles=" + str(ass_path).replace("\\", "/")
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(input_video),
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        str(output_video)
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        log.error(f"FFmpeg error: {stderr.decode('utf-8', errors='ignore')}")
        raise RuntimeError("Videoga subtitr yopishtirishda xatolik yuz berdi.")


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    get_user_credits(user_id, username)
    
    if REQUIRED_CHANNEL and not await check_subscription(bot, user_id):
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"))
        builder.row(InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub"))
        await message.answer(
            f"Botimizdan to'liq foydalanish uchun avval rasmiy kanalimizga obuna bo'ling:\n{REQUIRED_CHANNEL}",
            reply_markup=builder.as_markup()
        )
        return

    await message.answer(
        "Assalomu alaykum! Auto Subtitles botiga xush kelibsiz.\n"
        "Videongizga professional darajada avtomatik subtitrlar qo'shib beraman.",
        reply_markup=get_main_keyboard()
    )


# --- ADMIN KOMANDALARI (/add va /pro) ---
@router.message(Command("add"))
async def cmd_add_credits(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Ishlatish: /add [user_id] [miqdor]")
        return
    try:
        target_user_id = int(args[1])
        amount = int(args[2])
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, target_user_id))
            conn.commit()
        await message.answer(f"Foydalanuvchi ({target_user_id}) balansiga {amount} ta video qo'shildi.")
    except Exception as e:
        await message.answer(f"Xatolik: {e}")


@router.message(Command("pro"))
async def cmd_set_pro(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Ishlatish: /pro [user_id]")
        return
    try:
        target_user_id = int(args[1])
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target_user_id,))
            conn.commit()
        await message.answer(f"Foydalanuvchi ({target_user_id}) PRO statusga o'tkazildi.")
    except Exception as e:
        await message.answer(f"Xatolik: {e}")


@router.callback_query(F.data == "check_sub")
async def callback_check_sub(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    if await check_subscription(bot, user_id):
        await callback.message.delete()
        await callback.message.answer(
            "Obunangiz tasdiqlandi! Xush kelibsiz.",
            reply_markup=get_main_keyboard()
        )
    else:
        await callback.answer("Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)


@router.message(F.text == "⚡ Auto Subtitr qo'yish")
async def cmd_auto_subtitles(message: Message):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    
    if credits <= 0 and not is_user_pro(user_id):
        await message.answer(
            "Balansingizda video yaratish uchun urinishlar qolmadi.\n\n"
            "Ko'proq video yaratish uchun PRO tarifga o'ting",
            reply_markup=get_main_keyboard()
        )
        return
        
    await message.answer(
        "Marhamat, subtitr qo'shilishi kerak bo'lgan videoni yuboring.\n\n"
        "(Video formati MP4, hajmi 50 MB dan oshmasligi kerak)",
        reply_markup=get_main_keyboard()
    )


# --- VIDEO KELGANDA QABUL QILISH (HANDLER) ---
@router.message(F.video)
async def handle_video(message: Message, bot: Bot):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    
    if credits <= 0 and not is_user_pro(user_id):
        await message.answer(
            "Balansingizda video yaratish uchun urinishlar qolmadi.\n\n"
            "Ko'proq video yaratish uchun PRO tarifga o'ting",
            reply_markup=get_main_keyboard()
        )
        return

    status_msg = await message.answer("✨ Subtitrlar tayyorlanmoqda, iltimos kuting...")
    
    try:
        user_dir = WORK_ROOT / str(uuid.uuid4())
        user_dir.mkdir(parents=True, exist_ok=True)
        
        input_video = user_dir / "input.mp4"
        output_video = user_dir / "output.mp4"
        ass_path = user_dir / "subs.ass"
        
        file_info = await bot.get_file(message.video.file_id)
        await bot.download_file(file_info.file_path, destination=input_video)
        
        # ElevenLabs orqali ovozni matnga o'girish va subtitr yasash
        with open(input_video, "rb") as audio_file:
            transcript = el_client.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v1",
                tag_audio_events=False
            )
        
        words = getattr(transcript, "words", [])
        if not words:
            await status_msg.edit_text("❌ Videodan ovoz topilmadi yoki matnga o'girib bo'lmadi.")
            shutil.rmtree(user_dir, ignore_errors=True)
            return
            
        generate_word_by_word_ass(
            words=words,
            ass_path=ass_path,
            anim_style="mrbeast_style",
            text_color_hex="&H00FFFFFF",
            font_size=85
        )
        
        await burn_subtitles_to_video(input_video, ass_path, output_video)
        
        if not is_user_pro(user_id):
            deduct_user_credit(user_id)
            
        remaining_credits = get_user_credits(user_id)
        
        await message.answer_video(
            video=FSInputFile(output_video),
            caption=f"🔥 Subtitr Tayyor!\n\n💳 Qolgan balans: {remaining_credits} ta video",
            reply_markup=get_main_keyboard()
        )
        await status_msg.delete()
        shutil.rmtree(user_dir, ignore_errors=True)
        
    except Exception as e:
        log.error(f"Video qayta ishlashda xatolik: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")


@router.message(F.text == "🎨 Subtitr uslublari")
async def cmd_sub_styles(message: Message):
    styles_text = (
        "Subtitr uslublarini tanlash:\n\n"
        "Hozirda quyidagi animatsiya uslublari mavjud:\n"
        "1. Komika Axis Pop-up (MrBeast uslubi)\n"
        "2. Smooth Text Tracking (Fade)\n"
        "3. Active Bold / Regular\n"
        "4. Active Word Highlight (Box)\n\n"
        "Video yuborganingizdan so'ng uslubni tanlashingiz mumkin."
    )
    await message.answer(styles_text, reply_markup=get_main_keyboard())


@router.message(F.text == "💳 Balans")
async def cmd_balance(message: Message):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    pro_status = "PRO Tarif (Cheksiz)" if is_user_pro(user_id) else "Standard (Bepul)"
    await message.answer(
        f"Sizning balansingiz:\n\n"
        f"ID: {user_id}\n"
        f"Qolgan urinishlar: {credits} ta video\n"
        f"Status: {pro_status}",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "💎 PRO Tariflar")
async def cmd_pro_tariffs(message: Message):
    text = (
        "AVTO SUBTITR — PRO TARIFLAR\n\n"
        "Nima uchun PRO ga o'tish kerak?\n"
        "• Cheklovsiz videolar va tezkor ishlov berish\n"
        "• 2K Ultra HD sifat va mukammal shriftlar\n"
        "• Barcha turdagi premium animatsiyalar\n\n"
        "1 Oylik PRO: 49,000 so'm\n"
        "VIP Umrbod (Lifetime): 149,000 so'm\n\n"
        f"To'lov uchun karta (bosib nusxalash mumkin):\n`{CARD_NUMBER}`\n"
        f"Karta egasi: {CARD_HOLDER}\n\n"
        f"To'lovni amalga oshirgach, chekni darhol adminga yuboring: @{ADMIN_USERNAME}"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")


@router.message(F.text == "📜 Oferta")
async def cmd_terms(message: Message):
    terms_text = (
        "Foydalanish shartlari va Ommaviy Oferta:\n\n"
        "1. Umumiy qoidalar:\n"
        "Ushbu shartnoma Auto Subtitles boti orqali taqdim etiladigan xizmatlardan foydalanish qoidalarini belgilaydi. Botdan foydalanishni boshlagan har bir shaxs ushbu shartlarga to'liq rozilik bildirgan hisoblanadi.\n\n"
        "2. Xizmatlar mazmuni:\n"
        "Bot foydalanuvchilar tomonidan yuborilgan videolarga sun'iy intellekt yordamida avtomatik subtitrlar (taglavhalar) qo'shib berish xizmatini ko'rsatadi.\n\n"
        "3. To'lovlar va tariflar:\n"
        "Xizmatlar pullik va bepul asosda taqdim etiladi. PRO tariflar uchun qilingan to'lovlar raqamli xizmat ko'rsatilganligi sababli qaytarilmaydi.\n\n"
        "4. Foydalanuvchi mas'uliyati:\n"
        "Foydalanuvchi yuklayotgan videolari O'zbekiston Respublikasi qonunchiligiga zid kelmasligini, mualliflik huquqlarini buzmasligini va boshqalarning huquqlarini poymol qilmasligini kafolatlaydi.\n\n"
        "5. Maxfiylik:\n"
        "Foydalanuvchining shaxsiy ma'lumotlari xavfsiz saqlanadi va uchinchi shaxslarga berilmaydi."
    )
    await message.answer(terms_text, reply_markup=get_main_keyboard())


@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def cmd_contact_admin(message: Message):
    await message.answer(
        f"Texnik yordam va Admin:\n\n"
        f"Murojaat uchun: @{ADMIN_USERNAME}\n"
        f"Telefon raqam: {ADMIN_PHONE}",
        reply_markup=get_main_keyboard()
    )


async def main():
    if not WORK_ROOT.exists():
        WORK_ROOT.mkdir(parents=True)
    init_db()
    
    session = AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Botni ishga tushirish / Asosiy menyu")
    ])
    
    log.info("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi.")
