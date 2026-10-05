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

FONT_OPTIONS = {
    "the_bold": {"label": "🅱 The Bold", "family": "The Bold Font", "tokens": ("thebold",), "bold_ok": False},
    "komika": {"label": "🟢 Komika Axis", "family": "Komika Axis", "tokens": ("komika",), "bold_ok": True},
    "coolvetica": {"label": "🔵 Coolvetica", "family": "Coolvetica", "tokens": ("coolvetica",), "bold_ok": False},
    "bangers": {"label": "💥 Bangers", "family": "Bangers", "tokens": ("bangers",), "bold_ok": False},
    "arial_bold": {"label": "⚫ Arial Bold", "family": "Arial Bold", "tokens": ("arial", "bold"), "bold_ok": True},
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

    fixed_result = []
    for w in result:
        t = w["text"].replace("‘", "'").replace("’", "'").replace("`", "'")
        if fixed_result and (t.startswith("'") or fixed_result[-1]["text"].lower() in ("ko", "o", "g", "dela")):
            fixed_result[-1]["text"] += t
            fixed_result[-1]["end"] = w["end"]
        else:
            fixed_result.append(w)
    
    for w in fixed_result:
        w["text"] = re.sub(r"([oOgG])\s+'", r"\1'", w["text"])
        w["text"] = re.sub(r"\s+'", "'", w["text"])
        
    return fixed_result


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
    chosen_color = COLOR_OPTIONS.get(color_key, COLOR_OPTIONS["white"])["bgr"]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleMana, barcha xatoliklar to'g'rilangan, o'zbek tilidagi so'zlar orasida joy ochilib qolishi va so'zlar bo'linib ketishi muammosi bartaraf etilgan to'liq va tayyor `bot.py` kodi:

```python
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
    "yellow": {"label": "🟡 Sariq", "bgr":
