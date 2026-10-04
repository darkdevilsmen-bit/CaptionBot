import os
import re
import time
import uuid
import struct
import shutil
import sqlite3
import asyncio
import logging
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from elevenlabs.client import ElevenLabs
import imageio_ffmpeg

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# --- SOZLAMALAR ---
# Kalitlar shu yerda yozilgan. Xohlasangiz muhit o'zgaruvchisi (BOT_TOKEN / ELEVENLABS_API_KEY) bilan almashtirish mumkin.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8933394511:AAFJB8PAaNwHC3w0TpKvDrkRoRm-cIwkxEM")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "sk_2645eb8c6ab7457d5661f30bc9935e8107560bec586b14c8")

ADMIN_ID = 7662888182
ADMIN_USERNAME = "Captions_Admin"
ADMIN_PHONE = "+998 (93) 495-10-89"
REQUIRED_CHANNEL = "@Auto_Captions"

CARD_NUMBER = "5614686505428600"
CARD_HOLDER = "Toshpulatov Shoxrux"

MAX_VIDEO_BYTES = 50 * 1024 * 1024
WORK_ROOT = Path("temp_processing")
FONTS_DIR = Path("fonts").resolve()   # shriftlar shu papkada saqlanadi (Montserrat o'zi yuklanadi)
DB_FILE = Path("database.db")
INITIAL_CREDITS = 1

ANIMATION_STYLES = {
    "mrbeast_style": "🟢 MrBeast Pop-up",
    "smooth_tracking": "✨ Smooth Text Tracking (Fade)",
    "active_bold_regular": "🔥 Active Bold / Regular",
    "active_word_box": "⬛ Active Word Highlight (Box)",
}

FONT_SIZES = {
    "small": ("🔽 Kichik (70)", 70),
    "normal": ("📱 Normal (85)", 85),
    "large": ("📈 Katta (100)", 100),
    "xlarge": ("🔥 Juda katta (115)", 115),
}

# Montserrat uchun harflar orasi biroz zichroq (manfiy = zichroq). Font o'lchamiga nisbatan.
MONTSERRAT_SPACING = -0.03

_GF = "https://github.com/google/fonts/raw/main/ofl/montserrat/static/"
# Shriftlar fonts/ papkasidan (yoki bot.py yonidan) topiladi. Family nomi fayl ichidan o'qiladi.
#   tokens — fayl nomida (bo'sh joy, _ va - siz, kichik harfda) bo'lishi shart bo'lgan so'zlar
FONT_OPTIONS = {
    "the_bold": {"label": "🅱️ The Bold", "family": "The Bold Font", "tokens": ("thebold",),
                 "url": None, "bold_ok": False, "tight": False},
    "komika": {"label": "🟢 Komika Axis", "family": "Komika Axis", "tokens": ("komika",),
               "url": None, "bold_ok": True, "tight": False},
    "mont_xb": {"label": "💪 Montserrat ExtraBold", "family": "Montserrat ExtraBold", "tokens": ("montserrat", "extrabold"),
                "url": _GF + "Montserrat-ExtraBold.ttf", "bold_ok": False, "tight": True},
    "mont_black": {"label": "⚫ Montserrat Black", "family": "Montserrat Black", "tokens": ("montserrat", "black"),
                   "url": _GF + "Montserrat-Black.ttf", "bold_ok": False, "tight": True},
}
DEFAULT_FONT_KEY = "the_bold"

BASE_COLOR = "&H00FFFFFF"    # oq (BGR formatda)
ACTIVE_COLOR = "&H0000FFFF"  # sariq

router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

PROCESSING: set = set()  # hozir ishlov berilayotgan foydalanuvchilar (qo'sh bosishdan himoya)


