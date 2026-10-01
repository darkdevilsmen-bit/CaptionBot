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

VIDEO_QUALITIES = {
    "720p": ("📱 Standard HD (720p) [Free]", "1280:720", False),
    "2k": ("💎 PRO 2K Ultra (1440p) [PRO]", "2560:1440", True)
}

router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)


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
                credits INTEGER DEFAULT 3,
                is_pro INTEGER DEFAULT 0,
                bot_lang TEXT DEFAULT 'uz',
                terms_accepted INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_jobs (
                job_key TEXT PRIMARY KEY,
                user_id INTEGER,
                file_id TEXT,
                lang TEXT DEFAULT 'uz',
                style TEXT DEFAULT 'mrbeast_style',
                color TEXT DEFAULT 'yellow',
                size TEXT DEFAULT 'normal'
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
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WordStyle,Komika Axis,{font_size},{text_color_hex},&H000000FF,&HFF000000,&H80000000,1,0,0,0,100,100,1,0,1,1.5,4.0,2,40,40,420,1

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
            if (end - start) < 0.25:
                end = start + 0.25
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
                    end_sec = start_sec + 0.25
            else:
                end_sec = w["end"]

            start_fmt = format_ass_time(start_sec)
            end_fmt = format_ass_time(end_sec)
            word_text = w["word"]
            duration_ms = int((end_sec - start_sec) * 1000)

            # 2-animatsiya: Silliq tracking va fade out effekti
            if anim_style == "mrbeast_style":
                pro_anim = f"{{\\an2\\fad(12,12)\\fscx120\\fscy120\\t(0,50,\\fscx100\\fscy100)\\b1}}"
            elif anim_style == "smooth_tracking":
                pro_anim = f"{{\\an2\\fad(150,180)\\fsp-3\\t(0,{duration_ms},\\fsp4)\\b1}}"
            elif anim_style == "active_bold_regular":
                pro_anim = f"{{\\an2\\fad(12,12)\\b1}}"
            elif anim_style == "active_word_box":
                pro_anim = f"{{\\an2\\fad(12,12)\\bord3\\3c&H000000&\\b1}}"
            else:
                pro_anim = f"{{\\an2\\fad(12,12)\\b1}}"

            f.write(f"Dialogue: 0,{start_fmt},{end_fmt},WordStyle,,0,0,0,,{pro_anim}{word_text}\n")
            count += 1

    return count


async def process_job(bot: Bot, chat_id: int, user_id: int, file_id: str, lang: str, anim_style: str, text_color: str, font_size_val: int, quality_res: str) -> None:
    job_key = uuid.uuid4().hex[:8]
    work_dir = WORK_ROOT / job_key
    work_dir.mkdir(parents=True, exist_ok=True)

    input_video = work_dir / "input.mp4"
    audio_path = work_dir / "audio.mp3"
    ass_path = work_dir / "subtitles.ass"
    output_video = work_dir / "output.mp4"

    status_msg = await bot.send_message(
        chat_id,
        "⚡ <b>Pro AI Subtitr tayyorlanmoqda...</b>\n\n"
        "▓░░░░░░░░░ 15%\n\n"
        "📥 <i>Video yuklab olinmoqda...</i>",
        parse_mode="HTML"
    )

    try:
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise Exception("Telegram video yo'lini bermadi.")

        await bot.download_file(file.file_path, destination=input_video)

        await status_msg.edit_text(
            "⚡ <b>Pro AI Subtitr tayyorlanmoqda...</b>\n\n"
            "▓▓▓░░░░░░░ 40%\n\n"
            "🎙 <i>Audio ajratib olinmoqda...</i>",
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
            "⚡ <b>Pro AI Subtitr tayyorlanmoqda...</b>\n\n"
            "▓▓▓▓▓▓░░░░ 70%\n\n"
            "✨ <i>ElevenLabs orqali ovoz matnga o'girilmoqda...</i>",
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

        try:
            transcription = await asyncio.wait_for(
                asyncio.to_thread(transcribe_audio), 
                timeout=180.0
            )
        except asyncio.TimeoutError:
            raise Exception("ElevenLabs javob berish vaqti tugadi (Timeout). Qaytadan urinib ko'ring.")

        words = getattr(transcription, "words", []) or []
        color_hex = TEXT_COLORS.get(text_color, TEXT_COLORS["yellow"])[1]
        count = generate_word_by_word_ass(words, ass_path, anim_style, color_hex, font_size_val)
        if count == 0:
            await status_msg.edit_text("❌ Videoda nutq aniqlanmadi.")
            return

        abs_fonts_dir = str(FONTS_DIR.resolve())
        vf_filter = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,ass=subtitles.ass:fontsdir='{abs_fonts_dir}'"

        cmd_render = [
            "ffmpeg", "-y", "-i", "input.mp4",
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "output.mp4"
        ]

        await status_msg.edit_text(
            "⚡ <b>Pro AI Subtitr tayyorlanmoqda...</b>\n\n"
            "▓▓▓▓▓▓▓▓░░ 85%\n\n"
            "🎬 <i>9:16 Instagram formatda video yozilmoqda...</i>",
            parse_mode="HTML"
        )

        proc_render = await asyncio.create_subprocess_exec(
            *cmd_render, cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc_render.communicate()

        if proc_render.returncode != 0:
            err_msg = stderr.decode(errors="ignore")[:300]
            raise Exception(f"FFmpeg xatosi: {err_msg}")

        deduct_user_credit(user_id)
        current_bal = get_user_credits(user_id)

        await status_msg.edit_text("📤 <b>Tayyor! Video yuklanmoqda...</b>", parse_mode="HTML")
        await bot.send_video(
            chat_id,
            video=FSInputFile(str(output_video)),
            caption=f"🔥 <b>Subtitr Tayyor!</b>\n\n💳 Qolgan balans: <b>{current_bal} ta video</b>",
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
    "1.1. Ushbu bot sun'iy intellekt orqali videolarga avtomatik dinamik subtitr qo'shib beradi.\n"
    "1.2. Videolar vertikal formatda va hajmi 50 MB gacha bo'lishi lozim.\n\n"
    "<b>2. TO'LOVLAR</b>\n"
    "2.1. Sotib olingan kreditlar qaytarilmaydi."
)


@router.message(Command("panel"))
async def cmd_admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_pro = 1")
        total_pro = cursor.fetchone()[0]

    panel_text = (
        "🛠 <b>ADMIN BOSHQARUV PANELI</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users} ta</b>\n"
        f"💎 PRO obunachilar: <b>{total_pro} ta</b>\n\n"
        "📌 <b>Buyruqlar:</b>\n"
        "• Balans qo'shish: <code>/add [user_id] [kredit_soni]</code>\n"
        "• PRO ulash: <code>/pro [user_id]</code>\n"
        "• PRO olish: <code>/unpro [user_id]</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Statistikani yangilash", callback_data="refresh_admin_panel")]
    ])
    await message.answer(panel_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "refresh_admin_panel")
