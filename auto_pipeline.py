"""خط أنابيب قانوني: Gutenberg (ملكية عامة) → تحميل ملف → إرسال لقناتك → فهرسة في DB.

يعمل بجانب البوت (البوت يبقى شغالاً). يحترم سياسة Gutenberg (مهلة بين الطلبات).
يتوقف بأمان بـ Ctrl+C ويستأنف من ملف الحالة.

مثال:
  venv/Scripts/python.exe auto_pipeline.py --query philosophy --limit 5 --target @mychannel --dry-run
  venv/Scripts/python.exe auto_pipeline.py --query philosophy --limit 20 --target @mychannel --delay 5 --max-mb 15

الشروط: البوت مشرف في القناة الهدف، و LIB_CHANNEL مضبوط (يُنشر تلقائياً أيضاً عند الرفع اليدوي).
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from aiogram import Bot
from aiogram.types import FSInputFile

import aiohttp

import config
import database as db
from internet_search import HEADERS

STATE = "pipeline_state.json"
TMPDIR = "pipeline_dl"


def load_state() -> set:
    try:
        return set(json.load(open(STATE, encoding="utf-8")))
    except Exception:
        return set()


def save_state(done: set):
    json.dump(sorted(done), open(STATE, "w", encoding="utf-8"))


async def gutendex_page(session: aiohttp.ClientSession, query: str, page: int):
    params = {"search": query, "page": page} if query else {"page": page}
    async with session.get("https://gutendex.com/books/", params=params,
                           timeout=aiohttp.ClientTimeout(total=25)) as r:
        if r.status != 200:
            return []
        return (await r.json()).get("results", [])


def pick_file(g: dict, max_mb: float):
    """يفضل EPUB صغيراً ثم TXT. يعيد (url, ftype) أو (None, '')."""
    fmts = g.get("formats", {}) or {}
    for mime, ftype in (("application/epub+zip", "epub"),
                        ("text/plain", "txt"),
                        ("application/pdf", "pdf")):
        u = fmts.get(mime)
        if u:
            return u, ftype
    return None, ""


async def download_capped(session: aiohttp.ClientSession, url: str, dest: str, max_bytes: int) -> int:
    """تحميل بحد أقصى. يعيد الحجم أو -1 عند التجاوز/الفشل."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as r:
            if r.status != 200:
                return -1
            size = 0
            with open(dest, "wb") as f:
                async for chunk in r.content.iter_chunked(64 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        break
                    f.write(chunk)
            if size > max_bytes:
                try:
                    os.remove(dest)
                except OSError:
                    pass
                return -1
            return size
    except Exception as e:
        print(f"[X] download: {e!r}")
        return -1


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--target", default="", help="قناة/شات الهدف مثل @mychannel (مطلوب إلا مع --dry-run)")
    ap.add_argument("--category", default="عام")
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--max-mb", type=float, default=15.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not config.BOT_TOKEN or "1234" in config.BOT_TOKEN:
        print("ضع BOT_TOKEN الحقيقي في .env أولاً")
        return
    if not a.dry_run and not a.target:
        print("حدد --target (القناة) أو استخدم --dry-run للمعاينة")
        return

    await db.init_db()
    os.makedirs(TMPDIR, exist_ok=True)
    done = load_state()
    bot = Bot(token=config.BOT_TOKEN)
    max_bytes = int(a.max_mb * 1024 * 1024)
    added = skipped = 0

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            page = 1
            while added < a.limit:
                books = await gutendex_page(s, a.query, page)
                if not books:
                    break
                for g in books:
                    if added >= a.limit:
                        break
                    gid = str(g.get("id"))
                    if gid in done:
                        continue
                    url, ftype = pick_file(g, a.max_mb)
                    if not url:
                        continue
                    title = (g.get("title") or "بدون عنوان")[:150]
                    if a.dry_run:
                        print(f" - {title} | {url}")
                        added += 1
                        continue
                    authors = ", ".join(x.get("name", "") for x in g.get("authors", []))[:100] or "غير معروف"
                    if await db.find_by_source(url):
                        done.add(gid)
                        skipped += 1
                        continue
                    dest = os.path.join(TMPDIR, f"{gid}.{ftype}")
                    size = await download_capped(s, url, dest, max_bytes)
                    if size < 0:
                        print(f" - تخطي (كبير/فشل): {title}")
                        continue
                    try:
                        msg = await bot.send_document(
                            a.target, FSInputFile(dest),
                            caption=f"📖 {title} — {authors}"[:1000])
                        fid = msg.document.file_id
                        uniq = msg.document.file_unique_id or ""
                    except Exception as e:
                        print(f"[X] send: {e!r} — تأكد أن البوت مشرف في {a.target}")
                        break
                    langs = g.get("languages", ["en"])
                    lang = langs[0] if langs else "en"
                    if lang not in ("ar", "en"):
                        lang = "en"
                    bid = await db.add_book(title, authors, a.category, "", fid, ftype,
                                            os.path.basename(dest), size, lang, None,
                                            file_unique_id=uniq, source_url=url)
                    done.add(gid)
                    save_state(done)
                    added += 1
                    print(f" + #{bid}: {title}")
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                    time.sleep(a.delay)
                page += 1
                time.sleep(a.delay)
    finally:
        await bot.session.close()
        save_state(done)
    print(f"OK: added={added} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
