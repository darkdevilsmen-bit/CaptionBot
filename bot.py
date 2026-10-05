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
from urllib.parse import quote
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

try:
    from aiogram.types import CopyTextButton
except Exception:
    CopyTextButton = None

from elevenlabs.client import ElevenLabs
import imageio_ffmpeg

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# --- SOZLAMALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8933394511:AAE_-rkX_t_yhFF79k-fpQoosvHE1CtTp2o")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "sk_2645eb8c6ab7457d5661f30bc9935e8107560bec586b14c8")

ADMIN_ID = 7662888182
ADMIN_USERNAME = "Captions_Admin"
ADMIN_PHONE = "+998 (93) 495-10-89"

REQUIRED_CHANNEL = "@Auto_Captions"

CARD_NUMBER = "5614686505428600"
CARD_HOLDER = "Toshpulatov Shoxrux"

MAX_VIDEO_BYTES = 50 * 1024 * 1024
WORK_ROOT = Path("temp_processing").resolve()
FONTS_DIR = Path("fonts").resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", ".")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "database.db"
STT_MODEL = os.getenv("STT_MODEL", "scribe_v2")
INITIAL_CREDITS = 1

HEADLIGHT_WORDS = {
    "chirchiq", "chirchiqda", "chirchiqning", "chirchiqliklar", "chirchiqqa",
    "toshkent", "toshkentda", "samarqand", "buxoro", "andijon", "farg'ona",
    "namangan", "qashqadaryo", "surxondaryo", "xorazm", "navoiy", "jizzax",
    "qoraqalpog'iston", "o'zbekiston", "ozbekiston", "rossiya", "turkiya", "dubay",
    "diqqat", "ogohlantirish", "shoshiling", "tezkor", "bomba", "daxshat",
    "dahshat", "shok", "yangilik", "sensatsiya", "muhim", "rasman", "favqulodda",
    "qarang", "eshiting", "tomosha", "sir", "sirlari", "haqiqat", "aldov",
    "xushxabar", "afsus", "voy", "o'rtoqlar", "do'stlar", "odamlar", "xalq",
    "vapshe", "vapsheyam", "zo'r", "daraxt", "gap", "yo'q", "gapyo'q", "lekin",
    "prosto", "chempion", "super", "klass", "top", "trend", "reels", "video",
    "bunaqasi", "bo'lmagan", "ko'ring", "aytgancha", "rosti", "aniq", "tiniq",
    "chotki", "otdushi", "baza", "yondiradi", "portlatdi", "dod", "voydod",
    "narxi", "qancha", "so'm", "dollar", "valyuta", "kurs", "tekin", "bepul",
    "skidka", "aksiya", "arzon", "qimmat", "foyda", "daromad", "sovg'a", "yutuq",
    "bonus", "pulingiz", "pul", "million", "milliard", "sotuvda", "xarid",
    "buyurtma", "yetkazib", "berish", "magazin", "do'kon", "bozor", "savdo",
    "kafolat", "kredit", "rassrochka", "foizsiz", "halol",
    "obuna", "layk", "komment", "repost", "podpiska", "profil", "ssilka",
    "admin", "kanal", "guruh", "direct", "lichka", "raqam", "telefon", "manzil",
    "lokatsiya", "aloqa", "yozing", "bosing", "saqlab", "oling", "tarqating",
    "fikringiz", "savol", "javob", "jonli", "efir", "stories", "post",
    "birinchi", "oxirgi", "yagona", "mukammal", "haqiqiy", "original", "poddelka",
    "soxta", "toza", "sifatli", "ajoyib", "chiroyli", "mashhur", "professional",
    "aqlli", "tez", "oson", "qulay", "ishonchli", "xavfsiz", "muammo", "qaror",
    "xato", "to'g'ri", "noto'g'ri", "sabab", "natija", "rekord", "tarixiy",
    "ish", "biznes", "loyiha", "startap", "kasb", "mutaxassis", "ustoz",
    "shogird", "o'quvchi", "talaba", "universitet", "maktab", "kurs", "dars",
    "ta'lim", "ishchi", "vakansiya", "oylik", "maosh", "karyera", "rivojlanish",
    "muvaffaqiyat", "maqsad", "reja", "strategiya", "taktika", "maslahat", "tavsiya"
}

ANIMATION_STYLES = {
    "smooth_tracking": "✨ Smooth Tracking + Fade Out",
    "mrbeast_style": "🟢 MrBeast Pop-up",
}

