"""إثراء البيانات الوصفية من مصادر مفتوحة: OpenLibrary + Google Books + Gutendex."""
import aiohttp

HEADERS = {"User-Agent": "Telegram-Library-Bot/4.0"}

async def _get(session, url, params):
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=12)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None

async def enrich(title: str = "", author: str = "", isbn: str = "") -> dict:
    """يعيد قاموساً بالحقول: isbn,publisher,year,pages,cover_url,tags,description."""
    out: dict = {}
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        if isbn:
            clean = "".join(ch for ch in isbn if ch.isdigit() or ch.lower() == "x")
            d = await _get(s, f"https://openlibrary.org/isbn/{clean}.json", {})
            if d:
                out["title"] = d.get("title", "")
                out["publisher"] = ", ".join(d.get("publishers", [])[:2])
                if d.get("covers"):
                    out["cover_url"] = f"https://covers.openlibrary.org/b/id/{d['covers'][0]}-L.jpg"
        if not out:
            q = " ".join(x for x in [title, author] if x)[:120] or isbn
            d = await _get(s, "https://openlibrary.org/search.json",
                           {"q": q, "limit": 1, "fields": "title,author_name,publisher,first_publish_year,isbn,cover_i,subject"})
            docs = (d or {}).get("docs", [])
            if docs:
                b = docs[0]
                out = {
                    "title": b.get("title", ""),
                    "publisher": ", ".join(b.get("publisher", [])[:1]),
                    "year": b.get("first_publish_year"),
                    "isbn": (b.get("isbn", [""])[0] if b.get("isbn") else ""),
                    "tags": ", ".join(b.get("subject", [])[:5]),
                }
                if b.get("cover_i"):
                    out["cover_url"] = f"https://covers.openlibrary.org/b/id/{b['cover_i']}-L.jpg"
        # Google Books كمصدر ثانٍ للصفحات والوصف
        if title or isbn:
            g = await _get(s, "https://www.googleapis.com/books/v1/volumes",
                           {"q": f"isbn:{isbn}" if isbn else f"intitle:{title} inauthor:{author}", "maxResults": 1})
            items = (g or {}).get("items", [])
            if items:
                info = items[0].get("volumeInfo", {})
                out.setdefault("pages", info.get("pageCount", 0) or 0)
                out.setdefault("publisher", info.get("publisher", ""))
                out.setdefault("description", (info.get("description", "") or "")[:800])
                img = (info.get("imageLinks", {}) or {}).get("thumbnail", "")
                out.setdefault("cover_url", img)
                if not out.get("year") and info.get("publishedDate", "")[:4].isdigit():
                    out["year"] = int(info["publishedDate"][:4])
    # تنظيف
    for k in ("pages", "year"):
        try:
            out[k] = int(out.get(k) or 0) or None
        except (TypeError, ValueError):
            out[k] = None
    return {k: v for k, v in out.items() if v}
