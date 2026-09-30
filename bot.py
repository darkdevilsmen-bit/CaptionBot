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

from PIL import Image, ImageDraw, ImageFont
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
FONTS_DIR = Path("fonts")
DB_FILE = Path("database.db")
INITIAL_CREDITS = 3

VIDEO_LANGS = {
    "uz": ("🇺🇿 O'zbekcha", "uz"),
    "ru": ("🇷🇺 Ruscha", "ru"),
    "en": ("🇬🇧 Inglizcha", "en"),
}

COLORS = {
    "white":  ("⚪ 100% Oppoq (Pro)", (255, 255, 255)),
    "yellow": ("🟡 Sariq (Tracking Style)", (255, 255, 0)),
    "green":  ("🟢 Yashil", (0, 255, 0)),
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


def create_word_image(text: str, text_color: tuple, font_size: int, output_path: Path):
    font_path = FONTS_DIR / "KomikaAxis.ttf"
    try:
        font = ImageFont.truetype(str(font_path), font_size)
    except Exception:
        font = ImageFont.load_default()

    # Tasvir o'lchamini aniqlash (Vertikal 1080x1920 video uchun standart canvas)
    canvas_width = 1080
    canvas_height = 300
    img = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Matn koordinatalarini markazga to'g'rilash
    bbox = d.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = (canvas_width - text_w) // 2
    y = (canvas_height - text_h) // 2

    # Qalin qora kontur (outline)
    outline_color = (0, 0, 0, 255)
    for ox in range(-4, 5):
        for oy in range(-4, 5):
            if ox != 0 or oy != 0:
                d.text((x + ox, y + oy), text, font=font, fill=outline_color)

    # Asosiy rangdagi matn
    d.text((x, y), text, font=font, fill=(*text_color, 255))
    img.save(output_path, "PNG")


async def process_job(bot: Bot, job: Dict[str, Any]) -> None:
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    file_id = job["file_id"]
    lang = job["lang"]
    color = job["color"]
    font_size = 75
    job_key = job["key"]

    work_dir = WORK_ROOT / job_key
    work_dir.mkdir(parents=True, exist_ok=True)

    input_video = work_dir / "input.mp4"
    audio_path = work_dir / "audio.mp3"
    output_video = work_dir / "output.mp4"
    images_dir = work_dir / "images"
    images_dir.mkdir(exist_ok=True)

    status_msg = await bot.send_message(
        chat_id,
        "⚡ <b>Komika Axis Subtitle AI ishga tushdi!</b>\n\n"
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
            "⚡ <b>Komika Axis Subtitle AI ishga tushdi!</b>\n\n"
            "▓▓▓░░░░░░░ 40%\n\n"
            "🎙 <i>Audio tahlil qilinmoqda...</i>",
            parse_mode="HTML"
        )

        cmd_extract = [
            "ffmpeg", "-y", "-i", "input.mp4",
            "-vn", "-acodec", "libmp3lame", "-ar", "24000", "-ac", "1", "-b:a", "192k",
            "audio.mp3"
        ]
        await asyncio.to_thread(subprocess.run, cmd_extract, cwd=str(work_dir), capture_output=True, text=True)

        await status_msg.edit_text(
            "⚡ <b>Komika Axis Subtitle AI ishga tushdi!</b>\n\n"
            "▓▓▓▓▓▓░░░░ 70%\n\n"
            "✨ <i>Komika Axis shriftida so'zlar markazlashtirilmoqda...</i>",
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

        cleaned_words = []
        for w in words:
            raw_text = getattr(w, "text", None) or getattr(w, "word", None) or ""
            start = float(getattr(w, "start", 0.0))
            end = float(getattr(w, "end", start + 0.4))
            clean = str(raw_text).strip().upper()
            for ch in [".", ",", "!", "?", ":", ";", '"', "'", "-", "—", "_"]:
                clean = clean.replace(ch, "")
            if clean:
                if (end - start) < 0.35:
                    end = start + 0.35
                cleaned_words.append({"word": clean, "start": start, "end": end})

        if not cleaned_words:
            await status_msg.edit_text("❌ Videoda nutq aniqlanmadi.")
            return

        # So'zlarni 2-3 tadan guruhlab, har bir guruhni bitta markaziy rasmga aylantiramiz
        chunks = []
        chunk_size = 2
        for i in range(0, len(cleaned_words), chunk_size):
            chunk = cleaned_words[i:i + chunk_size]
            start_t = chunk[0]["start"]
            end_t = chunk[-1]["end"]
            text = " ".join([c["word"] for c in chunk])
            chunks.append({"text": text, "start": start_t, "end": end_t})

        # FFmpeg filter_complex yaratish (har bir guruh ekranning bir xil markaziy pastki qismida chiqadi)
        filter_parts = ["[0:v]"]
        last_out = "v0"

        for i, ch in enumerate(chunks):
            img_path = images_dir / f"chunk_{i}.png"
            create_word_image(ch["text"], color, font_size, img_path)

            start_t = ch["start"]
            end_t = ch["end"]
            next_input = f"v{i+1}"
            
            # overlay=(W-w)/2:H-h-300 — bu yerda matn har doim qat'iy markazda joylashadi
            filter_parts.append(
                f"[{last_out}][{i+1}:v] overlay=(W-w)/2:H-h-350:enable='between(t,{start_t},{end_t})'[{next_input}];"
            )
            last_out = next_input

        filter_complex = "".join(filter_parts)[:-1]

        cmd_render = ["ffmpeg", "-y", "-i", "input.mp4"]
        for i in range(len(chunks)):
            cmd_render.extend(["-i", str(images_dir / f"chunk_{i}.png")])

        cmd_render.extend([
            "-filter_complex", filter_complex,
            "-map", f"[{last_out}]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-c:a", "copy",
            "output.mp4"
        ])

        res = await asyncio.to_thread(subprocess.run, cmd_render, cwd=str(work_dir), capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"FFmpeg xatosi: {res.stderr[:200]}")

        deduct_user_credit(user_id)
        current_bal = get_user_credits(user_id)

        await status_msg.edit_text("📤 <b>Tayyor! Video yuborilmoqda...</b>", parse_mode="HTML")
        await bot.send_video(
            chat_id,
            video=FSInputFile(str(output_video)),
            caption=f"🔥 <b>Komika Axis Subtitr Tayyor!</b>\n\n💳 Balans: <b>{current_bal} ta video</b>",
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
    await message.answer("🎨 <b>Komika Axis shrifti markazlashgan holda ishlaydi.</b> Videongizni yuborib sinab ko'rishingiz mumkin!", parse_mode="HTML")


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
            f"⚠️️ <i>Sizda bepul foydalanish limiti tugadi!</i>\n"
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
        f"👨‍‍💻 <b>Admin:</b> @{ADMIN_USERNAME}"
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
        "color": (255, 255, 0),
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
    for cname, (title, _) in COLORS.items():
        kb.button(text=title, callback_data=f"col:{key}:{cname}")
    kb.adjust(2)
    await call.message.edit_text("2️⃣ Subtitr rangini tanlang:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("col:"))
async def on_color(call: CallbackQuery, bot: Bot) -> None:
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return
    _, key, cname = parts
    job = jobs.get(key)
    if not call.message:
        return
    if not job:
        await call.answer("Eskirgan so'rov.", show_alert=True)
        return

    job["color"] = COLORS[cname][1]
    jobs.pop(key, None)
    await call.message.edit_text("✅ Sozlamalar qabul qilindi. Komika Axis shriftida video tayyorlanmoqda...")
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
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    asyncio.create_task(web_server())
    await start_bot_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass