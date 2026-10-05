"""استيراد كتب من مجلد Google Drive عام إلى مكتبتك (تخزين file_id داخلياً).

الطريقة: سرد الملفات عبر Drive API (مفتاح مجاني) → تحميل محلي → إرسال
للقناة عبر البوت → حفظ file_id في قاعدة البيانات. يعمل بجانب البوت.

1) شارك المجلد: "Anyone with the link - Viewer" وانسخ ID من الرابط:
     https://drive.google.com/drive/folders/XXXX  →  XXXX هو ID
2) مفتاح مجاني: Google Cloud Console ← New Project ← Enable "Google Drive API"
   ← Credentials ← API key ← ضعه في .env كـ DRIVE_API_KEY=...
3) معاينة ثم تنفيذ:
  venv/Scripts/python.exe drive_import.py --folder XXXX --limit 5 --dry-run
  venv/Scripts/python.exe drive_import.py --folder XXXX --limit 50 --target "@قناتك" --category كتب --delay 3

شروط: ملفات PDF/EPUB/TXT/MOBI حتى 45MB (حد تلغرام 50MB)، والبوت مشرف في القناة.
قانونياً: فقط كتب تملك حقوقها أو ملكية عامة.
"""
import argparse
import asyncio
import os
import re
import sys

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

TMPDIR = "drive_dl"
EXTS = (".pdf", ".epub", ".txt", ".mobi")
DOC_EXPORT = "application/pdf"  # مستندات Google تُصدَّر PDF
MAX_DEPTH = 2


def parse_name(name: str):
    """يستخرج (عنوان، مؤلف) من 'عنوان - مؤلف.pdf' وإلا (الاسم، غير معروف)."""
    base = re.sub(r"\.(pdf|epub|txt|mobi)$", "", name, flags=re.I).strip()
    if " - " in base:
        t, a = base.split(" - ", 1)
        return t.strip()[:150] or base[:150], a.strip()[:100] or "غير معروف"
    return base[:150], "غير معروف"


async def drive_list(session: aiohttp.ClientSession, key: str, folder: str, depth: int = 0):
    """سرد تكراري: ملفات كتب + اختصارات (تُحل) + مجلدات فرعية (حتى MAX_DEPTH)."""
    out = []
    if depth > MAX_DEPTH:
        return out
    page = None
    while True:
        params = {
            "key": key,
            "q": f"'{folder}' in parents and trashed=false",
            "fields": "nextPageToken,files(id,name,mimeType,size,shortcutDetails)",
            "pageSize": 100,
        }
        if page:
            params["pageToken"] = page
        async with session.get("https://www.googleapis.com/drive/v3/files", params=params,
                               timeout=aiohttp.ClientTimeout(total=25)) as r:
            if r.status != 200:
                print(f"[X] list: HTTP {r.status} — تحقق من المفتاح والمشاركة العامة")
                return out
            data = await r.json()
        for f in data.get("files", []):
            mt = f.get("mimeType", "")
            if mt == "application/vnd.google-apps.shortcut":
                sd = f.get("shortcutDetails", {}) or {}
                tid, tmt = sd.get("targetId", ""), sd.get("targetMimeType", "")
                if not tid:
                    continue
                if tmt == "application/vnd.google-apps.folder":
                    out += await drive_list(session, key, tid, depth + 1)
                else:
                    out.append({"id": tid, "name": f.get("name", tid),
                                "mimeType": tmt, "size": f.get("size")})
            elif mt == "application/vnd.google-apps.folder":
                out += await drive_list(session, key, f["id"], depth + 1)
            else:
                out.append(f)
        page = data.get("nextPageToken")
        if not page:
            return out


def is_book(f: dict) -> bool:
    name = (f.get("name") or "").lower()
    if name.endswith(EXTS):
        return True
    return f.get("mimeType") == "application/vnd.google-apps.document"


async def download_entry(session, key, f, dest, max_bytes) -> int:
    """تحميل ملف عادي أو تصدير مستند Google كـ PDF. يعيد الحجم أو -1."""
    try:
        if f.get("mimeType") == "application/vnd.google-apps.document":
            url, params = (f"https://www.googleapis.com/drive/v3/files/{f['id']}/export",
                           {"mimeType": DOC_EXPORT, "key": key})
        else:
            url, params = ("https://www.googleapis.com/drive/v3/files/"
                           f"{f['id']}?alt=media", {"key": key})
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=300)) as r:
            if r.status != 200:
                return -1
            size = 0
            with open(dest, "wb") as fh:
                async for ch in r.content.iter_chunked(256 * 1024):
                    size += len(ch)
                    if size > max_bytes:
                        break
                    fh.write(ch)
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
    ap.add_argument("--folder", required=True, help="ID المجلد من رابط Drive")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--target", default="", help="قناة الرفع مثل @قناتك")
    ap.add_argument("--category", default="كتب")
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--max-mb", type=float, default=45.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    key = os.getenv("DRIVE_API_KEY", "").strip()
    if not key:
        print("ضع DRIVE_API_KEY في .env أولاً (مفتاح Drive API المجاني)")
        return
    await db.init_db()
    os.makedirs(TMPDIR, exist_ok=True)
    max_bytes = int(a.max_mb * 1024 * 1024)
    bot = Bot(token=config.BOT_TOKEN) if config.BOT_TOKEN else None

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            files = [f for f in await drive_list(s, key, a.folder) if is_book(f)]
            print(f"FOUND {len(files)} ملفاً")
            done = 0
            for f in files:
                if done >= a.limit:
                    break
                is_doc = f.get("mimeType") == "application/vnd.google-apps.document"
                ext = ".pdf" if is_doc else os.path.splitext(f.get("name", ""))[1].lower()
                title, author = parse_name(f["name"] if not is_doc else f["name"] + ".pdf")
                base = f"https://www.googleapis.com/drive/v3/files/{f['id']}"
                dl = base + "?alt=media"
                if a.dry_run:
                    print(f" - {title} | {author} | {f.get('size', '?')}b")
                    done += 1
                    continue
                if not a.target or not bot:
                    print("حدد --target (القناة) للتنفيذ الحقيقي")
                    return
                if await db.find_by_source(dl):
                    continue
                size = int(f.get("size") or 0)
                if size > max_bytes:
                    print(f" - تخطي (كبير): {title}")
                    continue
                dest = os.path.join(TMPDIR, f["id"] + ext)
                size = await download_entry(s, key, f, dest, max_bytes)
                if size < 0:
                    print(f" - تخطي (كبير/فشل): {title}")
                    continue
                try:
                    msg = await bot.send_document(a.target, FSInputFile(dest),
                                                  caption=f"📖 {title} — {author}"[:1000])
                except Exception as e:
                    print(f"[X] send: {e!r} — البوت مشرف؟")
                    break
                ftype = ext[1:] or "pdf"
                bid = await db.add_book(title, author, a.category, "", msg.document.file_id,
                                        ftype, f["name"], size, "ar", None,
                                        file_unique_id=msg.document.file_unique_id or "",
                                        source_url=dl)
                print(f" + #{bid}: {title}")
                done += 1
                try:
                    os.remove(dest)
                except OSError:
                    pass
                await asyncio.sleep(a.delay)
    finally:
        if bot:
            await bot.session.close()
    print(f"OK: imported={done}")


if __name__ == "__main__":
    asyncio.run(main())
