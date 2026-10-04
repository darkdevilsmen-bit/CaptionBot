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
INITIAL_CREDITS = 1

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
    "small": ("🔽 Kichik (50)", 50),
    "normal": ("📱 Normal (70)", 70),
    "large": ("📈 Katta (90)", 90),
    "xlarge": ("🔥 Juda katta (110)", 110)
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
Style: Default,Arial,{font_size},{text_color_hex},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,10,10,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    chunk_size = 5
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        if not chunk:
            continue
        start_t = chunk[0].start
        end_t = chunk[-1].end

        for idx, w in enumerate(chunk):
            w_start = w.start
            w_end = w.end
            text_parts = []
            for j, cw in enumerate(chunk):
                word_str = cw.text.strip()
                if not word_str:
                    continue
                if j == idx:
                    if anim_style == "mrbeast_style":
                        text_parts.pop() if text_parts else None
                        text_parts.append(f"{{\\c&H0000FFFF\\fscx120\\fscy120}}{word_str}{{\\r}}")
                    elif anim_style == "active_word_box":
                        text_parts.append(f"{{\\3c&H000000&\\4c&H00FFFF00&}}{word_str}{{\\r}}")
                    else:
                        text_parts.append(f"{{\\c&H00FFFF00&}}{word_str}{{\\r}}")
                else:
                    text_parts.append(word_str)
            
            line_text = " ".join(text_parts)
            s_str = format_ass_time(w_start)
            e_str = format_ass_time(w_end if w_end > w_start else w_start + 0.3)
            events.append(f"Dialogue: 0,{s_str},{e_str},Default,,0,0,0,,{line_text}")

    ass_path.write_text(header + "\n".join(events), encoding="utf-8")
    return len(words)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    get_user_credits(user_id, username)
    
    welcome_text = (
        "✨ **Assalomu alaykum! Auto Captions botiga xush kelibsiz.**\n\n"
        "Bu bot videolaringizga avtomatik tarzda professional va chiroyli subtitrlar (titrlar) qo'shib beradi.\n\n"
        "Pastdagi tugmalar yordamida kerakli bo'limni tanlang:"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")


@router.message(F.text == "💳 Balans")
async def show_balance(message: Message):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    pro_status = "Faol 💎" if is_user_pro(user_id) else "Faol emas"
    
    text = (
        f"💳 **Sizning balansingiz:**\n\n"
        f"🔹 Qolgan urinishlar: **{credits} ta**\n"
        f"⭐ PRO Status: **{pro_status}**\n\n"
        f"Ko'proq urinish sotib olish uchun PRO Tariflar bo'limiga o'ting."
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def contact_admin(message: Message):
    text = (
        f"👨‍💻 **Admin bilan bog'lanish:**\n\n"
        f"Murojaat uchun: @{ADMIN_USERNAME}\n"
        f"Telefon: {ADMIN_PHONE}"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "📜 Oferta")
async def show_terms(message: Message):
    text = (
        "📜 **Foydalanish shartlari (Oferta):**\n\n"
        "1. Bot xizmatlaridan foydalanganda qoidalarga amal qiling.\n"
        "2. To'lovlar qaytarilmaydi.\n"
        "3. Har qanday savollar bo'yicha adмин bilan bog'lanishingiz mumkin."
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "🎨 Subtitr uslublari")
async def show_styles(message: Message):
    user_id = message.from_user.id
    session = USER_SESSIONS.setdefault(user_id, {"anim": "mrbeast_style", "color": "yellow", "size": "normal"})
    
    text = (
        f"🎨 **Joriy sozlamalaringiz:**\n"
        f"• Uslub: {ANIMATION_STYLES.get(session['anim'])}\n"
        f"• Rang: {TEXT_COLORS.get(session['color'])[0]}\n"
        f"• O'lcham: {FONT_SIZES.get(session['size'])[0]}\n\n"
        f"O'zgartirish uchun pastdagi tugmalardan foydalaning:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Uslubni o'zgartirish", callback_data="set_anim"))
    builder.row(InlineKeyboardButton(text="Rangni o'zgartirish", callback_data="set_color"))
    builder.row(InlineKeyboardButton(text="O'lchamni o'zgartirish", callback_data="set_size"))
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("set_"))
async def process_settings_callback(callback: CallbackQuery):
    action = callback.data
    user_id = callback.from_user.id
    session = USER_SESSIONS.setdefault(user_id, {"anim": "mrbeast_style", "color": "yellow", "size": "normal"})
    
    builder = InlineKeyboardBuilder()
    if action == "set_anim":
        for k, v in ANIMATION_STYLES.items():
            builder.row(InlineKeyboardButton(text=v, callback_data=f"anim_{k}"))
        await callback.message.edit_text("Uslubni tanlang:", reply_markup=builder.as_markup())
    elif action == "set_color":
        for k, v in TEXT_COLORS.items():
            builder.row(InlineKeyboardButton(text=v[0], callback_data=f"color_{k}"))
        await callback.message.edit_text("Rangni tanlang:", reply_markup=builder.as_markup())
    elif action == "set_size":
        for k, v in FONT_SIZES.items():
            builder.row(InlineKeyboardButton(text=v[0], callback_data=f"size_{k}"))
        await callback.message.edit_text("O'lchamni tanlang:", reply_markup=builder.as_markup())
    elif action.startswith("anim_"):
        session["anim"] = action.split("_", 1)[1]
        await callback.answer("Uslub saqlandi!")
        await callback.message.edit_text("✅ Uslub muvaffaqiyatli yangilandi!")
    elif action.startswith("color_"):
        session["color"] = action.split("_", 1)[1]
        await callback.answer("Rang saqlandi!")
        await callback.message.edit_text("✅ Rang muvaffaqiyatli yangilandi!")
    elif action.startswith("size_"):
        session["size"] = action.split("_", 1)[1]
        await callback.answer("O'lcham saqlandi!")
        await callback.message.edit_text("✅ O'lcham muvaffaqiyatli yangilandi!")