# ---------------------------------------------------------------- KLAVIATURA
def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="⚡ Auto Subtitr qo'yish")],
        [KeyboardButton(text="🎨 Subtitr uslublari"), KeyboardButton(text="💳 Balans")],
        [KeyboardButton(text="💎 PRO Tariflar"), KeyboardButton(text="📜 Oferta")],
        [KeyboardButton(text="👨‍💻 Admin bilan bog'lanish")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ------------------------------------------------------------------ BAZA
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 1,
                is_pro INTEGER DEFAULT 0,
                bot_lang TEXT DEFAULT 'uz',
                terms_accepted INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                user_id INTEGER PRIMARY KEY,
                sid TEXT,
                file_id TEXT,
                video_path TEXT,
                dir_path TEXT,
                anim_style TEXT,
                font_key TEXT,
                font_size INTEGER,
                created REAL
            )
            """
        )
        conn.commit()


def get_user_credits(user_id: int, username: str = "") -> int:
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT OR IGNORE INTO users (user_id, username, credits, is_pro, bot_lang, terms_accepted) "
                "VALUES (?, ?, ?, 0, 'uz', 0)",
                (user_id, username, INITIAL_CREDITS),
            )
            conn.commit()
            return INITIAL_CREDITS
        return row[0]


def is_user_pro(user_id: int) -> bool:
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT is_pro FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and row[0] == 1)


def deduct_user_credit(user_id: int) -> bool:
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET credits = credits - 1 WHERE user_id = ? AND credits > 0", (user_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------- SESSIYALAR (bazada)
# Sessiya bazada saqlanadi, shuning uchun bot qayta ishga tushsa ham tugmalar ishlayveradi.
_SESSION_COLS = {"anim_style", "font_key", "font_size"}


def db_save_session(user_id: int, sid: str, file_id: str, video_path: str, dir_path: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (user_id, sid, file_id, video_path, dir_path, anim_style, font_key, font_size, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, sid, file_id, video_path, dir_path, "mrbeast_style", DEFAULT_FONT_KEY, 85, time.time()),
        )
        conn.commit()


def db_get_session(user_id: int) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def db_update_session(user_id: int, **fields):
    fields = {k: v for k, v in fields.items() if k in _SESSION_COLS}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(f"UPDATE sessions SET {sets} WHERE user_id = ?", (*fields.values(), user_id))
        conn.commit()


def db_delete_session(user_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()


def cleanup_stale_sessions(max_age_sec: int = 24 * 3600):
    """24 soatdan eski sessiyalar va yetim vaqtinchalik papkalarni tozalaydi."""
    now = time.time()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("SELECT user_id, dir_path, created FROM sessions").fetchall()
        for uid, dir_path, created in rows:
            if now - (created or 0) > max_age_sec:
                shutil.rmtree(dir_path, ignore_errors=True)
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
        conn.commit()
        alive = {Path(r[0]).resolve() for r in conn.execute("SELECT dir_path FROM sessions").fetchall()}
    if WORK_ROOT.exists():
        for d in WORK_ROOT.iterdir():
            if d.is_dir() and d.resolve() not in alive and now - d.stat().st_mtime > 3600:
                shutil.rmtree(d, ignore_errors=True)


async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        log.error(f"Obunani tekshirishda xatolik: {e}")
        return False


# ------------------------------------------------------- VAQT FORMATLARI
def format_srt_time(seconds: float) -> str:
    """SRT: HH:MM:SS,mmm  (masalan 00:01:05,320)"""
    total_ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_ass_time(seconds: float) -> str:
    """ASS: H:MM:SS.cc  (ASS millisekund emas, santisekund ishlatadi)"""
    total_cs = max(0, int(round(seconds * 100)))
    h, rem = divmod(total_cs, 360_000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ----------------------------------------- TOZA MATNNI AJRATIB OLISH (ASOSIY FIX)
def _get(obj: Any, *names: str, default: Any = None) -> Any:
    """Obyekt (attribut) yoki dict'dan birinchi mavjud maydonni oladi."""
    for name in names:
        if isinstance(obj, dict):
            if obj.get(name) is not None:
                return obj[name]
        else:
            val = getattr(obj, name, None)
            if val is not None:
                return val
    return default


_HAS_ALNUM = re.compile(r"[^\W_]", re.UNICODE)
_EVENT_TAG = re.compile(r"^[\(\[\*<].*[\)\]\*>]$")  # (musiqa), [shovqin], *kulgi*


