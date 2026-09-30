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
from aiogram.fsm.state import State, StatesGroup
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
DB_FILE = Path("database.db")
INITIAL_CREDITS = 3

VIDEO_LANGS = {
    "uz": ("🇺🇿 O'zbekcha", "uz"),
    "ru": ("🇷🇺 Ruscha", "ru"),
    "en": ("🇬🇧 Inglizcha", "en"),
}

COLORS = {
    "white":  ("⚪ 100% Oppoq (Pro)", "&H00FFFFFF"),
    "yellow": ("🟡 Sariq (Captions Style)", "&H0000FFFF"),
    "green":  ("🟢 Yashil", "&H0000FF00"),
}

FONTS = {
    "coolvetica": {
        "title": "🖤 Coolvetica (Standart Pro)",
        "font_name": "Coolvetica"
    },
    "arial_black": {
        "title": "🅰️ Arial Bold (Pro)",
        "font_name": "Arial"
    },
    "bangers": {
        "title": "🔥 Bangers",
        "font_name": "Bangers"
    }
}
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from PIL import Image, ImageDraw, ImageFont

# Bot tokeningizni shu yerga yozing
TOKEN = "8933394511:AAGS2vZzoGop39HMYQTzn5HppFLeqvs-LEg"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def create_rounded_text_badge(text_content, box_color="green", font_size=70):
    # Ranglar palitrasi
    colors = {
        "green": (46, 204, 113),  # Yashil rang
        "red": (231, 76, 60),     # Qizil rang
    }
    bg_color = colors.get(box_color, box_color)

    # Shrift faylining aniq yo'li (bot.py turgan papkadan qidiradi)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Qaysi shrift ishlatilishini shu yerda tanlaysiz:
    # "Bangers-Regular.ttf" yoki "Coolvetica.ttf"
    font_filename = "Bangers-Regular.ttf" 
    font_path = os.path.join(current_dir, font_filename)

    # Shrift topilganini tekshiramiz, topilmasa ogohlantirib default shriftga o'tamiz
    if os.path.exists(font_path):
        try:
            font = ImageFont.truetype(font_path, font_size)
            print(f"Shrift muvaffaqiyatli yuklandi: {font_filename}")
        except Exception as e:
            print(f"Shriftni o'qishda xatolik: {e}")
            font = ImageFont.load_default()
    else:
        print(f"DIQQAT: {font_filename} topilmadi! Papkani tekshiring.")
        font = ImageFont.load_default()

    # Matn o'lchamlarini hisoblash
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = dummy_draw.textbbox((0, 0), text_content, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Plashka atrofi uchun bo'sh joy (padding)
    padding_x = 45
    padding_y = 25
    img_width = text_width + (padding_x * 2)
    img_height = text_height + (padding_y * 2)

    # Plashka rasmini yaratish (Shaffof fon bilan)
    badge_img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge_img)

    # Burchaklarni yumshatish radiusi (Corner box)
    corner_radius = 30
    draw.rounded_rectangle(
        [(0, 0), (img_width, img_height)], 
        radius=corner_radius, 
        fill=bg_color
    )

    # Matnni plashka o'rtasiga yozish (Oq rangda)
    text_x = (img_width - text_width) // 2 - bbox[0]
    text_y = (img_height - text_height) // 2 - bbox[1]
    draw.text((text_x, text_y), text_content, font=font, fill=(255, 255, 255, 255))

    # Vaqtinchalik faylga saqlash
    temp_filename = f"temp_badge_{os.getpid()}.png"
    badge_img.save(temp_filename)

    return temp_filename

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Matn ichidagi so'zga qarab rang tanlash
    color = "green" if "qosh" in text.lower() else "red"
    
    # Plashka rasmini hosil qilish
    badge_path = create_rounded_text_badge(text.upper(), box_color=color)
    
    # Foydalanuvchiga yuborish
    await update.message.reply_photo(photo=open(badge_path, 'rb'))
    
    # Vaqtinchalik faylni o'chirish
    if os.path.exists(badge_path):
        os.remove(badge_path)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot ishga tushdi va shriftlar sozlandi...")
    app.run_polling()

