import os
import uuid
import shutil
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
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from elevenlabs.client import ElevenLabs

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# --- SOZLAMALAR ---
BOT_TOKEN = "8933394511:AAGS2vZzoGop39HMYQTzn5HppFLeqvs-LEg"
ELEVENLABS_API_KEY = "sk_2645eb8c6ab7457d5661f30bc9935e8107560bec586b14c8"
ADMIN_ID = 7662888182
ADMIN_USERNAME = "Captions_Admin"

WORK_ROOT = Path("temp_processing")
FONTS_DIR = Path(".")
DB_FILE = Path("database.db")

router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

class CaptionStates(StatesGroup):
    waiting_for_video = State()

def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="⚡ Video Yuborish & Subtitr")],
        [KeyboardButton(text="💎 PRO Tarif"), KeyboardButton(text="💳 Balans & To'lov")],
        [KeyboardButton(text="📜 Oferta"), KeyboardButton(text="👨‍💻 Admin bilan bog'lanish")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_styles_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🟢 Komika Axis Pop-up (MrBeast)", callback_data="style_mrbeast")],
        [InlineKeyboardButton(text="✨ Smooth Text Tracking", callback_data="style_smooth")],
        [InlineKeyboardButton(text="🔥 Active Bold / Regular", callback_data="style_bold")],
        [InlineKeyboardButton(text="⬛ Active Word Highlight (Box)", callback_data="style_box")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 3,
                is_pro INTEGER DEFAULT 0,
                terms_accepted INTEGER DEFAULT 0
            )
        """)
        conn.commit()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, credits) VALUES (?, ?, 3)", (user_id, message.from_user.username or ""))
        conn.commit()

    await message.answer(
        f"✨ Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
        f"🚀 **Komika Axis** shrifti va professional animatsiyali subtitrlar yaratish uchun quyidagi tugmani bosing:",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@router.message(F.text == "⚡ Video Yuborish & Subtitr")
async def ask_for_video(message: Message, state: FSMContext):
    await state.set_state(CaptionStates.waiting_for_video)
    await message.answer("📥 Iltimos, subtitr qo'shilishi kerak bo'lgan **9:16 formatdagi videoni** yuboring:")

@router.message(F.text == "💎 PRO Tarif")
async def cmd_pro(message: Message):
    await message.answer("💎 **1 oylik PRO Tarif:** Cheksiz 2K videolar, prioritet navbat va Komika Axis shrifti — 75,000 so'm.\n\n💳 Karta: `5614 6865 0542 8600` (Toshpulatov Shoxrux)\n👨‍💻 Admin: @Captions_Admin", parse_mode="HTML")

@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def cmd_admin(message: Message):
    await message.answer(f"👨‍‍💻 Admin: @{ADMIN_USERNAME}", parse_mode="HTML")

@router.message(CaptionStates.waiting_for_video, F.video)
async def process_incoming_video(message: Message, state: FSMContext):
    file_id = message.video.file_id
    file_info = await message.bot.get_file(file_id)
    
    job_key = uuid.uuid4().hex[:8]
    work_dir = WORK_ROOT / job_key
    work_dir.mkdir(parents=True, exist_ok=True)
    
    input_video = work_dir / "input.mp4"
    await message.bot.download_file(file_info.file_path, destination=input_video)

    await state.update_data(input_video=str(input_video), job_key=job_key)
    await state.set_state(None)

    await message.answer("🎨 Subtitr animatsiya uslubini tanlang:", reply_markup=get_styles_keyboard())

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

def generate_word_by_word_ass(words: List[Any], ass_path: Path, anim_style: str) -> int:
    color_hex = rgb_to_ass((255, 255, 0)) # Sariq rang
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WordStyle,Komika Axis,85,{color_hex},&H000000FF,&HFF000000,&H80000000,0,0,0,0,100,100,2,0,1,6.0,2.0,2,40,40,450,1

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

            if anim_style == "style_mrbeast":
                pro_anim = "{\\an2\\fad(40,80)\\fscx120\\fscy120\\t(0,60,\\fscx100\\fscy100)\\b0}"
            elif anim_style == "style_smooth":
                pro_anim = "{\\an2\\fad(150,150)\\b0}"
            elif anim_style == "style_bold":
                pro_anim = "{\\an2\\fad(40,80)\\b1}"
            else: # Box style
                pro_anim = "{\\an2\\fad(40,80)\\bord8\\3c&H000000&\\b0}"

            f.write(f"Dialogue: 0,{start_fmt},{end_fmt},WordStyle,,0,0,0,,{pro_anim}{word_text}\n")
            count += 1

    return count

@router.callback_query(F.data.startswith("style_"))
async def handle_style_selection(callback: CallbackQuery, state: FSMContext):
    anim_style = callback.data
    data = await state.get_data()
    input_video_str = data.get("input_video")
    job_key = data.get("job_key")

    if not input_video_str:
        await callback.message.answer("⚠️ Xatolik: Video topilmadi. Qaytadan video yuboring.")
        await callback.answer()
        return

    await callback.message.edit_text("⏳ **Video tayyorlanmoqda...** Iltimos, biroz kuting.")
    
    asyncio.create_task(process_video_background(callback.message, input_video_str, anim_style, job_key))
    await callback.answer()

async def process_video_background(message: Message, input_video_str: str, anim_style: str, job_key: str):
    work_dir = WORK_ROOT / job_key
    try:
        input_video = Path(input_video_str)
        audio_path = work_dir / "audio.mp3"
        ass_path = work_dir / "subtitles.ass"
        output_video = work_dir / "output.mp4"

        cmd_extract = ["ffmpeg", "-y", "-i", str(input_video), "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", "-b:a", "48k", str(audio_path)]
        proc = await asyncio.create_subprocess_exec(*cmd_extract)
        await proc.communicate()

        def transcribe():
            with open(audio_path, "rb") as af:
                return el_client.speech_to_text.convert(file=("audio.mp3", af.read(), "audio/mpeg"), model_id="scribe_v1", language_code="uz")

        transcription = await asyncio.to_thread(transcribe)
        words = getattr(transcription, "words", []) or []

        generate_word_by_word_ass(words, ass_path, anim_style)

        abs_fonts_dir = str(FONTS_DIR.resolve())
        cmd_render = [
            "ffmpeg", "-y", "-threads", "4", "-i", str(input_video),
            "-vf", f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,ass={str(ass_path)}:fontsdir='{abs_fonts_dir}'",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "copy", str(output_video)
        ]
        proc_render = await asyncio.create_subprocess_exec(*cmd_render)
        await proc_render.communicate()

        await message.bot.send_video(message.chat.id, video=FSInputFile(str(output_video)), caption="🔥 **Subtitr tayyor! (Komika Axis shrifti bilan)**", parse_mode="MARKDOWN")

    except Exception as e:
        log.error(f"Render xatosi: {e}")
        await message.bot.send_message(message.chat.id, f"❌ Xatolik yuz berdi: {e}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

async def main():
    init_db()
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    
    session = AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot klassik rejimda ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
