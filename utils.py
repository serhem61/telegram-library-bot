import html
import re
import time
from config import MAX_FILE_MB

_last: dict[int, float] = {}

ALLOWED_EXT = {"pdf": "pdf", "epub": "epub", "txt": "txt", "mobi": "mobi"}

def esc(s: str | None) -> str:
    return html.escape(str(s or ""), quote=False)

def chunk(text: str, size: int = 4000) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]

def flood_ok(user_id: int, seconds: float = 1.2) -> bool:
    now = time.time()
    if now - _last.get(user_id, 0) < seconds:
        return False
    _last[user_id] = now
    return True

def book_text(b: dict) -> str:
    cat = b.get("category") or "عام"
    lines = [
        f"📖 <b>{esc(b.get('title'))}</b>",
        f"✍️ {esc(b.get('author'))}",
        f"📂 {esc(cat)} | 🌍 {esc(b.get('lang'))} | ⬇️ {b.get('downloads', 0)}",
    ]
    meta = []
    if b.get("publisher"):
        meta.append(f"🏛 {esc(b['publisher'])}")
    if b.get("year"):
        meta.append(f"📅 {b['year']}")
    if b.get("pages"):
        meta.append(f"📄 {b['pages']} ص")
    if b.get("isbn"):
        meta.append(f"🔖 <code>{esc(b['isbn'])}</code>")
    if meta:
        lines.append(" | ".join(meta))
    if b.get("rating_cnt"):
        lines.append(f"⭐ {b.get('rating_avg', 0)} ({b.get('rating_cnt')} تقييم)")
    if b.get("tags"):
        lines.append(f"🏷 {esc(str(b['tags'])[:120])}")
    if b.get("source_url") and not b.get("file_id"):
        lines.append("🌐 نسخة خارجية برابط مجاني (زر التحميل يرسل الرابط)")
    desc = esc((b.get("description") or "")[:500])
    if desc:
        lines += ["", desc]
    return "\n".join(lines)

def net_text(query: str, results: list[dict]) -> str:
    t = f"🌐 <b>نتائج «{esc(query)}» (مصادر مجانية):</b>\n\n"
    for i, r in enumerate(results, 1):
        t += (f"{i}. 📖 <b>{esc(r['title'])}</b>\n"
              f"   ✍️ {esc(r['author'])} | 🏷 {esc(r['source'])}\n"
              f"   🔗 <a href=\"{esc(r['link'])}\">تحميل / قراءة</a>\n\n")
    t += "⚖️ مصادر ملكية عامة ومجانية فقط."
    return t

def validate_file(file_name: str, mime: str, size: int):
    """تحقق صارم من الصيغة والحجم. يعيد (ok, ftype, err)."""
    ext = (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""
    ftype = ALLOWED_EXT.get(ext, "")
    if not ftype:
        if (mime or "").find("pdf") >= 0:
            ftype = "pdf"
        else:
            return False, "", "⚠️ الصيغ المقبولة: PDF / EPUB / TXT / MOBI فقط."
    if (size or 0) / 1024 / 1024 > MAX_FILE_MB:
        return False, "", f"⚠️ الحجم يتجاوز {MAX_FILE_MB}MB."
    return True, ftype, ""

_AR_STOP = {"من","في","على","إلى","عن","أن","إن","مع","ما","لا","لم","لن","قد","هذا","هذه","ذلك","التي","الذي","الذين","بين","بعد","قبل","عند","غير","كل","كما","ثم","أو","و","هو","هي","كان","كانت","يكون","تكون","لقد","وقد","إذا","لكن","بل","حتى"}

def summarize(text: str, sentences: int = 3) -> str:
    """تلخيص استخراجي محلي (بدون AI خارجي): أول الجمل الأعلى تكراراً للكلمات."""
    text = (text or "").strip()
    if not text:
        return "لا يوجد وصف لتلخيصه."
    parts = re.split(r"(?<=[.!؟?])\s+", text)
    parts = [p.strip() for p in parts if len(p.strip()) > 20][:12]
    if len(parts) <= sentences:
        return "🧾 " + " ".join(parts)[:800]
    freq: dict[str, int] = {}
    for p in parts:
        for w in re.findall(r"[\w\u0600-\u06FF]{3,}", p):
            wl = w.lower()
            if wl not in _AR_STOP:
                freq[wl] = freq.get(wl, 0) + 1
    scored = sorted(parts, key=lambda p: sum(freq.get(w.lower(), 0) for w in re.findall(r"[\w\u0600-\u06FF]{3,}", p)), reverse=True)
    top = sorted(scored[:sentences], key=parts.index)
    return "🧾 " + " ".join(top)[:800]
