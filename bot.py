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
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from elevenlabs.client import ElevenLabs

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# --- SOZLAMALAR ---
BOT_TOKEN = "8933394511:AAGS2vZzoGop39HMYQTzn5HppFLeqvs-LEg"
ELEVENLABS_API_KEY = "sk_2645eb8c6ab7457d5661f30bc9935e8107560bec586b14c8"
ADMIN_ID = 7662888182
ADMIN_USERNAME = "Captions_Admin"
ADMIN_PHONE = "+998 (93) 495-10-89"

REQUIRED_CHANNEL = "@Auto_Captions" 

CARD_NUMBER = "5614 6865 0542 8600"
CARD_HOLDER = "Toshpulatov Shoxrux"

MAX_VIDEO_BYTES = 50 * 1024 * 1024
WORK_ROOT = Path("temp_processing")
FONTS_DIR = Path(".")
DB_FILE = Path("database.db")
INITIAL_CREDITS = 3

VIDEO_LANGS = {
    "uz": ("🇺🇿 O'zbekcha", "uz"),
    "ru": ("🇷🇺 Ruscha", "ru"),
    "en": ("🇬🇧 Inglizcha", "en"),
}

FONTS_LIST = {
    "komika": ("Komika Axis (MrBeast Style)", "KomikaAxis.ttf"),
    "coolvetica": ("Coolvetica (Clean & Modern)", "coolvetica.ttf"),
}

COLORS = {
    "white":  ("⚪ 100% Oppoq (Pro)", (255, 255, 255)),
    "yellow": ("🟡 Sariq (MrBeast Style)", (255, 255, 0)),
    "green":  ("🟢 Yashil", (0, 255, 0)),
}

SIZES = {
    "small":  ("📉 Kichik", 60),
    "normal": ("📐 Standart", 85),
    "large":  ("📈 Katta (MrBeast)", 110),
}

ANIMATION_STYLES = {
    "mrbeast_style": {
        "title": "🟢 Komika Axis Pop-up Style (⭐)",
        "desc": "Klassik qalin pop-up va sakrab chiqish animatsiyasi"
    },
    "smooth_tracking": {
        "title": "✨ Smooth Text Tracking",
        "desc": "Harflarning silliq tarqalib va kengayib borish effekti"
    },
    "active_bold_regular": {
        "title": "🔥 Active Bold / Regular",
        "desc": "Gapirilayotgan so'z qalin va ajralib turadi"
    },
    "active_word_box": {
        "title": "⬛ Active Word Highlight (Box Style)",
        "desc": "So'z orqasida qora fonli to'rtburchak blok bo'ladi"
    }
}

jobs: Dict[str, Dict[str, Any]] = {}
router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="⚡ Auto Subtitr qo'yish")],
        [KeyboardButton(text="🎨 Subtitr uslublari"), KeyboardButton(text="💳 Balans")],
        [KeyboardButton(text="💰 To'lov qilish"), KeyboardButton(text="📜 Oferta")],
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
                credits INTEGER DEFAULT 3,
                bot_lang TEXT DEFAULT 'uz',
                terms_accepted INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def get_user_data(user_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT credits, bot_lang, terms_accepted FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()


def get_user_credits(user_id: int, username: str = "") -> int:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, username, credits, bot_lang, terms_accepted) VALUES (?, ?, ?, 'uz', 0)",
                (user_id, username, INITIAL_CREDITS)
            )
            conn.commit()
            return INITIAL_CREDITS
        return row[0]


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
    if not REQUIRED_CHANNEL or REQUIRED_CHANNEL == "@sizning_kanal":
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception:
        pass
    return False


def format_ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{mins:02d}:{secs:02d}.{centis:02d}"


def rgb_to_ass(rgb: tuple) -> str:
    r, g, b = rgb
    return f"&H00{b:02X}{g:02X}{r:02X}"