def clean_text(raw: Any) -> str:
    """Faqat str qabul qiladi. Obyektni hech qachon str() qilmaydi."""
    if not isinstance(raw, str):
        return ""
    text = raw.replace("\\N", " ").replace("\\n", " ")
    text = re.sub(r"[{}\\]", "", text)      # ASS override belgilarini olib tashlash
    text = re.sub(r"\s+", " ", text).strip()
    if not text or _EVENT_TAG.match(text) or not _HAS_ALNUM.search(text):
        return ""
    return text


def extract_clean_words(transcript: Any) -> List[Dict[str, Any]]:
    """
    ElevenLabs javobidan [{'text', 'start', 'end'}, ...] ro'yxatini yasaydi.
    - so'z matni `.text` da (Whisper uslubidagi `.word` ham qo'llab-quvvatlanadi)
    - 'spacing' va 'audio_event' turlari tashlab yuboriladi
    - bo'sh / faqat belgi / shovqin teglari filtrlanadi
    """
    raw_words = _get(transcript, "words", default=[]) or []
    result: List[Dict[str, Any]] = []

    for w in raw_words:
        w_type = _get(w, "type")
        if w_type is not None and str(w_type).lower() != "word":
            continue

        text = clean_text(_get(w, "text", "word"))
        if not text:
            continue

        start = _get(w, "start")
        end = _get(w, "end")
        try:
            start = float(start)
            end = float(end) if end is not None else start + 0.3
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + 0.2

        result.append({"text": text, "start": start, "end": end})

    return result


def group_into_chunks(words: List[Dict[str, Any]], max_words: int = 4, max_gap: float = 0.8, max_chars: int = 24) -> List[List[Dict[str, Any]]]:
    """So'zlarni qisqa qatorlarga bo'ladi (pauza yoki tinish belgisida uziladi)."""
    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for w in words:
        if current:
            gap = w["start"] - current[-1]["end"]
            ends_sentence = current[-1]["text"][-1] in ".!?…"
            too_long = sum(len(x["text"]) + 1 for x in current) + len(w["text"]) > max_chars
            if len(current) >= max_words or gap > max_gap or ends_sentence or too_long:
                chunks.append(current)
                current = []
        current.append(w)
    if current:
        chunks.append(current)
    return chunks


# ------------------------------------------------------------ SRT / ASS
def write_srt(chunks: List[List[Dict[str, Any]]], srt_path: Path) -> int:
    lines = []
    for idx, chunk in enumerate(chunks, 1):
        text = " ".join(w["text"] for w in chunk)
        lines.append(
            f"{idx}\n{format_srt_time(chunk[0]['start'])} --> {format_srt_time(chunk[-1]['end'])}\n{text}\n"
        )
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return len(chunks)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_font_file(key: str) -> Optional[Path]:
    """fonts/ papkasidan (yoki bot.py yonidagi papkadan) shrift faylini topadi."""
    opt = FONT_OPTIONS.get(key)
    if not opt:
        return None
    for folder in (FONTS_DIR, Path(".").resolve()):
        if not folder.exists():
            continue
        for f in sorted(folder.iterdir()):
            n = _norm(f.stem)
            if f.suffix.lower() in (".ttf", ".otf") and "italic" not in n and all(t in n for t in opt["tokens"]):
                return f
    return None


def read_font_family(path: Path) -> Optional[str]:
    """TTF/OTF faylning 'name' jadvalidan haqiqiy family nomini o'qiydi (FFmpeg/libass aynan shu nom bilan qidiradi)."""
    try:
        data = path.read_bytes()
        base = 0
        if data[:4] == b"ttcf":
            base = struct.unpack(">I", data[12:16])[0]
        num_tables = struct.unpack(">H", data[base + 4:base + 6])[0]
        name_off = None
        for i in range(num_tables):
            rec = data[base + 12 + 16 * i: base + 28 + 16 * i]
            if rec[:4] == b"name":
                name_off = struct.unpack(">I", rec[8:12])[0]
                break
        if name_off is None:
            return None
        count, str_off = struct.unpack(">HH", data[name_off + 2:name_off + 6])
        found: Dict[int, str] = {}
        for i in range(count):
            plat, enc, lang, nid, length, off = struct.unpack(">HHHHHH", data[name_off + 6 + 12 * i: name_off + 18 + 12 * i])
            if nid not in (1, 4, 16):
                continue
            raw = data[name_off + str_off + off: name_off + str_off + off + length]
            try:
                text = raw.decode("utf-16-be") if plat in (0, 3) else raw.decode("mac_roman")
            except Exception:
                continue
            text = text.strip().replace(",", " ")
            if text and (nid not in found or (plat == 3 and lang == 0x409)):
                found[nid] = text
        return found.get(1) or found.get(16) or found.get(4)
    except Exception as e:
        log.warning(f"Shrift nomini o'qib bo'lmadi ({path.name}): {e}")
        return None