async def refresh_admin_panel(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID:
        return

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_pro = 1")
        total_pro = cursor.fetchone()[0]

    panel_text = (
        "🛠 <b>ADMIN BOSHQARUV PANELI</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users} ta</b>\n"
        f"💎 PRO obunachilar: <b>{total_pro} ta</b>\n\n"
        "📌 <b>Buyruqlar:</b>\n"
        "• Balans qo'shish: <code>/add [user_id] [kredit_soni]</code>\n"
        "• PRO ulash: <code>/pro [user_id]</code>\n"
        "• PRO olish: <code>/unpro [user_id]</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Statistikani yangilash", callback_data="refresh_admin_panel")]
    ])
    try:
        await call.message.edit_text(panel_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.message(Command("pro"))
async def cmd_make_pro(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("⚠️ Xato format! Ishlatilishi:\n<code>/pro [user_id]</code>", parse_mode="HTML")
        return

    try:
        target_user_id = int(parts[1])
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target_user_id,))
            conn.commit()

        await message.reply(f"✅ ID: <code>{target_user_id}</code> foydalanuvchiga muvaffaqiyatli <b>PRO obuna</b> ulandi!", parse_mode="HTML")

        user_msg = (
            "🎉 <b>TABRIKLAYMIZ! SIZGA PRO TARIF BERILDI!</b> 🚀💎\n\n"
            "✨ Hurmatli foydalanuvchi, sizning hisobingiz ma'muriyat tomonidan <b>PRO TARIFGA</b> o'tkazildi!\n\n"
            "🌟 <b>Sizga ochilgan imkoniyatlar:</b>\n"
            "• 💎 <b>PRO 2K Ultra (1440p)</b> sifatli videolar chiqarish imkoniyati;\n"
            "• ⚡ Ustuvor (prioritet) va eng tezkor render navbati;\n"
            "• 🎬 Cheksiz professional Komika Axis dinamik subtitrlari.\n\n"
            "🚀 <i>Hozirdayoq videongizni yuboring va natijani sinab ko'ring!</i>"
        )
        await bot.send_message(target_user_id, user_msg, parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        await message.reply(f"❌ Xatolik yuz berdi: {e}")


@router.message(Command("unpro"))
async def cmd_remove_pro(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("⚠️ Xato format! Ishlatilishi:\n<code>/unpro [user_id]</code>", parse_mode="HTML")
        return

    try:
        target_user_id = int(parts[1])
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (target_user_id,))
            conn.commit()

        await message.reply(f"✅ ID: <code>{target_user_id}</code> foydalanuvchidan PRO obuna olib tashlandi.", parse_mode="HTML")
        await bot.send_message(target_user_id, "⚠️ Sizning PRO obunangiz muddati tugadi va tarifingiz Standart (Free) rejimiga o'tkazildi.", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("add"))
async def cmd_add_credits(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("⚠️ Format: <code>/add [user_id] [kredit_soni]</code>", parse_mode="HTML")
        return
    try:
        target_user_id = int(parts[1])
        amount = int(parts[2])
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, target_user_id))
            conn.commit()
        await message.reply(f"✅ ID <code>{target_user_id}</code> ga <b>{amount} ta</b> kredit qo'shildi!", parse_mode="HTML")
        await bot.send_message(target_user_id, f"🎉 Hisobingizga <b>+{amount} ta video</b> qo'shildi!", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Xato: {e}")


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    get_user_credits(user_id, message.from_user.username or "")
    
    await message.answer(
        f"✨ Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
        f"🎬 Menga videongizni yuboring va darhol professional subtitrga ega bo'ling!",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == "⚡ Auto Subtitr qo'yish")
async def cmd_auto_subtitr(message: Message):
    await message.answer("🎬 Menga <b>9:16 vertikal videongizni</b> yuboring:", parse_mode="HTML")


@router.message(F.text == "🎨 Subtitr uslublari")
async def cmd_subtitr_styles(message: Message):
    text = (
        "🎨 <b>SUBTITR USLUBLARI</b>\n\n"
        "• 🟢 <b>Komika Axis Pop-up:</b> MrBeast uslubidagi sakrab chiquvchi qalin shrift.\n"
        "• ✨ <b>Smooth Text Tracking:</b> Harflarning silliq kengayish va fade effekti.\n"
        "• 🔥 <b>Active Bold / Regular:</b> So'zlarning qalinlashib boruvchi dinamik ko'rinishi.\n"
        "• ⬛ <b>Active Word Highlight:</b> So'z orqasida qora fonli blok.\n\n"
        "<i>Videongizni yuboring va istalgan uslubni tanlang!</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💎 PRO Tariflar")
async def cmd_pro_tariffs(message: Message):
    user_id = message.from_user.id
    text = (
        "💎 <b>PRO TARIFLAR VA IMKONIYATLAR</b>\n\n"
        "• 📱 <b>Standard HD (720p)</b> — Barcha foydalanuvchilar uchun.\n"
        "• 💎 <b>PRO 2K Ultra (1440p)</b> — Faqat PRO obunachilar uchun maxsus kristalli tiniq sifat.\n\n"
        "💳 <b>Kredit paketlari narxlari:</b>\n"
        "• 10 ta video — 45,000 so'm\n"
        "• 25 ta video — 95,000 so'm\n"
        "• 50 ta video — 175,000 so'm\n\n"
        f"💳 Karta: <code>{CARD_NUMBER}</code>\n"
        f"👤 Egasi: <b>{CARD_HOLDER}</b>\n\n"
        "📸 To'lov qilgach, chekni adminga yuboring!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 PRO sotib olish uchun adminga yozish", url=f"https://t.me/{ADMIN_USERNAME}?text=Salom,%20men%20PRO%20tarif%20sotib%20olmoqchiman.%20ID%20raqamim:%20{user_id}")],
        [InlineKeyboardButton(text="👨‍💻 Adminga chek yuborish", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text == "📜 Oferta")
async def show_oferta(message: Message):
    await message.answer(OFERTA_FULL_TEXT, parse_mode="HTML")


@router.message(F.text == "💳 Balans")
async def cmd_balans(message: Message):
    user_id = message.from_user.id
    credits = get_user_credits(user_id)
    is_pro = is_user_pro(user_id)
    status_text = "💎 <b>PRO Obuna:</b> Faol ✅" if is_pro else "👤 <b>Status:</b> Free (Standart)"
    
    text = (
        "💎 <b>SHAXSIY BALANS</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🔋 Qolgan urinishlar: <b>{credits} ta video</b>\n"
        f"{status_text}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 PRO sotib olish", url=f"https://t.me/{ADMIN_USERNAME}?text=Salom,%20men%20PRO%20tarif%20sotib%20olmoqchiman.%20ID%20raqamim:%20{user_id}")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text == "💰 To'lov qilish")