def generate_word_by_word_ass(words: List[Any], ass_path: Path, text_color: tuple, font_size: int, font_key: str, anim_style: str) -> int:
    color_hex = rgb_to_ass(text_color)
    font_filename = FONTS_LIST.get(font_key, ("KOMIKA AXIS", "KomikaAxis.ttf"))[1]
    font_file = (FONTS_DIR / font_filename).resolve()
    
    if not font_file.exists():
        font_file = (FONTS_DIR / "KomikaAxis.ttf").resolve()

    font_path_str = str(font_file).replace("\\", "/")
    font_tag = f"\\fn{font_path_str}"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WordStyle,Arial,{font_size},{color_hex},&H000000FF,&HFF000000,&H80000000,0,0,0,0,100,100,2,0,1,5.0,2.0,2,40,40,450,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    cleaned_words = []
    for w in words:
        raw_text = getattr(w, "text", None) or getattr(w, "word", None) or ""
        start = float(getattr(w, "start", 0.0))
        end = float(getattr(w, "end", start + 0.35))
        clean = str(raw_text).strip().upper()
        for ch in [".", ",", "!", "?", ":", ";", '"', "'", "-", "—", "_"]:
            clean = clean.replace(ch, "")
        if clean:
            if (end - start) < 0.4:
                end = start + 0.4
            cleaned_words.append({"word": clean, "start": start, "end": end})

    if not cleaned_words:
        return 0

    count = 0
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header)
        for i, w in enumerate(cleaned_words):
            start_sec = w["start"]
            if i + 1 < len(cleaned_words):
                next_start = cleaned_words[i + 1]["start"]
                end_sec = min(w["end"], next_start)
                if end_sec <= start_sec:
                    end_sec = start_sec + 0.4
            else:
                end_sec = w["end"]

            start_fmt = format_ass_time(start_sec)
            end_fmt = format_ass_time(end_sec)
            word_text = w["word"]
            duration_ms = int((end_sec - start_sec) * 1000)

            if anim_style == "mrbeast_style":
                pro_anim = f"{{\\an2{font_tag}\\fad(40,80)\\fscx120\\fscy120\\t(0,60,\\fscx100\\fscy100)\\b0}}"
            elif anim_style == "smooth_tracking":
                pro_anim = f"{{\\an2{font_tag}\\fad(40,80)\\fsp2\\t(0,{duration_ms},\\fsp12)\\b0}}"
            elif anim_style == "active_bold_regular":
                pro_anim = f"{{\\an2{font_tag}\\fad(40,80)\\b0}}"
            elif anim_style == "active_word_box":
                pro_anim = f"{{\\an2{font_tag}\\fad(40,80)\\b0}}"
            else:
                pro_anim = f"{{\\an2{font_tag}\\fad(40,80)\\b0}}"

            f.write(f"Dialogue: 0,{start_fmt},{end_fmt},WordStyle,,0,0,0,,{pro_anim}{word_text}\n")
            count += 1

    return count