def resolve_font(key: str) -> Tuple[str, bool, bool, Optional[Path]]:
    """(family nomi, qalin tegi ishlatilsinmi, zich harf oralig'i, fayl). Shrift topilmasa Arial."""
    opt = FONT_OPTIONS.get(key)
    if opt:
        f = find_font_file(key)
        if f:
            return read_font_family(f) or opt["family"], opt["bold_ok"], opt["tight"], f
    return "Arial", True, False, None


def available_fonts() -> List[str]:
    return [k for k in FONT_OPTIONS if find_font_file(k)]


async def ensure_fonts():
    """Montserrat fayllari yo'q bo'lsa Google Fonts'dan yuklab oladi (bir marta)."""
    import aiohttp
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for key, opt in FONT_OPTIONS.items():
        url = opt["url"]
        if not url or find_font_file(key):
            continue
        dest = FONTS_DIR / url.rsplit("/", 1)[-1]
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as sess:
                async with sess.get(url) as resp:
                    status = resp.status
                    data = await resp.read()
            if status != 200 or len(data) < 50_000 or data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
                raise RuntimeError(f"noto'g'ri javob (status={status}, {len(data)} bayt)")
            dest.write_bytes(data)
            log.info(f"Shrift yuklandi: {dest.name}")
        except Exception as e:
            log.warning(f"{dest.name} yuklanmadi ({e}). Xohlasangiz faylni qo'lda {FONTS_DIR} ichiga qo'ying.")


def _style_word(text: str, active: bool, anim_style: str, bold_ok: bool = True) -> str:
    b1, b0 = ("\\b1", "\\b0") if bold_ok else ("", "")
    if not active:
        return f"{{\\c{BASE_COLOR}&{b0}}}{text}"
    if anim_style == "mrbeast_style":
        return (f"{{\\c{ACTIVE_COLOR}&{b1}\\t(0,90,\\fscx125\\fscy125)\\t(90,180,\\fscx100\\fscy100)}}"
                f"{text}{{\\fscx100\\fscy100}}")
    if anim_style == "active_bold_regular":
        return f"{{\\c{ACTIVE_COLOR}&{b1}}}{text}{{{b0}}}"
    if anim_style == "active_word_box":
        return f"{{\\c&H00000000&\\3c{ACTIVE_COLOR}&\\bord7}}{text}{{\\bord3\\3c&H00000000&}}"
    return f"{{\\c{ACTIVE_COLOR}&}}{text}"  # smooth_tracking


