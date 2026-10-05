"""استيراد قانوني بالجملة من مشروع Gutenberg (ملكية عامة) عبر Gutendex.

يخزّن الكتب كسجلات خارجية (رابط تحميل مجاني) بلا رفع ملفات.
مثال (PowerShell):
  venv/Scripts/python.exe bulk_import.py --query philosophy --limit 20 --dry-run

ملاحظة صريحة: هذا ملكية عامة فقط (إنجليزية غالباً). الكتب العربية المحمية
بحقوق النشر لا تُستورد بهذه الأداة.
"""
import argparse
import asyncio
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import database as db
from categorize import classify
from internet_search import HEADERS

import aiohttp

LANG_MAP = {"en": "en", "fr": "en", "de": "en", "es": "en"}
PAGE_SIZE = 32


def pick_link(formats: dict) -> tuple[str, str]:
    fmts = formats or {}
    if fmts.get("application/epub+zip"):
        return fmts["application/epub+zip"], "epub"
    if fmts.get("text/plain"):
        return fmts["text/plain"], "txt"
    if fmts.get("application/pdf"):
        return fmts["application/pdf"], "pdf"
    return "", ""


async def fetch_page(session: aiohttp.ClientSession, query: str, page: int):
    """يعيد (books, ok). ok=False تعني خطأ شبكة (يُعاد المحاولة) لا نهاية الكتالوج."""
    params = {"search": query, "page": page} if query else {"page": page}
    try:
        async with session.get("https://gutendex.com/books/", params=params,
                               timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                print(f"[X] page {page}: HTTP {r.status}")
                return [], False
            data = await r.json()
            return data.get("results", []), True
    except Exception as e:
        print(f"[X] page {page}: {e!r}")
        return [], False


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="", help="كلمة بحث (فارغ = الأحدث)")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--category", default="عام")
    ap.add_argument("--delay", type=float, default=1.5, help="مهلة ثوانٍ بين الصفحات (احتراماً للخادم)")
    ap.add_argument("--start-page", type=int, default=1, help="صفحة البداية (للاستئناف)")
    ap.add_argument("--auto-cat", dest="auto_cat", action="store_true", default=True)
    ap.add_argument("--no-auto-cat", dest="auto_cat", action="store_false",
                    help="تعطيل التصنيف التلقائي واستخدام --category للكل")
    ap.add_argument("--dry-run", action="store_true", help="عرض فقط بلا حفظ")
    a = ap.parse_args()

    await db.init_db()
    added = dup = skipped = 0
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        page = max(1, a.start_page)
        fails = 0
        while added + dup < a.limit:
            books, ok = await fetch_page(s, a.query, page)
            if not ok:
                fails += 1
                wait = min(60 * fails, 300)
                print(f"WAIT {wait}s (fail {fails})", flush=True)
                time.sleep(wait)
                if fails > 8:
                    page += 1  # تجاوز الصفحة العالقة بدل التوقف
                    fails = 0
                continue
            fails = 0
            if not books:
                break
            for g in books:
                if added + dup >= a.limit:
                    break
                link, ftype = pick_link(g.get("formats", {}))
                if not link:
                    skipped += 1
                    continue
                title = (g.get("title") or "بدون عنوان")[:150]
                authors = ", ".join(x.get("name", "") for x in g.get("authors", []))[:100] or "غير معروف"
                langs = g.get("languages", ["en"])
                lang = LANG_MAP.get(langs[0] if langs else "en", "en")
                shelves = g.get("bookshelves", []) or []
                subjects = g.get("subjects", []) or []
                tags = ", ".join([*shelves[:2], *subjects[:4]])[:200]
                category = classify(shelves, subjects) if a.auto_cat else a.category
                if a.dry_run:
                    print(f" - {title} | {authors} | {link}")
                    added += 1
                    continue
                before = await db.find_by_source(link)
                bid = await db.add_book(title, authors, category, "", "", ftype, "", 0,
                                        lang, None, file_unique_id="", source_url=link)
                if before and before["id"] == bid:
                    dup += 1
                else:
                    if tags:
                        await db.update_book_meta(bid, tags=tags)
                    added += 1
            page += 1
            if page % 10 == 0:
                print(f"PAGE {page}: added={added} dup={dup}", flush=True)
            time.sleep(a.delay)
    print(f"OK: added={added} dup={dup} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