async def cmd_payment(message: Message):
    user_id = message.from_user.id
    payment_text = (
        "💳 <b>TARIFLAR VA TO'LOV:</b>\n\n"
        "• 10 ta video — 45,000 so'm\n"
        "• 25 ta video — 95,000 so'm\n"
        "• 50 ta video — 175,000 so'm\n\n"
        f"💳 Karta: <code>{CARD_NUMBER}</code>\n"
        f"👤 Egasi: <b>{CARD_HOLDER}</b>\n\n"
        "📸 To'lov qilgach, chekni va ID raqamingizni adminga yuboring!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 PRO sotib olish uchun yozish", url=f"https://t.me/{ADMIN_USERNAME}?text=Salom,%20men%20PRO%20tarif%20sotib%20olmoqchiman.%20ID%20raqamim:%20{user_id}")],
        [InlineKeyboardButton(text="📤 Chekni adminga yuborish", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    await message.answer(payment_text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def cmd_contact_admin(message: Message):
    await message.answer(f"👨‍💻 Admin: @{ADMIN_USERNAME}\n📞 Tel: {ADMIN_PHONE}", parse_mode="HTML")


@router.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def on_video(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    
    if credits <= 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 PRO sotib olish", url=f"https://t.me/{ADMIN_USERNAME}?text=Salom,%20men%20PRO%20tarif%20sotib%20olmoqchiman.%20ID%20raqamim:%20{user_id}")]
        ])
        await message.reply("❌ Balansingiz tugagan. Davom etish uchun tarifni to'ldiring:", reply_markup=kb, parse_mode="HTML")
        return

    media = message.video or message.document
    if (media.file_size or 0) > MAX_VIDEO_BYTES:
        await message.answer("❌ Video hajmi 50 MB dan oshmasligi kerak.")
        return

    key = uuid.uuid4().hex[:8]
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_jobs (job_key, user_id, file_id) VALUES (?, ?, ?)",
            (key, user_id, media.file_id)
        )
        conn.commit()

    kb = InlineKeyboardBuilder()
    for code, title in VIDEO_LANGS.items():
        kb.button(text=title, callback_data=f"lang:{key}:{code}")
    kb.adjust(2)
    await message.reply("1️⃣ <b>Videodagi nutq tilini tanlang:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("lang:"))
async def on_select_lang(call: CallbackQuery) -> None:
    await call.answer()
    parts = call.data.split(":")
    if len(parts) < 3:
        return
    _, key, code = parts
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id FROM user_jobs WHERE job_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            await call.message.answer("⚠️ Sessiya eskirgan. Iltimos, videoni qaytadan yuboring.")
            return
        cursor.execute("UPDATE user_jobs SET lang = ? WHERE job_key = ?", (code, key))
        conn.commit()

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    kb = InlineKeyboardBuilder()
    for skey, title in ANIMATION_STYLES.items():
        kb.button(text=title, callback_data=f"anim:{key}:{skey}")
    kb.adjust(1)

    await call.message.answer("2️⃣ <b>Subtitr animatsiya uslubini tanlang:</b>\n<i>(Shrift: Komika Axis)</i>", reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("anim:"))
async def on_select_anim(call: CallbackQuery) -> None:
    await call.answer()
    parts = call.data.split(":")
    if len(parts) < 3:
        return
    _, key, skey = parts
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id FROM user_jobs WHERE job_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            await call.message.answer("⚠️ Sessiya eskirgan. Iltimos, videoni qaytadan yuboring.")
            return
        cursor.execute("UPDATE user_jobs SET style = ? WHERE job_key = ?", (skey, key))
        conn.commit()

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    kb = InlineKeyboardBuilder()
    for ckey, (ctitle, _) in TEXT_COLORS.items():
        kb.button(text=ctitle, callback_data=f"color:{key}:{ckey}")
    kb.adjust(2)

    await call.message.answer("🎨 <b>Subtitr matn rangini tanlang:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("color:"))
async def on_select_color(call: CallbackQuery) -> None:
    await call.answer()
    parts = call.data.split(":")
    if len(parts) < 3:
        return
    _, key, ckey = parts
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id FROM user_jobs WHERE job_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            await call.message.answer("⚠️ Sessiya eskirgan. Iltimos, videoni qaytadan yuboring.")
            return
        cursor.execute("UPDATE user_jobs SET color = ? WHERE job_key = ?", (ckey, key))
        conn.commit()

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    kb = InlineKeyboardBuilder()
    for fkey, (ftitle, _) in FONT_SIZES.items():
        kb.button(text=ftitle, callback_data=f"size:{key}:{fkey}")
    kb.adjust(2)

    await call.message.answer("📏 <b>Subtitr matn o'lchamini tanlang:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("size:"))
async def on_select_size(call: CallbackQuery) -> None:
    await call.answer()
    parts = call.data.split(":")
    if len(parts) < 3:
        return
    _, key, fkey = parts
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id FROM user_jobs WHERE job_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            await call.message.answer("⚠️ Sessiya eskirgan. Iltimos, videoni qaytadan yuboring.")
            return
        cursor.execute("UPDATE user_jobs SET size = ? WHERE job_key = ?", (fkey, key))
        conn.commit()

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    kb = InlineKeyboardBuilder()
    for qkey, (title, _, _) in VIDEO_QUALITIES.items():
        kb.button(text=title, callback_data=f"qual:{key}:{qkey}")
    kb.adjust(1)

    await call.message.answer("3️⃣ <b>Video sifatini tanlang:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("qual:"))
async def on_select_quality(call: CallbackQuery, bot: Bot) -> None:
    await call.answer()
    parts = call.data.split(":")
    if len(parts) < 3:
        return
    _, key, qkey = parts
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, lang, style, color, size FROM user_jobs WHERE job_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            await call.message.answer("⚠️ Sessiya eskirgan yoki video allaqachon ishlatilgan. Iltimos, videoni qaytadan yuboring.")
            return
        file_id, lang, anim_style, text_color, font_key = row
        # Ma'lumotni darhol o'chirmaymiz, xatolik chiqsa qayta ishlatish uchun qoldiramiz yoki jarayon oxirida tozalaymiz

    chat_id = call.message.chat.id
    user_id = call.from_user.id
    font_size_val = FONT_SIZES.get(font_key, FONT_SIZES["normal"])[1]

    q_info = VIDEO_QUALITIES.get(qkey)
    if not q_info:
        return

    quality_title, quality_res, is_pro_required = q_info

    if is_pro_required and not is_user_pro(user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 PRO sotib olish uchun adminga yozish", url=f"https://t.me/{ADMIN_USERNAME}?text=Salom,%20men%20PRO%20tarif%20sotib%20olmoqchiman.%20ID%20raqamim:%20{user_id}")],
            [InlineKeyboardButton(text="📱 Standard HD (720p) bilan davom etish", callback_data=f"qual:{key}:720p")]
        ])
        await call.message.answer(
            "💎 <b>Bu imkoniyat faqat PRO obunachilar uchun!</b>\n\n"
            "Siz Standard (Free) tarifdasiz. <b>PRO 2K Ultra</b> sifatidan foydalanish uchun hisobingizni PRO tarifga o'tkazing yoki 720p sifatini tanlang.",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    # Ishga tushgach bazadan o'chiramiz
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_jobs WHERE job_key = ?", (key,))
        conn.commit()

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    asyncio.create_task(process_job(bot, chat_id, user_id, file_id, lang, anim_style, text_color, font_size_val, quality_res))


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
            await asyncio.sleep(5)
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