if __name__ == '__main__':
    main()

    # Matnni plashka o'rtasiga yozish (Oq rangda)
    text_x = (img_width - text_width) // 2 - bbox[0]
    text_y = (img_height - text_height) // 2 - bbox[1]
    draw.text((text_x, text_y), text_content, font=font, fill=(255, 255, 255, 255))

    # Vaqtinchalik faylga saqlash
    temp_filename = f"temp_badge_{os.getpid()}.png"
    badge_img.save(temp_filename)

    return temp_filename

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Matn ichida shartga qarab rang tanlash (masalan: "qosh" bo'lsa yashil, boshqa so'zda qizil)
    color = "green" if "qosh" in text.lower() else "red"
    
    # Plashka rasmini hosil qilish
    badge_path = create_rounded_text_badge(text.upper(), box_color=color)
    
    # Foydalanuvchiga tayyor rasm/plashkani yuborish
    await update.message.reply_photo(photo=open(badge_path, 'rb'))
    
    # Vaqtinchalik faylni o'chirib tashlash
    if os.path.exists(badge_path):
        os.remove(badge_path)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == '__main__':
    main()
ANIMATION_STYLES = {
    "mrbeast_style": {
        "title": "🟢 MrBeast Style (Tavsiya etiladi ⭐)",
        "desc": "So'zma-so'z pop-up va qalin qora konturli dinamik uslub"
    },
    "active_bold_regular": {
        "title": "🔥 Active Bold / Regular",
        "desc": "Gapirilayotgan so'z qalin, qolganlari oddiy ko'rinishda"
    },
    "active_word_box": {
        "title": "⬛ Active Word Highlight (Box Style)",
        "desc": "So'z orqasida qora fonli to'rtburchak blok bo'ladi"
    },
    "word_fade_in_out": {
        "title": "✨ Smooth Fade In & Out",
        "desc": "Mayin paydo bo'lib, sekin so'nib yo'qoluvchi klassik uslub"
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
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        if "terms_accepted" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN terms_accepted INTEGER DEFAULT 0")
        if "bot_lang" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN bot_lang TEXT DEFAULT 'uz'")
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
                "INSERT INTO users (user_id, username, credits, bot_lang, terms_accepted) VALUES (?, ?, ?, 'uz', 0)",
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


def generate_word_by_word_ass(words: List[Any], ass_path: Path, text_color: str, font_name: str, font_size: int, anim_style: str = "mrbeast_style") -> int:
    margin_v = 500

    if anim_style == "active_word_box":
        border_style = 3
        outline_val = 2.0
    else:
        border_style = 1
        outline_val = 4.0 if anim_style == "mrbeast_style" else 2.0
    
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WordStyle,{font_name},{font_size},{text_color},&H000000FF,&HFF000000,&H80000000,0,0,0,0,100,100,2,0,{border_style},{outline_val},2.0,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    cleaned_words = []
    for w in words:
        raw_text = getattr(w, "text", None) or getattr(w, "word", None) or ""
        start = float(getattr(w, "start", 0.0))
        end = float(getattr(w, "end", start + 0.20))

        clean = str(raw_text).strip().upper()
        for ch in [".", ",", "!", "?", ":", ";", '"', "'", "-", "—", "_"]:
            clean = clean.replace(ch, "")

        if clean:
            if end <= start:
                end = start + 0.18
            cleaned_words.append({"word": clean, "start": start, "end": end})

    if not cleaned_words:
        return 0

    count = 0
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header)

        for i, w in enumerate(cleaned_words):
            start_fmt = format_ass_time(w["start"])
            
            if i + 1 < len(cleaned_words):
                next_start = cleaned_words[i + 1]["start"]
                end_t = min(w["end"], next_start)
                if end_t <= w["start"]:
                    end_t = w["start"] + 0.30
            else:
                end_t = w["end"]

            end_fmt = format_ass_time(end_t)
            word_text = w["word"]

            if anim_style == "mrbeast_style":
                pro_anim = r"{\an2\fad(40,100)\fscx140\fscy140\t(0,50,\fscx100\fscy100)\b1}"
            elif anim_style == "active_bold_regular":
                pro_anim = r"{\an2\fad(60,100)\b1}"
            elif anim_style == "active_word_box":
                pro_anim = r"{\an2\fad(60,100)\b1}"
            elif anim_style == "word_fade_in_out":
                pro_anim = r"{\an2\fad(200,300)\b1}"
            else:
                pro_anim = r"{\an2\fad(100,150)\b1}"

            f.write(f"Dialogue: 0,{start_fmt},{end_fmt},WordStyle,,0,0,0,,{pro_anim}{word_text}\n")
            count += 1

    return count


async def process_job(bot: Bot, job: Dict[str, Any]) -> None:
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    file_id = job["file_id"]
    lang = job["lang"]
    color = job["color"]
    font_key = job.get("font", "coolvetica")
    font_info = FONTS.get(font_key, FONTS["coolvetica"])
    font_size = job.get("size", 100)
    anim_style = job.get("style", "mrbeast_style")
    job_key = job["key"]

    work_dir = WORK_ROOT / job_key
    work_dir.mkdir(parents=True, exist_ok=True)

    input_video = work_dir / "input.mp4"
    audio_path = work_dir / "audio.mp3"
    ass_path = work_dir / "subtitles.ass"
    output_video = work_dir / "output.mp4"

    status_msg = await bot.send_message(
        chat_id,
        "⚡ <b>Pro AI ishga tushdi!</b>\n\n"
        "▓░░░░░░░░░ 15%\n\n"
        "📥 <i>Video yuklanmoqda...</i>\n"
        "⏱ <i>Taxminan 15–20 soniya</i>",
        parse_mode="HTML"
    )

    try:
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise Exception("Telegram video yo'lini bermadi.")

        await bot.download_file(file.file_path, destination=input_video)

        await status_msg.edit_text(
            "⚡ <b>Pro AI ishga tushdi!</b>\n\n"
            "▓▓▓░░░░░░░ 40%\n\n"
            "🎙 <i>Audio tahlil qilinmoqda...</i>",
            parse_mode="HTML"
        )

        cmd_extract = [
            "ffmpeg", "-y", "-i", "input.mp4",
            "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", "-b:a", "96k",
            "audio.mp3"
        ]
        await asyncio.to_thread(subprocess.run, cmd_extract, cwd=str(work_dir), capture_output=True, text=True)

        await status_msg.edit_text(
            "⚡ <b>Pro AI ishga tushdi!</b>\n\n"
            "▓▓▓▓▓▓░░░░ 70%\n\n"
            "✨ <i>Animatsiya ulanmoqda...</i>",
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

        count = generate_word_by_word_ass(
            words=words,
            ass_path=ass_path,
            text_color=color,
            font_name=font_info["font_name"],
            font_size=font_size,
            anim_style=anim_style
        )

        if count == 0:
            await status_msg.edit_text("❌ Videoda nutq aniqlanmadi.")
            return

        cmd_render = [
            "ffmpeg", "-y", "-i", "input.mp4",
            "-vf", "ass=subtitles.ass",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "copy",
            "output.mp4"
        ]

        res = await asyncio.to_thread(subprocess.run, cmd_render, cwd=str(work_dir), capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"FFmpeg xatosi: {res.stderr[:150]}")

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


# --- TO'LIQ OFERTA MATNI ---
OFERTA_FULL_TEXT = (
    "📜 <b>OMMAVIY OFERTA VA FOYDALANISH SHARTLARI</b>\n\n"
    "<b>1. UMUMIY QOIDALAR</b>\n"
    "1.1. Ushbu Ommaviy oferta (keyingi o'rinlarda — Oferta) foydalanuvchi va «Captions Pro» sun'iy intellekt botining ma'muriyati o'rtasidagi huquqiy munosabatlarni tartibga soladi.\n"
    "1.2. Botdan foydalanishni boshlash, shu jumladan /start buyrug'ini bosish va «Roziman» tugmasini bosish orqali foydalanuvchi ushbu shartlarning barchasiga so'zsiz rozilik bildiradi.\n\n"
    "<b>2. XIZMAT KO'RSATISH TARTIBI VA TEXNIK TALABLAR</b>\n"
    "2.1. Bot foydalanuvchining yuborgan videolariga sun'iy intellekt yordamida avtomatik ravishda professional dinamik subtitrlar (animatsiyalar) qo'shib beradi.\n"
    "2.2. Videolar <b>9:16 vertikal (1080x1920)</b> formatda va hajmi <b>50 MB dan oshmagan</b> bo'lishi shart.\n"
    "2.3. Har bir muvaffaqiyatli ishlov berilgan video uchun foydalanuvchi balansidan 1 ta kredit (urinish) avtomatik ravishda yechiladi.\n\n"
    "<b>3. TO'LOV, NARXLAR VA QAYTARIB BERMASLIK SHARTI</b>\n"
    "3.1. Botda taqdim etilgan xizmatlar va kredit paketlari narxlari «To'lov qilish» bo'limida ko'rsatilgan va ma'muriyat tomonidan o'zgartirilishi mumkin.\n"
    "3.2. Sotib olingan kreditlar va amalga oshirilgan pul o'tkazmalari hech qanday holatda ortga qaytarilmaydi (возврат не предусмотрен).\n"
    "3.3. To'lov faqat ko'rsatilgan rasmiy karta raqamiga amalga oshirilishi va chek tasdiqlash uchun adminga yuborilishi kerak.\n\n"
    "<b>4. MAS'ULIYAT VA CHEGARALAR</b>\n"
    "4.1. Ma'muriyat internet tarmog'idagi uzilishlar, Telegram serverlarining nosozliklari yoki uchinchi tomon API xizmatlari (ElevenLabs, FFmpeg) ishidagi vaqtinchalik xatolar uchun javobgar emas.\n"
    "4.2. Foydalanuvchi mualliflik huquqini buzuvchi yoki qonunchilikka zid videolarni yuklamasligi shart.\n\n"
    "<i>Botdan foydalanishni davom ettirish uchun pastdagi tugmani bosing:</i>"
)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    row = get_user_data(user_id)
    
    if row is None:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (user_id, username, credits, bot_lang, terms_accepted) VALUES (?, ?, ?, 'uz', 0)",
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
            "⚠️ <b>Botdan foydalanish uchun avval rasmiy kanalimizga a'zo bo'ling!</b>\n\n"
            "Kanalga qo'shilgach, <b>'🔄 Obunani tekshirish'</b> tugmasini bosing:",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return
    
    await message.answer(
        f"✨ Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
        f"🚀 Ushbu bot yordamida videolaringizga professional, zamonaviy va dinamik subtitrlarni soniyalar ichida qo'shishingiz mumkin.\n\n"
        f"🎥 Videongizni yuboring va mukammal natijaga ega bo'ling!",
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
    
    if not await check_subscription(bot, user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton(text="🔄 Obunani tekshirish", callback_data="check_sub")]
        ])
        await call.message.answer(
            "⚠️ <b>Botdan foydalanish uchun avval rasmiy kanalimizga a'zo bo'ling!</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    await call.message.answer(
        "✅ Shartlar muvaffaqiyatli qabul qilindi! Xush kelibsiz.",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "terms_decline")
async def on_terms_decline(call: CallbackQuery):
    await call.message.edit_text("❌ Siz shartlarni rad etdingiz. Botdan foydalanish uchun /start buyrug'ini bosing va shartlarga rozilik bildiring.")


@router.callback_query(F.data == "check_sub")
async def on_check_sub(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    if await check_subscription(bot, user_id):
        await call.message.delete()
        await call.message.answer(
            f"✅ <b>Tabriklaymiz! Kanalga muvaffaqiyatli a'zo bo'ldingiz.</b>\n\n"
            f"🚀 Botdan foydalanish uchun endi videongizni yuborishingiz mumkin!",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
    else:
        await call.answer("❌ Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)


@router.message(F.text == "⚡ Auto Subtitr qo'yish")
async def cmd_auto_subtitr(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Avval kanalimizga a'zo bo'ling! /start buyrug'ini bosing.")
        return
    await message.answer("🎬 Menga <b>9:16 vertikal videongizni</b> yuboring:", parse_mode="HTML")


@router.message(F.text == "🎨 Subtitr uslublari")
async def cmd_subtitr_styles(message: Message):
    await message.answer(
        "🎨 <b>Pro Animatsiya Uslublari (4 ta):</b>\n\n"
        "🟢 <b>MrBeast Style</b>\n"
        "🔥 <b>Active Bold / Regular</b>\n"
        "⬛ <b>Active Word Highlight (Box Style)</b>\n"
        "✨ <b>Smooth Fade In & Out</b>\n\n"
        "<i>Videongizni yuborib ushbu uslublardan birini tanlashingiz mumkin!</i>",
        parse_mode="HTML"
    )


@router.message(F.text == "📜 Oferta")
async def show_oferta(message: Message):
    await message.answer(OFERTA_FULL_TEXT, parse_mode="HTML")


@router.message(F.text == "💳 Balans")
async def cmd_balans(message: Message):
    credits = get_user_credits(message.from_user.id)
    text = (
        f"📊 <b>Sizning profilingiz va balansingiz:</b>\n\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"💎 Qolgan urinishlar (kreditlar): <b>{credits} ta video</b>\n\n"
        f"📌 <i>Har bir video uchun 1 ta kredit sarflanadi. Kreditlar tugasa, «To'lov qilish» bo'limidan balansingizni to'ldirishingiz mumkin.</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💰 To'lov qilish")
async def cmd_payment(message: Message):
    payment_text = (
        "💰 <b>Kreditlarni to'ldirish narxlari:</b>\n\n"
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


@router.message(F.text == "👨‍‍💻 Admin bilan bog'lanish")
async def cmd_contact_admin(message: Message):
    await message.answer(
        f"👨‍💻 <b>Bog'lanish uchun ma'lumotlar:</b>\n\n"
        f"• Admin: @{ADMIN_USERNAME}\n"
        f"• Telefon: {ADMIN_PHONE}",
        parse_mode="HTML"
    )


@router.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def on_video(message: Message, state: FSMContext, bot: Bot) -> None:
    if not await check_subscription(bot, message.from_user.id):
        await message.reply("⚠️ Avval kanalimizga a'zo bo'ling! /start buyrug'ini bosing.")
        return

    await state.clear()
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    
    if credits <= 0:
        await message.reply("❌ Balansingiz tugagan! Videolarga subtitr qo'shish uchun balansni to'ldiring.")
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
        "style": "mrbeast_style",
        "color": None,
        "font": "coolvetica",
        "size": 100,
        "ts": time.time()
    }

    kb = InlineKeyboardBuilder()
    for code, (title, _) in VIDEO_LANGS.items():
        kb.button(text=title, callback_data=f"lang:{key}:{code}")
    kb.adjust(2)
    await message.reply("1️⃣ Tilni tanlang:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("lang:"))
async def on_lang(call: CallbackQuery) -> None:
    _, key, code = call.data.split(":")
    job = jobs.get(key)
    if not job:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return

    job["lang"] = code
    job["ts"] = time.time()

    kb = InlineKeyboardBuilder()
    for skey, sinfo in ANIMATION_STYLES.items():
        kb.button(text=sinfo["title"], callback_data=f"style:{key}:{skey}")
    kb.adjust(1)
    await call.message.edit_text("2️⃣ Pro animatsiya uslubini tanlang:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("style:"))
async def on_style(call: CallbackQuery) -> None:
    _, key, skey = call.data.split(":")
    job = jobs.get(key)
    if not job:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return

    job["style"] = skey
    job["ts"] = time.time()

    kb = InlineKeyboardBuilder()
    for cname, (title, _) in COLORS.items():
        kb.button(text=title, callback_data=f"col:{key}:{cname}")
    kb.adjust(2)
    await call.message.edit_text("3️⃣ Subtitr rangini tanlang:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("col:"))
async def on_color(call: CallbackQuery) -> None:
    _, key, cname = call.data.split(":")
    job = jobs.get(key)
    if not job:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return

    job["color"] = COLORS[cname][1]
    job["ts"] = time.time()

    kb = InlineKeyboardBuilder()
    for fname, fdata in FONTS.items():
        kb.button(text=fdata["title"], callback_data=f"font:{key}:{fname}")
    kb.adjust(2)
    await call.message.edit_text("4️⃣ Shrift turini tanlang:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("font:"))
async def on_font(call: CallbackQuery, bot: Bot) -> None:
    _, key, fname = call.data.split(":")
    job = jobs.get(key)
    if not job:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return

    job["font"] = fname
    jobs.pop(key, None)
    await call.message.edit_text("✅ Sozlamalar qabul qilindi. Video tayyorlanmoqda...")
    asyncio.create_task(process_job(bot, job))


# --- RENDER PORT OCHISH UCHUN WEB SERVER ---
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
            log.warning(f"Tarmoq xatosi: {e}. 3 soniyadan so'ng qayta ulanadi...")
            await asyncio.sleep(3)
        finally:
            if bot and bot.session:
                try:
                    await bot.session.close()
                except Exception:
                    pass


async def main() -> None:
    if BOT_TOKEN.startswith("BU_YERGA") or ELEVENLABS_API_KEY.startswith("BU_YERGA"):
        print("Iltimos, tokenlarni kiriting.")
        sys.exit(1)

    init_db()
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    
    # Render port talabini qondirish uchun web-serverni fonda ishga tushiramiz
    asyncio.create_task(web_server())
    
    await start_bot_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass