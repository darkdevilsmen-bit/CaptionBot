import os
import sys
import time
import uuid
import json
import shutil
import sqlite3
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple

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
BOT_TOKEN = "8933394511:AAH4jiabi75UgDni40C2rfge8-4uDv7kzwE"
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

FONT_SIZES = {
    "small": ("🔽 Kichik (70)", 70),
    "normal": ("📱 Normal (85)", 85),
    "large": ("📈 Katta (100)", 100),
    "xlarge": ("🔥 Juda katta (115)", 115)
}

router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# Sessiyalar xotirada barqaror saqlanadi
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


def get_video_metadata(video_path: Path, fallback_w: int = 1080, fallback_h: int = 1920, fallback_dur: int = 0) -> Tuple[int, int, int]:
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "json",
            str(video_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            stream = data.get("streams", [{}])[0]
            w = int(stream.get("width", fallback_w))
            h = int(stream.get("height", fallback_h))
            d_val = stream.get("duration")
            d = int(float(d_val)) if d_val else fallback_dur
            return w, h, d
    except Exception:
        pass

    try:
        cmd = [FFMPEG_PATH, "-i", str(video_path)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        for line in res.stderr.splitlines():
            if "Video:" in line:
                for token in line.split(','):
                    token = token.strip()
                    if 'x' in token:
                        sub = token.split()[0]
                        parts = sub.split('x')
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            return int(parts[0]), int(parts[1]), fallback_dur
    except Exception:
        pass

    return fallback_w, fallback_h, fallback_dur


def generate_word_by_word_ass(words: List[Any], ass_path: Path, anim_style: str, font_size: int, video_w: int, video_h: int) -> int:
    """
    Haqiqiy karaoke/animatsiya:
    Kadrda bir vaqtda 3-4 ta so'z ko'rinadi va gapirilayotgan so'z o'sha soniyada
    ajralib (sakrab / sariq bo'lib / neon bo'lib) turadi.
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,20,20,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    clean_words = []
    for w in words:
        txt = getattr(w, 'word', None)
        if txt is None and isinstance(w, dict):
            txt = w.get('word', '')
        if txt is None:
            txt = str(w)
        txt = txt.strip()
        if not txt:
            continue
        
        st = getattr(w, 'start', None)
        if st is None and isinstance(w, dict):
            st = w.get('start', 0.0)
        st = float(st or 0.0)
        
        et = getattr(w, 'end', None)
        if et is None and isinstance(w, dict):
            et = w.get('end', st + 0.4)
        et = float(et or (st + 0.4))
        
        clean_words.append({"word": txt, "start": st, "end": et})

    if not clean_words:
        return 0

    dialogues = []
    chunk_size = 4
    for i in range(0, len(clean_words), chunk_size):
        chunk = clean_words[i:i + chunk_size]
        if not chunk:
            continue

        # Har bir so'z gapirilayotgan alohida vaqt oralig'i uchun kadr chizamiz
        for active_idx, target_word in enumerate(chunk):
            w_start = target_word["start"]
            w_end = target_word["end"]
            
            line_parts = []
            for j, item in enumerate(chunk):
                word_text = item["word"]
                if j == active_idx:
                    # Aktiv aytilayotgan so'zning animatsiyasi
                    if anim_style == "mrbeast_style":
                        # Sakrash va sariq rang
                        formatted = f"{{\\c&H0000FFFF&\\t(0,80,\\fscx125\\fscy125)\\t(80,160,\\fscx100\\fscy100)}}{word_text}"
                    elif anim_style == "smooth_tracking":
                        # Neon yashil va porlash
                        formatted = f"{{\\c&H0000FF00&\\bord5\\shad0}}{word_text}"
                    elif anim_style == "active_bold_regular":
                        # Qizil/olov rang va qalin
                        formatted = f"{{\\b1\\c&H000080FF&}}{word_text}{{\\b0}}"
                    elif anim_style == "active_word_box":
                        # Oq fon (box) bilan qora matn
                        formatted = f"{{\\c&H00000000&\\4c&H0000FFFF&\\bord4}}{word_text}"
                    else:
                        formatted = f"{{\\c&H0000FFFF&}}{word_text}"
                else:
                    # Hali aytilmagan yoki aytib bo'lingan oddiy oq so'z
                    formatted = f"{{\\c&H00FFFFFF&}}{word_text}"
                
                line_parts.append(formatted)

            text_content = " ".join(line_parts)
            dialogues.append(f"Dialogue: 0,{format_ass_time(w_start)},{format_ass_time(w_end)},Default,,0,0,0,,{text_content}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(dialogues) + "\n")
    return len(dialogues)


async def burn_subtitles_to_video(input_video: Path, ass_path: Path, output_video: Path):
    clean_ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
    vf_filter = f"subtitles='{clean_ass}',scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
    
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(input_video),
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "24",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
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

    # Oldingi sessiya bo'lsa tozalash
    if user_id in USER_SESSIONS:
        old_dir = Path(USER_SESSIONS[user_id].get("dir_path", ""))
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)

    user_dir = WORK_ROOT / f"user_{user_id}_{int(time.time())}"
    user_dir.mkdir(parents=True, exist_ok=True)
    input_video = user_dir / "input.mp4"
    
    status_dl = await message.reply("⏳ Video yuklab olinmoqda...")
    file_info = await bot.get_file(message.video.file_id)
    await bot.download_file(file_info.file_path, destination=input_video)
    
    init_w = message.video.width or 1080
    init_h = message.video.height or 1920
    init_dur = message.video.duration or 0

    USER_SESSIONS[user_id] = {
        "video_path": str(input_video),
        "dir_path": str(user_dir),
        "anim_style": "mrbeast_style",
        "font_size": 85,
        "raw_w": init_w,
        "raw_h": init_h,
        "raw_dur": init_dur,
        "processing": False
    }
    
    builder = InlineKeyboardBuilder()
    for key, name in ANIMATION_STYLES.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"anim_{key}"))
        
    await status_dl.delete()
    await message.answer(
        "✨ Videongiz qabul qilindi!\n\nSubtitr uchun **animatsiya uslubini** tanlang:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("anim_"))
async def callback_anim_style(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    if user_id not in USER_SESSIONS:
        await callback.message.answer("Sessiya topilmadi. Iltimos videoni qaytadan yuboring.")
        return
        
    style_key = callback.data.replace("anim_", "")
    USER_SESSIONS[user_id]["anim_style"] = style_key
    
    builder = InlineKeyboardBuilder()
    for key, (name, val) in FONT_SIZES.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"size_{key}"))
        
    try:
        await callback.message.edit_text(
            "📱 Endi subtitr **shrift o'lchamini** tanlang:",
            reply_markup=builder.as_markup()
        )
    except Exception:
        await callback.message.answer(
            "📱 Endi subtitr **shrift o'lchamini** tanlang:",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data.startswith("size_"))
async def callback_font_size(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    user_id = callback.from_user.id
    if user_id not in USER_SESSIONS:
        await callback.message.answer("Sessiya eskirgan. Iltimos videoni qaytadan yuboring.")
        return
        
    session = USER_SESSIONS[user_id]
    if session.get("processing"):
        return
    session["processing"] = True

    size_key = callback.data.replace("size_", "")
    session["font_size"] = FONT_SIZES.get(size_key, ("Normal", 85))[1]
    
    input_video = Path(session["video_path"])
    user_dir = Path(session["dir_path"])
    output_video = user_dir / "output.mp4"
    ass_path = user_dir / "subs.ass"
    
    status_msg = await callback.message.edit_text("✨ Subtitrlar tayyorlanmoqda, iltimos kuting...")
    
    try:
        v_width, v_height, v_dur = get_video_metadata(
            input_video,
            session.get("raw_w", 1080),
            session.get("raw_h", 1920),
            session.get("raw_dur", 0)
        )

        with open(input_video, "rb") as audio_file:
            transcript = el_client.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v1",
                tag_audio_events=False
            )
        
        words = getattr(transcript, "words", [])
        if not words and isinstance(transcript, dict):
            words = transcript.get("words", [])
            
        if not words:
            await status_msg.edit_text("❌ Videodan ovoz topilmadi yoki matnga o'girib bo'lmadi.")
            shutil.rmtree(user_dir, ignore_errors=True)
            USER_SESSIONS.pop(user_id, None)
            return
            
        generate_word_by_word_ass(
            words=words,
            ass_path=ass_path,
            anim_style=session["anim_style"],
            font_size=session["font_size"],
            video_w=v_width,
            video_h=v_height
        )
        
        await burn_subtitles_to_video(input_video, ass_path, output_video)
        
        if not is_user_pro(user_id):
            deduct_user_credit(user_id)
            
        remaining_credits = get_user_credits(user_id)
        
        await bot.send_video(
            chat_id=user_id,
            video=FSInputFile(output_video),
            width=v_width,
            height=v_height,
            duration=v_dur,
            supports_streaming=True,
            caption=f"🔥 Subtitr Tayyor!\n\n💳 Qolgan balans: {remaining_credits} ta video",
            reply_markup=get_main_keyboard()
        )
        await status_msg.delete()
        
    except Exception as e:
        log.error(f"Video qayta ishlashda xatolik: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")
    finally:
        shutil.rmtree(user_dir, ignore_errors=True)
        USER_SESSIONS.pop(user_id, None)


@router.message(F.text == "🎨 Subtitr uslublari")
async def cmd_sub_styles(message: Message):
    styles_text = (
        "Subtitr uslublarini tanlash:\n\n"
        "Hozirda quyidagi animatsiya uslublari mavjud:\n"
        "1. 🟢 Komika Axis Pop-up (MrBeast uslubi - har bir so'z aytilganda sakraydi)\n"
        "2. ✨ Smooth Text Tracking (Neon porlash bilan)\n"
        "3. 🔥 Active Bold / Regular (Aytilayotgan so'z qalinlashadi)\n"
        "4. ⬛ Active Word Highlight (Aktiv so'z sariq qutida ajraladi)\n\n"
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
