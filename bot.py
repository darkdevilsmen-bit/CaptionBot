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
    "uz": "🇺🇿 O'zbekcha",
    "ru": "🇷🇺 Ruscha",
    "en": "🇬🇧 Inglizcha",
}

ANIMATION_STYLES = {
    "mrbeast_style": "🟢 Komika Axis Pop-up (MrBeast)",
    "smooth_tracking": "✨ Smooth Text Tracking",
    "active_bold_regular": "🔥 Active Bold / Regular",
    "active_word_box": "⬛ Active Word Highlight (Box)"
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


def format_ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{mins:02d}:{secs:02d}.{centis:02d}"


def generate_word_by_word_ass(words: List[Any], ass_path: Path, anim_style: str) -> int:
    color_hex = "&H0000FFFF"  # Sariq rang
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
Style: WordStyle,Arial,85,{color_hex},&H000000FF,&HFF000000,&H80000000,1,0,0,0,100,100,2,0,1,6.0,2.0,2,40,40,450,1

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
            if (end - start) < 0.3:
                end = start + 0.3
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
                    end_sec = start_sec + 0.3
            else:
                end_sec = w["end"]

            start_fmt = format_ass_time(start_sec)
            end_fmt = format_ass_time(end_sec)
            word_text = w["word"]
            duration_ms = int((end_sec - start_sec) * 1000)

            if anim_style == "mrbeast_style":
                pro_anim = f"{{\\an2{font_tag}\\fad(30,50)\\fscx140\\fscy140\\t(0,70,\\fscx100\\fscy100)\\b1}}"
            elif anim_style == "smooth_tracking":
                pro_anim = f"{{\\an2{font_tag}\\fad(30,50)\\fsp-8\\t(0,{duration_ms},\\fsp14)\\b1}}"
            elif anim_style == "active_bold_regular":
                pro_anim = f"{{\\an2{font_tag}\\fad(30,50)\\b1}}"
            elif anim_style == "active_word_box":
                pro_anim = f"{{\\an2{font_tag}\\fad(30,50)\\bord8\\3c&H000000&\\b1}}"
            else:
                pro_anim = f"{{\\an2{font_tag}\\fad(30,50)\\b1}}"

            f.write(f"Dialogue: 0,{start_fmt},{end_fmt},WordStyle,,0,0,0,,{pro_anim}{word_text}\n")
            count += 1

    return count


async def process_job(bot: Bot, chat_id: int, user_id: int, file_id: str, lang: str, anim_style: str) -> None:
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
        count = generate_word_by_word_ass(words, ass_path, anim_style)
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

        await status_msg.edit_text(
            "⚡ <b>Pro AI Subtitr tayyorlanmoqda...</b>\n\n"
            "▓▓▓▓▓▓▓▓░░ 85%\n\n"
            "🎬 <i>Komika Axis subtitr videoga yozilmoqda...</i>",
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

    panel_text = f"🛠 <b>ADMIN PANEL</b>\n\n👥 Jami foydalanuvchilar: <b>{total_users} ta</b>\n\nBuyruq: <code>/add [user_id] [soni]</code>"
    await message.answer(panel_text, parse_mode="HTML")


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
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
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
        "• ✨ <b>Smooth Text Tracking:</b> Harflarning silliq kengayish effekti.\n"
        "• 🔥 <b>Active Bold / Regular:</b> So'zlarning qalinlashib boruvchi dinamik ko'rinishi.\n"
        "• ⬛ <b>Active Word Highlight:</b> So'z orqasida qora fonli blok.\n\n"
        "<i>Videongizni yuboring va istalgan uslubni tanlang!</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📜 Oferta")
async def show_oferta(message: Message):
    await message.answer(OFERTA_FULL_TEXT, parse_mode="HTML")


@router.message(F.text == "💳 Balans")
async def cmd_balans(message: Message):
    credits = get_user_credits(message.from_user.id)
    text = (
        "💎 <b>SHAXSIY BALANS</b>\n\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"🔋 Qolgan urinishlar: <b>{credits} ta video</b>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Tariflarni ko'rish va to'ldirish", callback_data="show_tariffs")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


def get_tariffs_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 10 ta video — 45,000 so'm", callback_data="buy_10")],
        [InlineKeyboardButton(text="💎 25 ta video — 95,000 so'm", callback_data="buy_25")],
        [InlineKeyboardButton(text="💎 50 ta video — 175,000 so'm", callback_data="buy_50")],
        [InlineKeyboardButton(text="👨‍💻 Adminga chek yuborish", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])


@router.callback_query(F.data == "show_tariffs")
async def on_show_tariffs(call: CallbackQuery):
    await call.answer()
    payment_text = (
        "💳 <b>TARIFLAR:</b>\n\n"
        "• 10 ta video — 45,000 so'm\n"
        "• 25 ta video — 95,000 so'm\n"
        "• 50 ta video — 175,000 so'm\n\n"
        f"💳 Karta: <code>{CARD_NUMBER}</code>\n"
        f"👤 Egasi: <b>{CARD_HOLDER}</b>\n\n"
        "📸 To'lov qilgach, chekni adminga yuboring!"
    )
    await call.message.answer(payment_text, reply_markup=get_tariffs_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.in_({"buy_10", "buy_25", "buy_50"}))
async def on_buy_package(call: CallbackQuery):
    await call.answer()
    text = (
        f"💳 <b>Karta:</b> <code>{CARD_NUMBER}</code>\n"
        f"👤 <b>Egasi:</b> {CARD_HOLDER}\n\n"
        f"To'lovni amalga oshirib, chekni quyidagi adminga yuboring:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Chekni yuborish", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    await call.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text == "💰 To'lov qilish")
async def cmd_payment(message: Message):
    payment_text = (
        "💳 <b>TARIFLAR:</b>\n\n"
        "• 10 ta video — 45,000 so'm\n"
        "• 25 ta video — 95,000 so'm\n"
        "• 50 ta video — 175,000 so'm\n\n"
        f"💳 Karta: <code>{CARD_NUMBER}</code>\n"
        f"👤 Egasi: <b>{CARD_HOLDER}</b>\n\n"
        "📸 To'lov qilgach, chekni adminga yuboring!"
    )
    await message.answer(payment_text, reply_markup=get_tariffs_keyboard(), parse_mode="HTML")


@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def cmd_contact_admin(message: Message):
    await message.answer(f"👨‍💻 Admin: @{ADMIN_USERNAME}\n📞 Tel: {ADMIN_PHONE}", parse_mode="HTML")


@router.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def on_video(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    
    if credits <= 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Tariflarni ko'rish", callback_data="show_tariffs")]
        ])
        await message.reply("❌ Balansingiz tugagan. Davom etish uchun to'ldiring:", reply_markup=kb, parse_mode="HTML")
        return

    media = message.video or message.document
    if (media.file_size or 0) > MAX_VIDEO_BYTES:
        await message.answer("❌ Video hajmi 50 MB dan oshmasligi kerak.")
        return

    key = uuid.uuid4().hex[:8]
    jobs[key] = {
        "file_id": media.file_id,
        "chat_id": message.chat.id,
        "user_id": user_id
    }

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
    
    job = jobs.get(key)
    if not job:
        await call.message.answer("⚠️ So'rov muddati o'tgan. Iltimos, videoni qaytadan yuboring.")
        return

    job["lang"] = code

    kb = InlineKeyboardBuilder()
    for skey, title in ANIMATION_STYLES.items():
        kb.button(text=title, callback_data=f"anim:{key}:{skey}")
    kb.adjust(1)

    try:
        await call.message.edit_text("2️⃣ <b>Subtitr animatsiya uslubini tanlang:</b>\n<i>(Shrift: Komika Axis)</i>", reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await call.message.answer("2️⃣ <b>Subtitr animatsiya uslubini tanlang:</b>\n<i>(Shrift: Komika Axis)</i>", reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("anim:"))
async def on_select_anim(call: CallbackQuery, bot: Bot) -> None:
    await call.answer("Qabul qilindi! Ish boshlandi...")
    parts = call.data.split(":")
    if len(parts) < 3:
        return
    _, key, skey = parts
    
    job = jobs.pop(key, None)
    if not job:
        await call.message.answer("⚠️ Ma'lumot topilmadi. Iltimos, videoni qaytadan yuboring.")
        return

    file_id = job["file_id"]
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    lang = job.get("lang", "uz")
    
    try:
        await call.message.edit_text("✅ <b>Qabul qilindi! Komika Axis shriftida video tayyorlanmoqda...</b>", parse_mode="HTML")
    except Exception:
        pass

    asyncio.create_task(process_job(bot, chat_id, user_id, file_id, lang, skey))


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
