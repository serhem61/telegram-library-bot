import asyncio
import logging
import time
import aiohttp

from config import CACHE_TTL

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Telegram-Library-Bot/2.0"}
_cache: dict[str, tuple[float, list]] = {}

def _get_cache(key: str):
    item = _cache.get(key)
    if item and time.time() - item[0] < CACHE_TTL:
        return item[1]
    _cache.pop(key, None)
    return None

def _set_cache(key: str, val: list):
    _cache[key] = (time.time(), val)
    if len(_cache) > 200:
        _cache.pop(next(iter(_cache)))

async def _fetch_json(session: aiohttp.ClientSession, url, params):
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception as e:
        log.warning("fetch fail %s: %s", url, e)
        return None

async def search_openlibrary(session, query: str, limit=4):
    data = await _fetch_json(session, "https://openlibrary.org/search.json",
        {"q": query, "limit": limit, "fields": "key,title,author_name,first_publish_year,cover_i"})
    if not data:
        return []
    out = []
    for d in data.get("docs", [])[:limit]:
        key = d.get("key", "")
        out.append({
            "source": "OpenLibrary", "title": d.get("title", "بدون عنوان") or "بدون عنوان",
            "author": ", ".join(d.get("author_name", [])[:2]) or "غير معروف",
            "year": d.get("first_publish_year", "?") or "?",
            "link": f"https://openlibrary.org{key}" if key else "https://openlibrary.org",
        })
    return out

async def search_gutenberg(session, query: str, limit=4):
    data = await _fetch_json(session, "https://gutendex.com/books/", {"search": query})
    if not data:
        return []
    out = []
    for b in data.get("results", [])[:limit]:
        fmts = b.get("formats", {}) or {}
        dl = fmts.get("application/epub+zip") or fmts.get("text/plain") or fmts.get("application/pdf") or ""
        out.append({
            "source": "Gutenberg", "title": b.get("title", "بدون عنوان") or "بدون عنوان",
            "author": ", ".join(a.get("name", "") for a in b.get("authors", [])) or "غير معروف",
            "year": "?", "link": dl or f"https://www.gutenberg.org/ebooks/{b.get('id')}",
        })
    return out

async def search_archive(session, query: str, limit=4):
    data = await _fetch_json(session, "https://archive.org/advancedsearch.php",
        {"q": f"({query}) AND mediatype:texts", "fl[]": ["identifier", "title", "creator"],
         "rows": limit, "output": "json"})
    if not data:
        return []
    out = []
    for d in data.get("response", {}).get("docs", [])[:limit]:
        ident = d.get("identifier", "")
        if not ident:
            continue
        title = d.get("title", ident)
        if isinstance(title, list):
            title = title[0] if title else ident
        creator = d.get("creator", "غير معروف")
        if isinstance(creator, list):
            creator = ", ".join(creator[:2]) or "غير معروف"
        out.append({
            "source": "Archive.org", "title": str(title)[:120],
            "author": str(creator or "غير معروف")[:80],
            "year": "?", "link": f"https://archive.org/details/{ident}",
        })
    return out

async def internet_search(query: str, limit_per_source: int = 3) -> list[dict]:
    """بحث متوازٍ مع كاش. يعيد حتى 10 نتائج."""
    query = query.strip()
    if not query:
        return []
    key = f"{query.lower()}:{limit_per_source}"
    cached = _get_cache(key)
    if cached is not None:
        return cached
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            res = await asyncio.gather(
                search_openlibrary(session, query, limit_per_source),
                search_gutenberg(session, query, limit_per_source),
                search_archive(session, query, limit_per_source),
            )
    except Exception as e:
        log.warning("internet_search: %s", e)
        return []
    merged: list[dict] = []
    for part in res:
        merged.extend(part or [])
    merged = merged[:10]
    _set_cache(key, merged)
    return merged
