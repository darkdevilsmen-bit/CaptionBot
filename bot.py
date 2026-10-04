import os
import sys
import time
import json
import shutil
import sqlite3
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple

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

WORK_ROOT = Path("temp_processing")
DB_FILE = Path("database.db")
INITIAL_CREDITS = 1

# 4 TA ASL ANIMATSIYA USLUBLARI (O'ZGARISHLARSIZ)
ANIMATION_STYLES = {
    "mrbeast_style": "🟢 Komika Axis Pop-up (MrBeast)",
    "smooth_tracking": "✨ Smooth Text Tracking (Fade)",
    "active_bold_regular": "🔥 Active Bold / Regular",
    "active_word_box": "⬛ Active Word Highlight (Box)"
}

FONT_SIZES = {
    "small": ("🔽 Kichik", 45),
    "normal": ("📱 Normal", 60),
    "large": ("📈 Katta", 75),
    "xlarge": ("🔥 Juda katta", 90)
}

router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()


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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_tasks (
                task_id TEXT PRIMARY KEY,
                user_id INTEGER,
                file_id TEXT,
                video_w INTEGER,
                video_h INTEGER,
                duration INTEGER,
                anim_style TEXT,
                font_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        log.error(f"Obuna tekshirish xatosi: {e}")
    return False


def format_ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{mins:02d}:{secs:02d}.{centis:02d}"


def get_exact_video_dimensions(video_path: Path) -> Tuple[int, int, int]:
    """Videoni kesmasdan (crop qilmasdan) aniq eni va bo'yini oladi"""
    try:
        cmd = [
            FFMPEG_PATH,
            "-i", str(video_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        for line in res.stderr.splitlines():
            if "Video:" in line:
                for chunk in line.split(","):
                    chunk = chunk.strip()
                    if "x" in chunk:
                        cand = chunk.split()[0]
                        parts = cand.split("x")
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            return int(parts[0]), int(parts[1]), 0
    except Exception as e:
        log.error(f"O'lcham olishda xatolik: {e}")
    return 1080, 1920, 0


def generate_word_by_word_ass(words: List[Any], ass_path: Path, anim_style: str, font_size: int, video_w: int, video_h: int) -> int:
    """
    Subtitr matni ekranning o'rtasidan biroz pastroqda aniq ko'rinadigan qilib joylanadi.
    MarginV video bo'yiga nisbatan avtomatik hisoblanadi (kadr tashqarisiga chiqib ketmaydi).
    """
    margin_bottom = int(video_h * 0.18)
    scaled_font_size = int(font_size * (video_w / 720.0))
    if scaled_font_size < 30:
        scaled_font_size = 30

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{scaled_font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,20,20,{margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    clean_words = []
    for w in words:
        txt = getattr(w, "word", None)
        if txt is None and isinstance(w, dict):
            txt = w.get("word", "")
        if txt is None:
            txt = str(w)
        txt = txt.strip()
        if not txt:
            continue

        st = getattr(w, "start", None)
        if st is None and isinstance(w, dict):
            st = w.get("start", 0.0)
        st = float(st or 0.0)

        et = getattr(w, "end", None)
        if et is None and isinstance(w, dict):
            et = w.get("end", st + 0.35)
        et = float(et or (st + 0.35))

        clean_words.append({"word": txt, "start": st, "end": et})

    if not clean_words:
        return 0

    dialogues = []
    chunk_size = 3
    for i in range(0, len(clean_words), chunk_size):
        chunk = clean_words[i:i + chunk_size]
        if not chunk:
            continue

        for active_idx, target_word in enumerate(chunk):
            w_start = target_word["start"]
            w_end = target_word["end"]

            line_parts = []
            for j, item in enumerate(chunk):
                word_text = item["word"]
                if j == active_idx:
                    if anim_style == "mrbeast_style":
                        formatted = f"{{\\c&H0000FFFF&\\t(0,70,\\fscx120\\fscy120)\\t(70,140,\\fscx100\\fscy100)}}{word_text}"
                    elif anim_style == "smooth_tracking":
                        formatted = f"{{\\fad(90,90)\\c&H00FFFF00&}}{word_text}"
                    elif anim_style == "active_bold_regular":
                        formatted = f"{{\\b1\\c&H000055FF&}}{word_text}{{\\b0}}"
                    elif anim_style == "active_word_box":
                        formatted = f"{{\\c&H00000000&\\4c&H0000FFFF&\\bord5}}{word_text}"
                    else:
                        formatted = f"{{\\c&H0000FFFF&}}{word_text}"
                else:
                    formatted = f"{{\\c&H00FFFFFF&}}{word_text}"

                line_parts.append(formatted)

            text_content = " ".join(line_parts)
            dialogues.append(f"Dialogue: 0,{format_ass_time(w_start)},{format_ass_time(w_end)},Default,,0,0,0,,{text_content}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(dialogues) + "\n")
    return len(dialogues)


async def burn_subtitles_to_video(input_video: Path, ass_path: Path, output_video: Path):
    """
    Videoni qirqmaydi (crop qilmaydi) va hajmini me'yorda saqlaydi.
    """
    clean_ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
    vf_filter = f"subtitles='{clean_ass}'"

    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(input_video),
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
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
        log.error(f"FFmpeg xatosi: {stderr.decode('utf-8', errors='ignore')}")
        raise RuntimeError("Subtitr yopishtirishda xatolik yuz berdi.")


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
    await callback.answer()
    user_id = callback.from_user.id
    if await check_subscription(bot, user_id):
        await callback.message.delete()
        await callback.message.answer(
            "Obunangiz tasdiqlandi! Xush kelibsiz.",
            reply_markup=get_main_keyboard()
        )
    else:
        await callback.message.answer("Siz hali kanalga obuna bo'lmadingiz! Iltimos, kanalga kiring va obuna bo'ling.")


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

    # Unikal vazifa ID (Tugmalar aynan shu vazifaga bog'lanadi, sessiya eskirib qolmaydi)
    task_id = str(int(time.time() * 1000))[-8:]
    w = message.video.width or 1080
    h = message.video.height or 1920
    dur = message.video.duration or 0

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO video_tasks (task_id, user_id, file_id, video_w, video_h, duration, anim_style, font_size)
            VALUES (?, ?, ?, ?, ?, ?, 'mrbeast_style', 60)
        """, (task_id, user_id, message.video.file_id, w, h, dur))
        conn.commit()

    builder = InlineKeyboardBuilder()
    for key, name in ANIMATION_STYLES.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"a:{task_id}:{key}"))

    await message.answer(
        "✨ Videongiz qabul qilindi!\n\nSubtitr uchun **animatsiya uslubini** tanlang:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("a:"))
async def callback_anim_style(callback: CallbackQuery):
    await callback.answer()
    _, task_id, style_key = callback.data.split(":")

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE video_tasks SET anim_style = ? WHERE task_id = ?", (style_key, task_id))
        conn.commit()

    builder = InlineKeyboardBuilder()
    for key, (name, _) in FONT_SIZES.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"s:{task_id}:{key}"))

    await callback.message.edit_text(
        "📱 Endi subtitr **shrift o'lchamini** tanlang:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("s:"))
async def callback_font_size(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    _, task_id, size_key = callback.data.split(":")

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM video_tasks WHERE task_id = ?", (task_id,))
        task = cursor.fetchone()

    if not task:
        await callback.message.answer("⚠️ Vazifa topilmadi. Iltimos videoni qaytadan yuboring.")
        return

    chosen_font_size = FONT_SIZES.get(size_key, ("Normal", 60))[1]
    user_id = task["user_id"]

    status_msg = await callback.message.edit_text("⏳ Video yuklab olinmoqda va tahlil qilinmoqda...")

    task_dir = WORK_ROOT / f"task_{task_id}"
    task_dir.mkdir(parents=True, exist_ok=True)
    input_video = task_dir / "input.mp4"
    output_video = task_dir / "output.mp4"
    ass_path = task_dir / "subs.ass"

    try:
        file_obj = await bot.get_file(task["file_id"])
        await bot.download_file(file_obj.file_path, destination=input_video)

        # Aniq o'lcham
        real_w, real_h, _ = get_exact_video_dimensions(input_video)
        if real_w == 0 or real_h == 0:
            real_w = task["video_w"]
            real_h = task["video_h"]

        await status_msg.edit_text("🎙 Ovoz tahlil qilinmoqda...")
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
            await status_msg.edit_text("❌ Videodan ovoz aniqlanmadi.")
            shutil.rmtree(task_dir, ignore_errors=True)
            return

        await status_msg.edit_text("✨ Subtitrlar animatsiya bilan yozilmoqda...")
        generate_word_by_word_ass(
            words=words,
            ass_path=ass_path,
            anim_style=task["anim_style"],
            font_size=chosen_font_size,
            video_w=real_w,
            video_h=real_h
        )

        await burn_subtitles_to_video(input_video, ass_path, output_video)

        if not is_user_pro(user_id):
            deduct_user_credit(user_id)

        remaining = get_user_credits(user_id)

        await bot.send_video(
            chat_id=user_id,
            video=FSInputFile(output_video),
            width=real_w,
            height=real_h,
            duration=task["duration"],
            supports_streaming=True,
            caption=f"🔥 Subtitr Tayyor!\n\n💳 Qolgan balans: {remaining} ta video",
            reply_markup=get_main_keyboard()
        )
        await status_msg.delete()

    except Exception as e:
        log.error(f"Xatolik: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")
    finally:
        shutil.rmtree(task_dir, ignore_errors=True)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM video_tasks WHERE task_id = ?", (task_id,))
            conn.commit()


@router.message(F.text == "🎨 Subtitr uslublari")
async def cmd_sub_styles(message: Message):
    styles_text = (
        "Subtitr uslublari:\n\n"
        "1. 🟢 Komika Axis Pop-up (MrBeast uslubi)\n"
        "2. ✨ Smooth Text Tracking (Fade)\n"
        "3. 🔥 Active Bold / Regular\n"
        "4. ⬛ Active Word Highlight (Box)\n\n"
        "Video yuborganingizda tugmalar orqali tanlashingiz mumkin."
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