COLOR_OPTIONS = {
    "white": {"label": "⚪ Oq (Standart)", "bgr": "&H00FFFFFF&"},
    "yellow": {"label": "🟡 Sariq", "bgr": "&H0000FFFF&"},
    "green": {"label": "🟢 MrBeast Yashil", "bgr": "&H0032FF00&"},
    "cyan": {"label": "🔵 Moviy / Cyan", "bgr": "&H00FFFF00&"},
    "pink": {"label": "🌸 Pushti / Qizil", "bgr": "&H005020FF&"},
}
DEFAULT_COLOR_KEY = "white"

ACTIVE_SPOKEN_COLOR = "&H0000FFFF&"
HEADLIGHT_COLOR = "&H0032FF00&"

FONT_SIZES = {
    "small": ("🔽 Kichik (70)", 70),
    "normal": ("📱 Normal (85)", 85),
    "large": ("📈 Katta (100)", 100),
    "xlarge": ("🔥 Juda katta (115)", 115),
}

MONTSERRAT_SPACING = -0.02

# 🟢 Repozitariydagi barcha shriftlar ro'yxati (fonts papkasi va asosiy papka tekshiriladi)
FONT_OPTIONS = {
    "the_bold": {"label": "🅱 The Bold", "family": "The Bold Font", "tokens": ("thebold",), "bold_ok": False, "tight": False},
    "komika": {"label": "🟢 Komika Axis", "family": "Komika Axis", "tokens": ("komika",), "bold_ok": True, "tight": False},
    "coolvetica": {"label": "🔵 Coolvetica", "family": "Coolvetica", "tokens": ("coolvetica",), "bold_ok": False, "tight": False},
    "bangers": {"label": "💥 Bangers", "family": "Bangers", "tokens": ("bangers",), "bold_ok": False, "tight": False},
    "arial_bold": {"label": "⚫ Arial Bold", "family": "Arial Bold", "tokens": ("arial", "bold"), "bold_ok": True, "tight": False},
}
DEFAULT_FONT_KEY = "the_bold"

LANG_OPTIONS = {
    "uzb": ("🇺🇿 O'zbekcha", "uzb"),
    "rus": ("🇷🇺 Ruscha", "rus"),
    "eng": ("🇬🇧 Inglizcha", "eng"),
    "auto": ("🌐 Avto aniqlash", None),
}

TARIFFS = [
    {"emoji": "🥈", "name": "1 OYLIK PRO", "price": "49 000 so'm"},
    {"emoji": "👑", "name": "VIP UMRBOD", "price": "149 000 so'm"},
]

router = Router()
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