def generate_word_by_word_ass(
    chunks: List[List[Dict[str, Any]]],
    ass_path: Path,
    anim_style: str,
    font_size: int,
    video_w: int,
    video_h: int,
    font_key: str = DEFAULT_FONT_KEY,
) -> int:
    font_name, bold_ok, tight, _ = resolve_font(font_key)
    # Shrift o'lchami 1080 px asosida berilgan: video o'lchamiga moslaymiz
    font_size = max(24, int(round(font_size * min(video_w, video_h) / 1080)))
    spacing = round(font_size * MONTSERRAT_SPACING, 1) if tight else 0
    bold_flag = -1 if bold_ok else 0
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{BASE_COLOR},&H000000FF,&H00000000,&H80000000,{bold_flag},0,0,0,100,100,{spacing},0,1,3,0,2,40,40,{int(video_h * 0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues: List[str] = []
    for chunk in chunks:
        for i, active_word in enumerate(chunk):
            start = active_word["start"]
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else active_word["end"]
            if end <= start:
                end = start + 0.1

            parts = [
                _style_word(w["text"], j == i, anim_style, bold_ok)
                for j, w in enumerate(chunk)
            ]
            text = " ".join(parts)
            if anim_style == "smooth_tracking" and i == 0:
                text = "{\\fad(120,0)}" + text
            dialogues.append(
                f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},Default,,0,0,0,,{text}"
            )

    ass_path.write_text(header + "\n".join(dialogues) + "\n", encoding="utf-8")
    return len(dialogues)


# ------------------------------------------------------------------ FFMPEG
async def _run(cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
    )
    _, stderr = await proc.communicate()
    return proc.returncode, stderr.decode("utf-8", errors="ignore")


async def get_video_resolution(video_path: Path) -> Tuple[int, int]:
    """imageio-ffmpeg ichida ffprobe yo'q, shuning uchun `ffmpeg -i` chiqishini o'qiymiz."""
    _, err = await _run([FFMPEG_PATH, "-hide_banner", "-i", str(video_path)])
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", err)
    if not m:
        return 1080, 1920
    w, h = int(m.group(1)), int(m.group(2))
    rot = re.search(r"rotation of (-?\d+(?:\.\d+)?) degrees", err)
    if rot and abs(int(float(rot.group(1)))) in (90, 270):
        w, h = h, w
    return w, h


async def extract_audio(video: Path, audio: Path):
    code, err = await _run(
        [FFMPEG_PATH, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(audio)]
    )
    if code != 0:
        log.error(f"Audio ajratishda xato: {err[-800:]}")
        raise RuntimeError("Videodan audio ajratib bo'lmadi (ovoz yo'li yo'q bo'lishi mumkin).")


def _ff_escape(path: str) -> str:
    """Filtergraph ichidagi yo'l uchun escape."""
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


async def burn_subtitles_to_video(input_video: Path, ass_name: str, output_video: Path, work_dir: Path, font_key: str = DEFAULT_FONT_KEY):
    """
    ASS faylga faqat NISBIY nom beriladi va FFmpeg work_dir ichida ishga tushadi:
    shunda Windows `C:\\...` va bo'sh joy/ikki nuqta muammolari chiqmaydi.
    """
    vf = f"subtitles={ass_name}"
    font_file = resolve_font(font_key)[3]
    if font_file:
        vf += f":fontsdir='{_ff_escape(str(font_file.parent))}'"

    cmd = [
        FFMPEG_PATH, "-y",
        "-i", str(input_video.resolve()),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_video.resolve()),
    ]
    code, err = await _run(cmd, cwd=work_dir)
    if code != 0:
        log.error(f"FFmpeg xatosi: {err[-1500:]}")
        raise RuntimeError("Videoga subtitr yopishtirishda xatolik yuz berdi.")


# --------------------------------------------------------------- HANDLERLAR
@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    get_user_credits(user_id, message.from_user.username or "")

    if REQUIRED_CHANNEL and not await check_subscription(bot, user_id):
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="📢 Kanalga obuna bo'lish",
            url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"))
        builder.row(InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub"))
        await message.answer(
            f"Botimizdan to'liq foydalanish uchun avval rasmiy kanalimizga obuna bo'ling:\n{REQUIRED_CHANNEL}",
            reply_markup=builder.as_markup(),
        )
        return

    await message.answer(
        "Assalomu alaykum! Auto Subtitles botiga xush kelibsiz.\n"
        "Videongizga professional darajada avtomatik subtitrlar qo'shib beraman.",
        reply_markup=get_main_keyboard(),
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
        target, amount = int(args[1]), int(args[2])
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, target))
            conn.commit()
        await message.answer(f"Foydalanuvchi ({target}) balansiga {amount} ta video qo'shildi.")
    except Exception as e:
        await message.answer(f"Xatolik: {escape(str(e))}")


@router.message(Command("pro"))
async def cmd_set_pro(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Ishlatish: /pro [user_id]")
        return
    try:
        target = int(args[1])
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target,))
            conn.commit()
        await message.answer(f"Foydalanuvchi ({target}) PRO statusga o'tkazildi.")
    except Exception as e:
        await message.answer(f"Xatolik: {escape(str(e))}")


@router.callback_query(F.data == "check_sub")
async def callback_check_sub(callback: CallbackQuery, bot: Bot):
    if await check_subscription(bot, callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("Obunangiz tasdiqlandi! Xush kelibsiz.", reply_markup=get_main_keyboard())
    else:
        await callback.answer("Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)


NO_CREDITS_TEXT = (
    "Balansingizda video yaratish uchun urinishlar qolmadi.\n\n"
    "Ko'proq video yaratish uchun PRO tarifga o'ting"
)


@router.message(F.text == "⚡ Auto Subtitr qo'yish")
async def cmd_auto_subtitles(message: Message):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    if credits <= 0 and not is_user_pro(user_id):
        await message.answer(NO_CREDITS_TEXT, reply_markup=get_main_keyboard())
        return
    await message.answer(
        "Marhamat, subtitr qo'shilishi kerak bo'lgan videoni yuboring.\n\n"
        "(Video formati MP4, hajmi 50 MB dan oshmasligi kerak)",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.video)
async def handle_video(message: Message, bot: Bot):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    if credits <= 0 and not is_user_pro(user_id):
        await message.answer(NO_CREDITS_TEXT, reply_markup=get_main_keyboard())
        return

    if user_id in PROCESSING:
        await message.answer("⏳ Oldingi videongiz hali tayyorlanmoqda, iltimos kuting.")
        return

    if message.video.file_size and message.video.file_size > MAX_VIDEO_BYTES:
        await message.answer("❌ Video hajmi 50 MB dan oshmasligi kerak.")
        return

    # Eski sessiya papkasi qolib ketgan bo'lsa tozalaymiz
    old = db_get_session(user_id)
    if old:
        shutil.rmtree(old["dir_path"], ignore_errors=True)
        db_delete_session(user_id)

    sid = uuid.uuid4().hex[:8]
    user_dir = WORK_ROOT / str(uuid.uuid4())
    user_dir.mkdir(parents=True, exist_ok=True)
    input_video = user_dir / "input.mp4"

    try:
        file_info = await bot.get_file(message.video.file_id)
        await bot.download_file(file_info.file_path, destination=input_video)
    except Exception as e:
        shutil.rmtree(user_dir, ignore_errors=True)
        log.error(f"Yuklab olishda xatolik: {e}")
        await message.answer("❌ Videoni yuklab olib bo'lmadi (Telegram cheklovi: ~20 MB gacha bo'lishi mumkin).")
        return

    db_save_session(user_id, sid, message.video.file_id, str(input_video), str(user_dir))

    builder = InlineKeyboardBuilder()
    for key, name in ANIMATION_STYLES.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"anim:{key}:{sid}"))
    await message.reply(
        "✨ Videongiz qabul qilindi!\n\nSubtitr uchun <b>animatsiya uslubini</b> tanlang:",
        reply_markup=builder.as_markup(),
    )


async def load_session(callback: CallbackQuery, bot: Bot, sid: str) -> Optional[Dict[str, Any]]:
    """Sessiyani bazadan oladi. Video fayl yo'qolgan bo'lsa (masalan, server qayta ishga tushsa) Telegram'dan qayta yuklaydi."""
    user_id = callback.from_user.id
    sess = db_get_session(user_id)
    if not sess or sess["sid"] != sid:
        await callback.answer("Bu tugma eskirgan. Iltimos, videoni qaytadan yuboring.", show_alert=True)
        return None
    video = Path(sess["video_path"])
    if not video.exists():
        try:
            video.parent.mkdir(parents=True, exist_ok=True)
            file_info = await bot.get_file(sess["file_id"])
            await bot.download_file(file_info.file_path, destination=video)
        except Exception as e:
            log.error(f"Videoni qayta yuklab bo'lmadi: {e}")
            shutil.rmtree(sess["dir_path"], ignore_errors=True)
            db_delete_session(user_id)
            await callback.answer("Videoni qayta yuklab bo'lmadi. Iltimos, videoni qaytadan yuboring.", show_alert=True)
            return None
    return sess


def _parse_cb(data: str) -> Optional[Tuple[str, str]]:
    parts = data.split(":", 2)
    return (parts[1], parts[2]) if len(parts) == 3 else None