async def process_job(bot: Bot, job: Dict[str, Any]) -> None:
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    file_id = job["file_id"]
    lang = job["lang"]
    font_key = job["font"]
    color = job["color"]
    font_size = job["size"]
    anim_style = job["style"]
    job_key = job["key"]

    work_dir = WORK_ROOT / job_key
    work_dir.mkdir(parents=True, exist_ok=True)

    input_video = work_dir / "input.mp4"
    audio_path = work_dir / "audio.mp3"
    ass_path = work_dir / "subtitles.ass"
    output_video = work_dir / "output.mp4"

    status_msg = await bot.send_message(
        chat_id,
        "⚡ <b>Pro AI Subtitr ishga tushdi!</b>\n\n"
        "▓░░░░░░░░░ 15%\n\n"
        "📥 <i>Video yuklanmoqda...</i>",
        parse_mode="HTML"
    )

    try:
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise Exception("Telegram video yo'lini bermadi.")

        await bot.download_file(file.file_path, destination=input_video)

        await status_msg.edit_text(
            "⚡ <b>Pro AI Subtitr ishga tushdi!</b>\n\n"
            "▓▓▓░░░░░░░ 40%\n\n"
            "🎙 <i>Audio tahlil qilinmoqda...</i>",
            parse_mode="HTML"
        )

        cmd_extract = [
            "ffmpeg", "-y", "-i", "input.mp4",
            "-vn", "-acodec", "libmp3lame", "-ar", "24000", "-ac", "1", "-b:a", "192k",
            "audio.mp3"
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd_extract, cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        await status_msg.edit_text(
            "⚡ <b>Pro AI Subtitr ishga tushdi!</b>\n\n"
            "▓▓▓▓▓▓░░░░ 70%\n\n"
            "✨ <i>Tanlangan shriftda subtitrlar tayyorlanmoqda...</i>",
            parse_mode="HTML"
        )

        def transcribe_audio():
            with open(audio_path, "rb") as af:
                return el_client.speech_to_text.convert(
                    file=("audio.mp3", af.read(), "audio/mpeg"),
                    model_id="scribe_v1",
                    language_code=lang,
                    tag_audio_events=False
                )

        transcription = await asyncio.to_thread(transcribe_audio)
        words = getattr(transcription, "words", []) or []

        count = generate_word_by_word_ass(words, ass_path, color, font_size, font_key, anim_style)
        if count == 0:
            await status_msg.edit_text("❌ Videoda nutq aniqlanmadi.")
            return

        abs_fonts_dir = str(FONTS_DIR.resolve())
        cmd_render = [
            "ffmpeg", "-y", "-i", "input.mp4",
            "-vf", f"ass=subtitles.ass:fontsdir='{abs_fonts_dir}'",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "output.mp4"
        ]

        proc_render = await asyncio.create_subprocess_exec(
            *cmd_render, cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc_render.communicate()

        if proc_render.returncode != 0:
            raise Exception(f"FFmpeg xatosi: {stderr.decode()[:200]}")

        deduct_user_credit(user_id)
        current_bal = get_user_credits(user_id)

        await status_msg.edit_text("📤 <b>Tayyor! Video yuborilmoqda...</b>", parse_mode="HTML")
        await bot.send_video(
            chat_id,
            video=FSInputFile(str(output_video)),
            caption=f"🔥 <b>Subtitr Tayyor!</b>\n\n💳 Balans: <b>{current_bal} ta video</b>",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
        await status_msg.delete()

    except Exception as e:
        error_detail = f"{type(e).__name__}: {str(e)}"
        log.error("Xatolik: %s", error_detail, exc_info=True)
        await status_msg.edit_text(f"❌ Xatolik yuz berdi:\n<code>{error_detail[:350]}</code>", parse_mode="HTML")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


OFERTA_FULL_TEXT = (
    "📜 <b>OMMAVIY OFERTA VA FOYDALANISH SHARTLARI</b>\n\n"
    "<b>1. UMUMIY QOIDALAR</b>\n"
    "1.1. Ushbu Ommaviy oferta foydalanuvchi va «Captions Pro» sun'iy intellekt botining ma'muriyati o'rtasidagi munosabatlarni tartibga soladi.\n"
    "1.2. Botdan foydalanishni boshlash orqali foydalanuvchi ushbu shartlarning barchasiga rozilik bildiradi.\n\n"
    "<b>2. XIZMAT KO'RSATISH TARTIBI</b>\n"
    "2.1. Bot yuborilgan videolarga sun'iy intellekt yordamida avtomatik ravishda dinamik subtitrlar qo'shib beradi.\n"
    "2.2. Videolar <b>9:16 vertikal (1080x1920)</b> formatda va hajmi <b>50 MB dan oshmagan</b> bo'lishi shart.\n\n"
    "<b>3. TO'LOV VA QAYTARIB BERMASLIK SHARTI</b>\n"
    "3.1. Sotib olingan kreditlar hech qanday holatda ortga qaytarilmaydi.\n"
    "3.2. To'lov faqat ko'rsatilgan karta raqamiga amalga oshirilishi shart.\n"
)


@router.message(Command("panel"))
async def cmd_admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda bu buyruqdan foydalanish huquqi yo'q!")
        return

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

    panel_text = (
        "🛠 <b>ADMIN PANEL</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users} ta</b>\n\n"
        "<b>Buyruq:</b>\n"
        "<code>/add [user_id] [kredit_soni]</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_stats")]
    ])
    await message.answer(panel_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "refresh_stats")