PROCESSING: set = set()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="⚡ Auto Subtitr qo'yish")],
        [KeyboardButton(text="🎨 Subtitr uslublari"), KeyboardButton(text="💳 Balans")],
        [KeyboardButton(text="💎 PRO Tariflar"), KeyboardButton(text="📜 Oferta")],
        [KeyboardButton(text="👨‍💻 Admin bilan bog'lanish")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


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
                color_key TEXT,
                created REAL,
                lang TEXT
            )
            """
        )
        for col in ["lang TEXT", "color_key TEXT"]:
            try:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
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
        return int(row[0])


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


_SESSION_COLS = {"anim_style", "font_key", "font_size", "color_key", "lang"}


def db_save_session(user_id: int, sid: str, file_id: str, video_path: str, dir_path: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (user_id, sid, file_id, video_path, dir_path, anim_style, font_key, font_size, color_key, created, lang) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, sid, file_id, video_path, dir_path, "smooth_tracking", DEFAULT_FONT_KEY, 85, DEFAULT_COLOR_KEY, time.time(), "uzb"),
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


def cleanup_stale_sessions(max_age_sec: int = 72 * 3600):
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
            if d.is_dir() and d.resolve() not in alive and now - d.stat().st_mtime > 14400:
                shutil.rmtree(d, ignore_errors=True)


async def check_subscription(bot: Bot, user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        log.error(f"Obunani tekshirishda xatolik: {e}")
        return False


def format_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_ass_time(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    h, rem = divmod(total_cs, 360_000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _get(obj: Any, *names: str, default: Any = None) -> Any:
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
_EVENT_TAG = re.compile(r"^[\(\[\*<].*[\)\]\*>]$")

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ж": "j", "z": "z", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e",
    "ю": "yu", "я": "ya", "ё": "yo", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}
_CYR_VOWELS = set("аеиоуўэюяё")


def uz_cyr_to_latin(text: str) -> str:
    if not re.search(r"[\u0400-\u04FF]", text):
        return text
    out = []
    prev = ""
    for ch in text:
        low = ch.lower()
        if low == "е":
            lat = "ye" if (not prev or prev.lower() in _CYR_VOWELS or not prev.isalpha() or prev in "ъЪ") else "e"
        elif low in _CYR:
            lat = _CYR[low]
        else:
            lat = ch
            out.append(lat)
            prev = ch
            continue
        out.append(lat.capitalize() if ch.isupper() and lat else lat)
        prev = ch
    res = "".join(out)
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        res = res.upper()
    return res


def clean_text(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    text = raw.replace("\\N", " ").replace("\\n", " ")
    text = re.sub(r"[{}\\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or _EVENT_TAG.match(text) or not _HAS_ALNUM.search(text):
        return ""
    return text


def extract_clean_words(transcript: Any, lang: Optional[str] = None) -> List[Dict[str, Any]]:
    raw_words = _get(transcript, "words", default=[]) or []
    result: List[Dict[str, Any]] = []

    for w in raw_words:
        w_type = _get(w, "type")
        if w_type is not None and str(w_type).lower() != "word":
            continue

        text = clean_text(_get(w, "text", "word"))
        if not text:
            continue
            
        if lang == "uzb":
            text = uz_cyr_to_latin(text)

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


def group_into_chunks(words: List[Dict[str, Any]], max_words: int = 3, max_gap: float = 0.65, max_chars: int = 20) -> List[List[Dict[str, Any]]]:
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
    opt = FONT_OPTIONS.get(key)
    if not opt:
        return None
    # fonts papkasi va asosiy papkani tekshiramiz
    search_dirs = (FONTS_DIR, Path(".").resolve())
    for folder in search_dirs:
        if not folder.exists():
            continue
        for f in sorted(folder.iterdir()):
            n = _norm(f.stem)
            if f.suffix.lower() in (".ttf", ".otf") and "italic" not in n and all(t in n for t in opt["tokens"]):
                return f.resolve()
    return None


def read_font_family(path: Path) -> Optional[str]:
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
    opt = FONT_OPTIONS.get(key)
    if opt:
        f = find_font_file(key)
        if f:
            return read_font_family(f) or opt["family"], opt["bold_ok"], False, f
    return "Arial", True, False, None


def available_fonts() -> List[str]:
    return [k for k in FONT_OPTIONS if find_font_file(k)]


async def ensure_fonts():
    FONTS_DIR.mkdir(parents=True, exist_ok=True)


def _format_word(word_text: str, state: str, anim_style: str, chosen_color: str, bold_ok: bool = True) -> str:
    b1, b0 = ("\\b1", "\\b0") if bold_ok else ("", "")
    clean_w = re.sub(r"[^\w]", "", word_text.lower())
    is_headlight = clean_w in HEADLIGHT_WORDS

    if state == "future":
        return f"{{\\c{chosen_color}\\fscx100\\fscy100{b0}}}{word_text}"

    if state == "past":
        color = HEADLIGHT_COLOR if is_headlight else chosen_color
        return f"{{\\c{color}\\fscx100\\fscy100{b1 if is_headlight else b0}}}{word_text}"

    active_color = HEADLIGHT_COLOR if is_headlight else ACTIVE_SPOKEN_COLOR

    if anim_style == "mrbeast_style":
        return (f"{{\\c{active_color}{b1}\\t(0,60,\\fscx120\\fscy120)\\t(60,130,\\fscx112\\fscy112)}}"
                f"{word_text}{{\\fscx112\\fscy112}}")

    return f"{{\\c{active_color}\\fscx112\\fscy112{b1}}}{word_text}{{\\fscx100\\fscy100{b0}}}"


def scaled_font_size(font_size: int, video_w: int, video_h: int) -> int:
    return max(24, int(round(font_size * min(video_w, video_h) / 1080)))


def max_chars_for(font_size: int, video_w: int, video_h: int) -> int:
    fs = scaled_font_size(font_size, video_w, video_h)
    avail = video_w - 2 * 40
    return int(max(8, min(24, avail / (fs * 0.62) - 1)))


def generate_word_by_word_ass(
    chunks: List[List[Dict[str, Any]]],
    ass_path: Path,
    anim_style: str,
    font_size: int,
    video_w: int,
    video_h: int,
    font_key: str = DEFAULT_FONT_KEY,
    color_key: str = DEFAULT_COLOR_KEY,
) -> int:
    font_name, bold_ok, _, _ = resolve_font(font_key)
    font_size = scaled_font_size(font_size, video_w, video_h)
    base_sp = 0.0
    bold_flag = -1 if bold_ok else 0
    chosen_color = COLOR_OPTIONS.get(color_key, COLOR_OPTIONS["white"])["bgr"]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{chosen_color},&H000000FF,&H00000000,&H80000000,{bold_flag},0,0,0,100,100,{base_sp},0,1,3.5,1.5,2,40,40,{int(video_h * 0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues: List[str] = []

    for chunk in chunks:
        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]
        total_dur_ms = max(250, int((chunk_end - chunk_start) * 1000))

        for i, current_word in enumerate(chunk):
            start = current_word["start"]
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else current_word["end"]
            if end <= start:
                end = start + 0.1

            word_parts = []
            for j, w in enumerate(chunk):
                if j < i:
                    state = "past"
                elif j == i:
                    state = "active"
                else:
                    state = "future"

                word_parts.append(_format_word(w["text"], state, anim_style, chosen_color, bold_ok))

            text = " ".join(word_parts)

            if anim_style == "smooth_tracking":
                dur_part = max(10, int((end - start) * 1000))
                anim_prefix = ""
                if i == len(chunk) - 1:
                    fade_time = min(150, max(50, int(dur_part * 0.4)))
                    anim_prefix = f"{{\\fad(0,{fade_time})}}"
                text = anim_prefix + text

            dialogues.append(
                f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},Default,,0,0,0,,{text}"
            )

    ass_path.write_text(header + "\n".join(dialogues) + "\n", encoding="utf-8")
    return len(dialogues)


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
        [FFMPEG_PATH, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)]
    )
    if code != 0:
        log.error(f"Audio ajratishda xato: {err[-800:]}")
        raise RuntimeError("Videodan audio ajratib bo'lmadi.")


def _escape_ass_filter_path(p: Path) -> str:
    s = str(p.resolve()).replace("\\", "/")
    s = s.replace(":", "\\:").replace("'", "\\'")
    return s


async def burn_subtitles_to_video(input_video: Path, ass_file: Path, output_video: Path, font_key: str = DEFAULT_FONT_KEY):
    escaped_ass = _escape_ass_filter_path(ass_file)
    vf = f"subtitles='{escaped_ass}'"
    font_file = resolve_font(font_key)[3]
    if font_file:
        escaped_font_dir = _escape_ass_filter_path(font_file.parent)
        vf += f":fontsdir='{escaped_font_dir}'"

    cmd = [
        FFMPEG_PATH, "-y",
        "-i", str(input_video.resolve()),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_video.resolve()),
    ]
    code, err = await _run(cmd)
    if code != 0:
        log.error(f"FFmpeg xatosi: {err[-1500:]}")
        raise RuntimeError("Videoga subtitr yopishtirishda xatolik yuz berdi.")


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
    args = message.text.strip().split()
    if len(args) == 2:
        val = args[1].lower()
        target = message.from_user.id
        if val == "pro":
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target,))
                conn.commit()
            await message.answer(f"Balansingiz PRO statusga o'tkazildi.")
            return
        elif val.isdigit():
            amount = int(val)
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, target))
                conn.commit()
            await message.answer(f"Balansingizga {amount} ta video qo'shildi.")
            return

    if len(args) >= 3:
        try:
            target = int(args[1])
            val = args[2].lower()
            if val == "pro":
                with sqlite3.connect(DB_FILE) as conn:
                    conn.execute("UPDATE users SET is_pro = 1 WHERE user_id = ?", (target,))
                    conn.commit()
                await message.answer(f"Foydalanuvchi ({target}) PRO statusga o'tkazildi.")
                return
            else:
                amount = int(val)
                with sqlite3.connect(DB_FILE) as conn:
                    conn.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, target))
                    conn.commit()
                await message.answer(f"Foydalanuvchi ({target}) balansiga {amount} ta video qo'shildi.")
                return
        except Exception as e:
            await message.answer(f"Xatolik: {escape(str(e))}")
            return

    await message.answer("Ishlatish:\n• /add [miqdor]\n• /add [user_id] [miqdor]\n• /add [user_id] pro")


@router.message(Command("pro"))
async def cmd_set_pro(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.strip().split()
    target = int(args[1]) if len(args) >= 2 and args[1].isdigit() else message.from_user.id
    try:
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
async def cmd_auto_subtitles(message: Message, bot: Bot):
    user_id = message.from_user.id
    if REQUIRED_CHANNEL and not await check_subscription(bot, user_id):
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"))
        builder.row(InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub"))
        await message.answer(f"Botdan foydalanish uchun avval kanalga obuna bo'ling:\n{REQUIRED_CHANNEL}", reply_markup=builder.as_markup())
        return

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
    if REQUIRED_CHANNEL and not await check_subscription(bot, user_id):
        return

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
        await message.answer("❌ Videoni yuklab olib bo'lmadi.")
        return

    db_save_session(user_id, sid, message.video.file_id, str(input_video), str(user_dir))

    builder = InlineKeyboardBuilder()
    for key, (name, _) in LANG_OPTIONS.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"lang:{key}:{sid}"))
    await message.reply(
        "✨ Videongiz qabul qilindi!\n\n🗣 Videodagi <b>nutq tilini</b> tanlang:",
        reply_markup=builder.as_markup(),
    )


async def load_session(callback: CallbackQuery, bot: Bot, sid: str) -> Optional[Dict[str, Any]]:
    user_id = callback.from_user.id
    sess = db_get_session(user_id)
    
    if not sess:
        await callback.answer("⏳ Sessiya yangilanmoqda...", show_alert=False)
        return None

    video = Path(sess["video_path"])
    if not video.exists():
        try:
            video.parent.mkdir(parents=True, exist_ok=True)
            file_info = await bot.get_file(sess["file_id"])
            await bot.download_file(file_info.file_path, destination=video)
        except Exception as e:
            log.error(f"Videoni qayta yuklab bo'lmadi: {e}")
            await callback.answer("Videoni qaytadan yuboring.", show_alert=True)
            return None
    return sess


def _parse_cb(data: str) -> Optional[Tuple[str, str]]:
    parts = data.split(":", 2)
    return (parts[1], parts[2]) if len(parts) == 3 else None


@router.callback_query(F.data.startswith("lang:"))
async def callback_language(callback: CallbackQuery, bot: Bot):
    parsed = _parse_cb(callback.data)
    if not parsed or parsed[0] not in LANG_OPTIONS:
        await callback.answer()
        return
    lang_key, sid = parsed
    sess = await load_session(callback, bot, sid)
    if not sess:
        return
    db_update_session(callback.from_user.id, lang=lang_key)

    builder = InlineKeyboardBuilder()
    for key, name in ANIMATION_STYLES.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"anim:{key}:{sid}"))
    await callback.message.edit_text("🎬 Subtitr uchun <b>animatsiya uslubini</b> tanlang:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("anim:"))
async def callback_anim_style(callback: CallbackQuery, bot: Bot):
    parsed = _parse_cb(callback.data)
    if not parsed or parsed[0] not in ANIMATION_STYLES:
        await callback.answer()
        return
    style_key, sid = parsed
    sess = await load_session(callback, bot, sid)
    if not sess:
        return
    db_update_session(callback.from_user.id, anim_style=style_key)

    builder = InlineKeyboardBuilder()
    for c_key, c_info in COLOR_OPTIONS.items():
        builder.row(InlineKeyboardButton(text=c_info["label"], callback_data=f"color:{c_key}:{sid}"))
    await callback.message.edit_text("🎨 Asosiy matn <b>rangini</b> tanlang (aytilayotgan so'z sariq bo'ladi):", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("color:"))
async def callback_color(callback: CallbackQuery, bot: Bot):
    parsed = _parse_cb(callback.data)
    if not parsed or parsed[0] not in COLOR_OPTIONS:
        await callback.answer()
        return
    color_key, sid = parsed
    sess = await load_session(callback, bot, sid)
    if not sess:
        return
    db_update_session(callback.from_user.id, color_key=color_key)

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
        await callback.answer()
        return
    key, sid = parsed
    sess = await load_session(callback, bot, sid)
    if not sess:
        return
    db_update_session(callback.from_user.id, font_key=key)

    builder = InlineKeyboardBuilder()
    for skey, (name, _) in FONT_SIZES.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"size:{skey}:{sid}"))
    await callback.message.edit_text("📱 Subtitr <b>o'lchamini</b> tanlang:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("size:"))
async def callback_font_size(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    parsed = _parse_cb(callback.data)
    if not parsed or parsed[0] not in FONT_SIZES:
        await callback.answer()
        return
    size_key, sid = parsed

    if user_id in PROCESSING:
        await callback.answer("Video tayyorlanmoqda, iltimos kuting...", show_alert=True)
        return

    session = await load_session(callback, bot, sid)
    if not session:
        return

    user_credits = get_user_credits(user_id, username)
    user_is_pro = is_user_pro(user_id)
    if user_credits < 1 and not user_is_pro:
        await callback.answer(NO_CREDITS_TEXT, show_alert=True)
        return

    PROCESSING.add(user_id)
    await callback.answer()

    font_size = FONT_SIZES[size_key][1]
    font_key = session.get("font_key") or DEFAULT_FONT_KEY
    anim_style = session.get("anim_style") or "smooth_tracking"
    color_key = session.get("color_key") or DEFAULT_COLOR_KEY
    lang_key = session.get("lang") or "uzb"
    lang_code = LANG_OPTIONS.get(lang_key, LANG_OPTIONS["uzb"])[1]

    input_video = Path(session["video_path"])
    user_dir = Path(session["dir_path"])
    output_video = user_dir / "output.mp4"
    audio_path = user_dir / "audio.wav"
    ass_path = user_dir / "subs.ass"
    srt_path = user_dir / "subs.srt"

    status_msg = await callback.message.edit_text("✨ Subtitrlar tayyorlanmoqda, iltimos kuting...")

    try:
        v_width, v_height = await get_video_resolution(input_video)
        await extract_audio(input_video, audio_path)

        def _transcribe():
            last_err: Optional[Exception] = None
            for model in dict.fromkeys([STT_MODEL, "scribe_v1"]):
                try:
                    kwargs: Dict[str, Any] = dict(model_id=model, tag_audio_events=False, timestamps_granularity="word")
                    if lang_code:
                        kwargs["language_code"] = lang_code
                    with open(audio_path, "rb") as f:
                        return el_client.speech_to_text.convert(file=f, **kwargs)
                except Exception as e:
                    last_err = e
                    log.warning(f"STT {model} xatosi: {e}")
            raise last_err

        transcript = await asyncio.to_thread(_transcribe)

        words = extract_clean_words(transcript, lang_code)
        if not words:
            await status_msg.edit_text("❌ Videodan ovoz topilmadi yoki matnga o'girib bo'lmadi.")
            return

        chunks = group_into_chunks(words, max_words=3, max_chars=max_chars_for(font_size, v_width, v_height))
        write_srt(chunks, srt_path)
        generate_word_by_word_ass(chunks, ass_path, anim_style, font_size, v_width, v_height, font_key, color_key)

        await burn_subtitles_to_video(input_video, ass_path, output_video, font_key)

        if not user_is_pro:
            deduct_user_credit(user_id)
        remaining = get_user_credits(user_id, username)

        await bot.send_video(
            chat_id=user_id,
            video=FSInputFile(output_video),
            width=v_width,
            height=v_height,
            supports_streaming=True,
            caption=f"🔥 Subtitr Tayyor!\n\n💳 Qolgan balans: {remaining if not user_is_pro else '♾ Cheksiz'} ta video",
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
    text = (
        "🎬 <b>SUBTITR USLUBLARI:</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "✨ <b>Smooth Tracking + Fade Out</b>\n"
        "Matn ekranda qotmasdan silliq yoyilib boradi va fraza oxirida erib yo'qoladi.\n\n"
        "🟢 <b>MrBeast Pop-up</b>\n"
        "Aytilayotgan so'z elastik tarzda sakrab kattalashadi va sariq rangda yonadi.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<i>Video yuborganingizdan so'ng uslub va rangni tanlashingiz mumkin.</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard())


def admin_url(text: str = "") -> str:
    base = f"https://t.me/{ADMIN_USERNAME}"
    return base + (f"?text={quote(text)}" if text else "")


LINE = "━━━━━━━━━━━━━━━━"


def pro_text() -> str:
    tariffs = "\n".join(f"{t['emoji']} <b>{escape(t['name'])}</b> — <b>{escape(t['price'])}</b>" for t in TARIFFS)
    return (
        f"💎 <b>AVTO SUBTITR — PRO TARIFLAR</b>\n{LINE}\n\n"
        "✅ Cheklovsiz videolar\n"
        "✅ 2K Ultra HD sifat va mukammal shriftlar\n"
        "✅ Barcha premium animatsiyalar\n"
        "✅ Tezkor ishlov berish\n\n"
        f"{LINE}\n{tariffs}\n{LINE}\n\n"
        f"💳 <b>To'lov uchun karta</b> (bosib nusxalang):\n<code>{CARD_NUMBER}</code>\n"
        f"👤 {escape(CARD_HOLDER)}\n\n"
        "📨 To'lovdan so'ng chekni adminga yuboring — PRO shu zahoti yoqiladi."
    )


def pro_keyboard(user_id: int):
    b = InlineKeyboardBuilder()
    for t in TARIFFS:
        b.row(InlineKeyboardButton(
            text=f"{t['emoji']} {t['name']} — {t['price']}",
            url=admin_url(f"Salom! {t['name']} tarifini olmoqchiman. Mening ID: {user_id}"),
        ))
    if CopyTextButton is not None:
        b.row(InlineKeyboardButton(text="📋 Karta raqamini nusxalash", copy_text=CopyTextButton(text=CARD_NUMBER)))
    b.row(InlineKeyboardButton(text="👨‍💻 Adminga chek yuborish", url=admin_url(f"Salom! To'lov qildim. Mening ID: {user_id}")))
    return b.as_markup()


@router.message(F.text == "💳 Balans")
async def cmd_balance(message: Message):
    user_id = message.from_user.id
    credits = get_user_credits(user_id, message.from_user.username or "")
    pro = is_user_pro(user_id)
    status = "👑 PRO (cheksiz)" if pro else "🆓 Standard (bepul)"
    left = "♾ Cheksiz" if pro else f"{credits} ta video"
    text = (
        f"💳 <b>SIZNING BALANSINGIZ</b>\n{LINE}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🎬 Qolgan videolar: <b>{left}</b>\n"
        f"⭐ Status: <b>{status}</b>\n{LINE}"
    )
    b = InlineKeyboardBuilder()
    if not pro:
        b.row(InlineKeyboardButton(text="💎 PRO tarifga o'tish", callback_data="pro_info"))
    b.row(InlineKeyboardButton(text="👨‍💻 Admin bilan bog'lanish", url=admin_url()))
    await message.answer(text, reply_markup=b.as_markup())


@router.callback_query(F.data == "pro_info")
async def callback_pro_info(callback: CallbackQuery):
    await callback.message.answer(pro_text(), reply_markup=pro_keyboard(callback.from_user.id))
    await callback.answer()


@router.message(F.text == "💎 PRO Tariflar")
async def cmd_pro_tariffs(message: Message):
    await message.answer(pro_text(), reply_markup=pro_keyboard(message.from_user.id))


@router.message(F.text == "📜 Oferta")
async def cmd_terms(message: Message):
    await message.answer(
        "Foydalanish shartlari va Ommaviy Oferta:\n\n"
        "1. Umumiy qoidalar:\n"
        "Ushbu shartnoma Auto Subtitles boti orqali taqdim etiladigan xizmatlardan foydalanish qoidalarini belgilaydi.\n\n"
        "2. Xizmatlar mazmuni:\n"
        "Bot foydalanuvchilar tomonidan yuborilgan videolarga sun'iy intellekt yordamida avtomatik subtitrlar qo'shib beradi.\n\n"
        "3. To'lovlar va tariflar:\n"
        "Xizmatlar pullik va bepul asosda taqdim etiladi.\n\n"
        "4. Foydalanuvchi mas'uliyati:\n"
        "Foydalanuvchi yuklayotgan videolari qonunchilikka zid kelmasligini kafolatlaydi.",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.text == "👨‍💻 Admin bilan bog'lanish")
async def cmd_contact_admin(message: Message):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💬 Telegram'da yozish", url=admin_url(f"Salom! Yordam kerak. Mening ID: {message.from_user.id}")))
    await message.answer(
        f"👨‍💻 <b>TEXNIK YORDAM VA ADMIN</b>\n{LINE}\n"
        f"💬 Telegram: @{ADMIN_USERNAME}\n"
        f"📞 Telefon: <code>{ADMIN_PHONE}</code>\n{LINE}\n"
        "Savol, to'lov yoki muammo bo'lsa — yozing, tez javob beramiz.",
        reply_markup=b.as_markup(),
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