@router.callback_query(F.data.startswith("anim:"))
async def callback_anim_style(callback: CallbackQuery, bot: Bot):
    parsed = _parse_cb(callback.data)
    if not parsed or parsed[0] not in ANIMATION_STYLES:
        await callback.answer("Noma'lum uslub.", show_alert=True)
        return
    style_key, sid = parsed
    sess = await load_session(callback, bot, sid)
    if not sess:
        return
    db_update_session(callback.from_user.id, anim_style=style_key)

    builder = InlineKeyboardBuilder()
    fonts = available_fonts()
    for key in fonts:
        builder.row(InlineKeyboardButton(text=FONT_OPTIONS[key]["label"], callback_data=f"font:{key}:{sid}"))
    if not fonts:
        builder.row(InlineKeyboardButton(text="🔤 Standart shrift", callback_data=f"font:arial:{sid}"))
    await callback.message.edit_text("🔠 Subtitr <b>shriftini</b> tanlang:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("font:"))
async def callback_font_family(callback: CallbackQuery, bot: Bot):
    parsed = _parse_cb(callback.data)
    if not parsed or (parsed[0] not in FONT_OPTIONS and parsed[0] != "arial"):
        await callback.answer("Bu shrift mavjud emas.", show_alert=True)
        return
    key, sid = parsed
    sess = await load_session(callback, bot, sid)
    if not sess:
        return
    db_update_session(callback.from_user.id, font_key=key)

    builder = InlineKeyboardBuilder()
    for skey, (name, _) in FONT_SIZES.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"size:{skey}:{sid}"))
    await callback.message.edit_text("📱 Endi subtitr <b>shrift o'lchamini</b> tanlang:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("size:"))
async def callback_font_size(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    parsed = _parse_cb(callback.data)
    if not parsed or parsed[0] not in FONT_SIZES:
        await callback.answer("Noma'lum o'lcham.", show_alert=True)
        return
    size_key, sid = parsed

    if user_id in PROCESSING:
        await callback.answer("Video tayyorlanmoqda, iltimos kuting...", show_alert=True)
        return

    session = await load_session(callback, bot, sid)
    if not session:
        return

    if get_user_credits(user_id) <= 0 and not is_user_pro(user_id):
        await callback.answer(NO_CREDITS_TEXT, show_alert=True)
        return

    PROCESSING.add(user_id)
    await callback.answer()

    font_size = FONT_SIZES[size_key][1]
    font_key = session["font_key"] or DEFAULT_FONT_KEY
    anim_style = session["anim_style"] or "mrbeast_style"
    input_video = Path(session["video_path"])
    user_dir = Path(session["dir_path"])
    output_video = user_dir / "output.mp4"
    audio_path = user_dir / "audio.mp3"
    ass_name = "subs.ass"
    ass_path = user_dir / ass_name
    srt_path = user_dir / "subs.srt"

    status_msg = await callback.message.edit_text("✨ Subtitrlar tayyorlanmoqda, iltimos kuting...")

    try:
        v_width, v_height = await get_video_resolution(input_video)
        await extract_audio(input_video, audio_path)

        def _transcribe():
            with open(audio_path, "rb") as f:
                return el_client.speech_to_text.convert(
                    file=f,
                    model_id="scribe_v1",
                    tag_audio_events=False,
                    timestamps_granularity="word",
                )

        # Bloklovchi so'rov botni qotirib qo'ymasligi uchun alohida oqimda
        transcript = await asyncio.to_thread(_transcribe)

        words = extract_clean_words(transcript)
        if not words:
            await status_msg.edit_text("❌ Videodan ovoz topilmadi yoki matnga o'girib bo'lmadi.")
            return

        chunks = group_into_chunks(words)
        write_srt(chunks, srt_path)
        generate_word_by_word_ass(chunks, ass_path, anim_style, font_size, v_width, v_height, font_key)

        await burn_subtitles_to_video(input_video, ass_name, output_video, user_dir, font_key)

        if not is_user_pro(user_id):
            deduct_user_credit(user_id)
        remaining = get_user_credits(user_id)

        await bot.send_video(
            chat_id=user_id,
            video=FSInputFile(output_video),
            caption=f"🔥 Subtitr Tayyor!\n\n💳 Qolgan balans: {remaining} ta video",
            reply_markup=get_main_keyboard(),
        )
        await bot.send_document(chat_id=user_id, document=FSInputFile(srt_path), caption="📄 SRT fayl")
        await status_msg.delete()

    except Exception as e:
        log.exception("Video qayta ishlashda xatolik")
        try:
            await status_msg.edit_text(f"❌ Xatolik yuz berdi: {escape(str(e))}\n\nIltimos, videoni qaytadan yuboring.")
        except Exception:
            pass
    finally:
        PROCESSING.discard(user_id)
        shutil.rmtree(user_dir, ignore_errors=True)
        db_delete_session(user_id)


@router.message(F.text == "🎨 Subtitr uslublari")
async def cmd_sub_styles(message: Message):
    await message.answer(
        "Subtitr uslublarini tanlash:\n\n"
        "Hozirda quyidagi animatsiya uslublari mavjud:\n"
        "1. MrBeast Pop-up\n"
        "2. Smooth Text Tracking (Fade)\n"
        "3. Active Bold / Regular\n"
        "4. Active Word Highlight (Box)\n\n"
        "Video yuborganingizdan so'ng uslubni tanlashingiz mumkin.",
        reply_markup=get_main_keyboard(),
    )


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
        reply_markup=get_main_keyboard(),
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
        f"To'lov uchun karta (bosib nusxalash mumkin):\n<code>{CARD_NUMBER}</code>\n"
        f"Karta egasi: {escape(CARD_HOLDER)}\n\n"
        f"To'lovni amalga oshirgach, chekni darhol adminga yuboring: @{ADMIN_USERNAME}"
    )
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(F.text == "📜 Oferta")
async def cmd_terms(message: Message):
    await message.answer(
        "Foydalanish shartlari va Ommaviy Oferta:\n\n"
        "1. Umumiy qoidalar:\n"
        "Ushbu shartnoma Auto Subtitles boti orqali taqdim etiladigan xizmatlardan foydalanish qoidalarini belgilaydi. "
        "Botdan foydalanishni boshlagan har bir shaxs ushbu shartlarga to'liq rozilik bildirgan hisoblanadi.\n\n"
        "2. Xizmatlar mazmuni:\n"
        "Bot foydalanuvchilar tomonidan yuborilgan videolarga sun'iy intellekt yordamida avtomatik subtitrlar "
        "(taglavhalar) qo'shib berish xizmatini ko'rsatadi.\n\n"
        "3. To'lovlar va tariflar:\n"
        "Xizmatlar pullik va bepul asosda taqdim etiladi. PRO tariflar uchun qilingan to'lovlar raqamli xizmat "
        "ko'rsatilganligi sababli qaytarilmaydi.\n\n"
        "4. Foydalanuvchi mas'uliyati:\n"
        "Foydalanuvchi yuklayotgan videolari O'zbekiston Respublikasi qonunchiligiga zid kelmasligini, mualliflik "
        "huquqlarini buzmasligini va boshqalarning huquqlarini poymol qilmasligini kafolatlaydi.\n\n"
        "5. Maxfiylik:\n"
        "Foydalanuvchining shaxsiy ma'lumotlari xavfsiz saqlanadi va uchinchi shaxslarga berilmaydi.",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def cmd_contact_admin(message: Message):
    await message.answer(
        f"Texnik yordam va Admin:\n\n"
        f"Murojaat uchun: @{ADMIN_USERNAME}\n"
        f"Telefon raqam: {ADMIN_PHONE}",
        reply_markup=get_main_keyboard(),
    )


async def main():
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    init_db()
    cleanup_stale_sessions()
    await ensure_fonts()
    log.info(f"Mavjud shriftlar: {[FONT_OPTIONS[k]['label'] for k in available_fonts()] or 'faqat Arial'}")

    bot = Bot(
        token=BOT_TOKEN,
        session=AiohttpSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.set_my_commands([BotCommand(command="start", description="Botni ishga tushirish / Asosiy menyu")])

    log.info("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi.")