async def refresh_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Huquqingiz yo'q!", show_alert=True)
        return

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

    panel_text = (
        "🛠 <b>ADMIN PANEL</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users} ta</b>\n\n"
        "<b>Buyruq:</b>\n"
        "<code>/add [user_id] [kredit_soni]</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_stats")]
    ])
    try:
        await call.message.edit_text(panel_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer("Yangilandi!")


@router.message(Command("add"))
async def cmd_add_credits(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("⚠️ Xato format! Ishlatilishi:\n<code>/add [user_id] [kredit_soni]</code>", parse_mode="HTML")
        return
    
    try:
        target_user_id = int(parts[1])
        amount = int(parts[2])
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT credits FROM users WHERE user_id = ?", (target_user_id,))
            row = cursor.fetchone()
            
            if row is None:
                cursor.execute(
                    "INSERT INTO users (user_id, username, credits, bot_lang, terms_accepted) VALUES (?, '', ?, 'uz', 1)",
                    (target_user_id, amount)
                )
                new_balance = amount
            else:
                cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, target_user_id))
                new_balance = row[0] + amount
            conn.commit()
            
        await message.reply(f"✅ Foydalanuvchi (ID: <code>{target_user_id}</code>) balansiga <b>{amount} ta</b> kredit qo'shildi!\n💎 Yangi balans: <b>{new_balance} ta</b>", parse_mode="HTML")
        
        try:
            user_msg = (
                "🎉 <b>Tabriklaymiz! Balansingiz to'ldirildi!</b> 🚀\n\n"
                f"💎 Hisobingizga qo'shildi: <b>+{amount} ta video</b>\n"
                f"📊 Jami qolgan urinishlar: <b>{new_balance} ta video</b>\n\n"
                "✨ Endi bemalol videolaringizga professional subtitrlar qo'shishingiz mumkin!"
            )
            await bot.send_message(target_user_id, user_msg, parse_mode="HTML", reply_markup=get_main_keyboard())
        except Exception as e:
            log.warning(f"Foydalanuvchiga xabar yuborib bo'lmadi: {e}")

    except Exception as e:
        await message.reply(f"❌ Xatolik yuz berdi: {e}")


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    row = get_user_data(user_id)
    
    if row is None:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, username, credits, bot_lang, terms_accepted) VALUES (?, ?, ?, 'uz', 0)",
                (user_id, message.from_user.username or "", INITIAL_CREDITS)
            )
            conn.commit()
        row = (INITIAL_CREDITS, 'uz', 0)

    credits, bot_lang, terms_accepted = row

    if terms_accepted == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Roziman", callback_data="terms_accept"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data="terms_decline")
            ]
        ])
        await message.answer(OFERTA_FULL_TEXT, reply_markup=kb, parse_mode="HTML")
        return

    if not await check_subscription(bot, user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton(text="🔄 Obunani tekshirish", callback_data="check_sub")]
        ])
        await message.answer(
            "⚠️ <b>Botdan foydalanish uchun avval rasmiy kanalimizga a'zo bo'ling!</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return
    
    await message.answer(
        f"✨ Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
        f"🚀 Videongizni yuboring va mukammal subtitrga ega bo'ling!",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "terms_accept")
async def on_terms_accept(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET terms_accepted = 1 WHERE user_id = ?", (user_id,))
        conn.commit()

    await call.message.delete()
    await call.message.answer("✅ Shartlar qabul qilindi. Xush kelibsiz!", reply_markup=get_main_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "terms_decline")
async def on_terms_decline(call: CallbackQuery):
    await call.message.edit_text("❌ Shartlar rad etildi. Qaytadan boshlash uchun /start ni bosing.")


@router.callback_query(F.data == "check_sub")
async def on_check_sub(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    if await check_subscription(bot, user_id):
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi! Videongizni yuborishingiz mumkin.", reply_markup=get_main_keyboard(), parse_mode="HTML")
    else:
        await call.answer("❌ Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)


@router.message(F.text == "⚡ Auto Subtitr qo'yish")
async def cmd_auto_subtitr(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Avval kanalimizga a'zo bo'ling! /start ni bosing.")
        return
    await message.answer("🎬 Menga <b>9:16 vertikal videongizni</b> yuboring:", parse_mode="HTML")


@router.message(F.text == "🎨 Subtitr uslublari")
async def cmd_subtitr_styles(message: Message):
    await message.answer("🎨 <b>Subtitrlar tanlangan shrift va animatsiya uslubida</b> ishlaydi. Videongizni yuborib sozlab olishingiz mumkin!", parse_mode="HTML")


@router.message(F.text == "📜 Oferta")
async def show_oferta(message: Message):
    await message.answer(OFERTA_FULL_TEXT, parse_mode="HTML")


@router.message(F.text == "💳 Balans")
async def cmd_balans(message: Message):
    credits = get_user_credits(message.from_user.id)
    
    if credits <= 0:
        text = (
            f"📊 <b>Sizning profilingiz va balansingiz:</b>\n\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"💎 Qolgan urinishlar: <b>0 ta video</b>\n\n"
            f"⚠️ <i>Sizda bepul foydalanish limiti tugadi!</i>\n"
            f"🚀 Videolarga professional subtitr qo'shishni davom ettirish uchun quyidagi tariflardan birini tanlang va balansingizni to'ldiring:"
        )
    else:
        text = (
            f"📊 <b>Sizning profilingiz va balansingiz:</b>\n\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"💎 Qolgan urinishlar: <b>{credits} ta video</b>\n\n"
            f"📌 <i>Har bir video uchun 1 ta kredit sarflanadi.</i>"
        )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Tariflarni ko'rish va to'ldirish", callback_data="show_tariffs")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "show_tariffs")
async def on_show_tariffs(call: CallbackQuery):
    payment_text = (
        "💰 <b>Kreditlarni to'ldirish tariflari:</b>\n\n"
        "💎 <b>10 ta video</b> — 45,000 so'm\n"
        "💎 <b>25 ta video</b> — 95,000 so'm\n"
        "💎 <b>50 ta video</b> — 175,000 so'm\n\n"
        "💳 <b>To'lov uchun karta raqami:</b>\n"
        f"<code>{CARD_NUMBER}</code>\n"
        f"👤 <b>Karta egasi:</b> {CARD_HOLDER}\n\n"
        f"📸 Pulni o'tkazgandan so'ng, to'lov chekini quyidagi adminga yuboring:\n"
        f"👨‍💻 <b>Admin:</b> @{ADMIN_USERNAME}"
    )
    await call.message.edit_text(payment_text, parse_mode="HTML")
    await call.answer()


@router.message(F.text == "💰 To'lov qilish")
async def cmd_payment(message: Message):
    payment_text = (
        "💰 <b>Kreditlarni to'ldirish tariflari:</b>\n\n"
        "💎 <b>10 ta video</b> — 45,000 so'm\n"
        "💎 <b>25 ta video</b> — 95,000 so'm\n"
        "💎 <b>50 ta video</b> — 175,000 so'm\n\n"
        "💳 <b>To'lov uchun karta raqami:</b>\n"
        f"<code>{CARD_NUMBER}</code>\n"
        f"👤 <b>Karta egasi:</b> {CARD_HOLDER}\n\n"
        f"📸 Pulni o'tkazgandan so'ng, to'lov chekini quyidagi adminga yuboring:\n"
        f"👨‍💻 <b>Admin:</b> @{ADMIN_USERNAME}"
    )
    await message.answer(payment_text, parse_mode="HTML")


@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def cmd_contact_admin(message: Message):
    await message.answer(f"👨‍💻 Admin: @{ADMIN_USERNAME}\n📞 Tel: {ADMIN_PHONE}", parse_mode="HTML")


@router.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def on_video(message: Message, state: FSMContext, bot: Bot) -> None:
    if not await check_subscription(bot, message.from_user.id):
        await message.reply("⚠️ Avval kanalimizga a'zo bo'ling!")
        return

    await state.clear()
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    
    if credits <= 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Tariflarni ko'rish", callback_data="show_tariffs")]
        ])
        await message.reply("❌ <b>Balansingiz tugagan!</b>\n\nBepul foydalanish limiti tugadi. Davom etish uchun balansni to'ldiring:", reply_markup=kb, parse_mode="HTML")
        return

    media = message.video or message.document
    if (media.file_size or 0) > MAX_VIDEO_BYTES:
        await message.answer("❌ Video hajmi 50 MB dan oshmasligi kerak.")
        return

    key = uuid.uuid4().hex[:8]
    jobs[key] = {
        "key": key,
        "user_id": user_id,
        "chat_id": message.chat.id,
        "file_id": media.file_id,
        "lang": "uz",
        "font": "komika",
        "size": 85,
        "color": (255, 255, 0),
        "style": "mrbeast_style",
        "ts": time.time()
    }

    kb = InlineKeyboardBuilder()
    for code, (title, _) in VIDEO_LANGS.items():
        kb.button(text=title, callback_data=f"lang:{key}:{code}")
    kb.adjust(2)
    await message.reply("1️⃣ Tilni tanlang:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("lang:"))
async def on_lang(call: CallbackQuery) -> None:
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return
    _, key, code = parts
    job = jobs.get(key)
    if not job:
        await call.answer("Eskirgan so'rov yoki vaqt o'tdi.", show_alert=True)
        return

    job["lang"] = code
    kb = InlineKeyboardBuilder()
    for fkey, (title, _) in FONTS_LIST.items():
        kb.button(text=title, callback_data=f"font:{key}:{fkey}")
    kb.adjust(1)
    await call.message.edit_text("2️⃣ Shrift turini tanlang:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("font:"))
async def on_font(call: CallbackQuery) -> None:
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return
    _, key, fkey = parts
    job = jobs.get(key)
    if not job:
        await call.answer("Eskirgan so'rov yoki vaqt o'tdi.", show_alert=True)
        return

    job["font"] = fkey
    kb = InlineKeyboardBuilder()
    for skey, (title, _) in SIZES.items():
        kb.button(text=title, callback_data=f"size:{key}:{skey}")
    kb.adjust(1)
    await call.message.edit_text("3️⃣ Subtitr o'lchamini tanlang:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("size:"))
async def on_size(call: CallbackQuery) -> None:
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return
    _, key, skey = parts
    job = jobs.get(key)
    if not job:
        await call.answer("Eskirgan so'rov yoki vaqt o'tdi.", show_alert=True)
        return

    job["size"] = SIZES[skey][1]
    kb = InlineKeyboardBuilder()
    for cname, (title, _) in COLORS.items():
        kb.button(text=title, callback_data=f"col:{key}:{cname}")
    kb.adjust(2)
    await call.message.edit_text("4️⃣ Subtitr rangini tanlang:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("col:"))
async def on_color(call: CallbackQuery) -> None:
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return
    _, key, cname = parts
    job = jobs.get(key)
    if not job:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return

    job["color"] = COLORS[cname][1]
    kb = InlineKeyboardBuilder()
    for skey, sinfo in ANIMATION_STYLES.items():
        kb.button(text=sinfo["title"], callback_data=f"anim:{key}:{skey}")
    kb.adjust(1)
    await call.message.edit_text("5️⃣ Animatsiya uslubini tanlang:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("anim:"))
async def on_animation(call: CallbackQuery, bot: Bot) -> None:
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return
    _, key, skey = parts
    job = jobs.get(key)
    if not call.message:
        return
    if not job:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return

    job["style"] = skey
    jobs.pop(key, None)
    await call.message.edit_text("✅ Sozlamalar qabul qilindi. Tanlangan shriftda video tezkor tayyorlanmoqda...")
    asyncio.create_task(process_job(bot, job))


async def handle(request):
    return web.Response(text="Captions Pro Bot is live and running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def start_bot_polling():
    while True:
        bot = None
        try:
            session = AiohttpSession(timeout=600.0)
            bot = Bot(token=BOT_TOKEN, session=session)
            dp = Dispatcher(storage=MemoryStorage())
            dp.include_router(router)
            
            await bot.delete_webhook(drop_pending_updates=True)
            log.info("Captions Pro Bot ishga tushdi!")
            await dp.start_polling(bot, handle_as_tasks=True, drop_pending_updates=True)
        except Exception as e:
            log.warning(f"Tarmoq xatosi: {e}. Qayta ulanmoqda...")
            await asyncio.sleep(3)
        finally:
            if bot and bot.session:
                try:
                    await bot.session.close()
                except Exception:
                    pass


async def main() -> None:
    init_db()
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    asyncio.create_task(web_server())
    await start_bot_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