@router.message(F.text == "⚡ Auto Subtitr qo'yish")
async def start_subtitling_flow(message: Message):
    await message.answer("Iltimos, subtitr qo'shmoqchi bo'lgan **videongizni yuboring** (maksimal hajm 50MB):", reply_markup=get_main_keyboard())


@router.message(F.video)
async def handle_video(message: Message, bot: Bot):
    user_id = message.from_user.id
    
    if not await check_subscription(bot, user_id):
        await message.answer(f"Botdan foydalanish uchun avval kanalimizga obuna bo'ling: {REQUIRED_CHANNEL}")
        return
        
    credits = get_user_credits(user_id, message.from_user.username or "")
    if credits <= 0 and not is_user_pro(user_id):
        await message.answer("❌ Balansingizda urinishlar qolmadi. Iltimos, tarif sotib oling yoki admin bilan bog'laning.")
        return

    if message.video.file_size > MAX_VIDEO_BYTES:
        await message.answer("❌ Video hajmi juda katta! Maksimal hajm: 50MB.")
        return

    status_msg = await message.answer("⏳ Video qabul qilindi, yuklab olinmoqda va qayta ishlanmoqda...")
    
    WORK_ROOT.mkdir(exist_ok=True)
    task_id = str(uuid.uuid4())
    task_dir = WORK_ROOT / task_id
    task_dir.mkdir(exist_ok=True)
    
    input_video = task_dir / "input.mp4"
    output_video = task_dir / "output.mp4"
    audio_path = task_dir / "audio.mp3"
    ass_path = task_dir / "subs.ass"
    
    try:
        file_info = await bot.get_file(message.video.file_id)
        await bot.download_file(file_info.file_path, destination=input_video)
        
        # Audio chiqarib olish
        cmd_audio = [FFMPEG_PATH, "-y", "-i", str(input_video), "-vn", "-acodec", "libmp3lame", str(audio_path)]
        subprocess.run(cmd_audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        await status_msg.edit_text("🎙️ ElevenLabs orqali ovozni matnga o'tkazish (Speech-to-Text) bajarilmoqda...")
        
        with open(audio_path, "rb") as f:
            transcript = el_client.speech_to_text.convert(
                file=f,
                model_id="scribe_v1",
                tag_audio_events=False
            )
            
        words = transcript.words if hasattr(transcript, 'words') else []
        if not words:
            await status_msg.edit_text("❌ Videodan so'zlar topilmadi yoki ovoz aniqlanmadi.")
            shutil.rmtree(task_dir, ignore_errors=True)
            return
            
        session = USER_SESSIONS.get(user_id, {"anim": "mrbeast_style", "color": "yellow", "size": "normal"})
        anim_style = session["anim"]
        color_hex = TEXT_COLORS.get(session["color"], TEXT_COLORS["yellow"])[1]
        f_size = FONT_SIZES.get(session["size"], FONT_SIZES["normal"])[1]
        
        generate_word_by_word_ass(words, ass_path, anim_style, color_hex, f_size)
        
        await status_msg.edit_text("🎨 Subtitrlar videoga yopishtirilmoqda (FFmpeg render)...")
        
        # Original resolution buzilmasligi uchun subtitles filter to'g'ridan-to'g'ri ishlatiladi
        escaped_ass = str(ass_path.resolve()).replace('\\', '/').replace(':', '\\:')
        cmd_render = [
            FFMPEG_PATH, "-y",
            "-i", str(input_video),
            "-vf", f"subtitles='{escaped_ass}'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            str(output_video)
        ]
        
        subprocess.run(cmd_render, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        if output_video.exists():
            deduct_user_credit(user_id)
            await status_msg.edit_text("📤 Tayyor video yuborilmoqda...")
            video_file = FSInputFile(output_video)
            await message.answer_video(video=video_file, caption="✨ Mana sizning subtitr qo'yilgan videongiz!")
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Videoni render qilishda xatolik yuz berdi.")
            
    except Exception as e:
        log.error(f"Video qayta ishlashda xato: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
    finally:
        shutil.rmtree(task_dir, ignore_errors=True)


async def main():
    init_db()
    session = AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Botni ishga tushirish")
    ])
    
    log.info("Bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
