"""قارئ WebApp مصغّر: يعرض بيانات الكتاب + الوصف + الغلاف + التلخيص المحلي.
ملاحظة صريحة: عرض الملف الكامل (EPUB/PDF) يحتاج S3/CDN — هذه النسخة تعرض
البيانات والوصف والاقتباسات مع رابط العودة للبوت للتحميل."""
import os
from aiohttp import web
import database as db

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")

async def api_book(request: web.Request):
    try:
        bid = int(request.query.get("book", "0"))
    except ValueError:
        return web.json_response({"error": "bad id"}, status=400)
    b = await db.get_book(bid)
    if not b:
        return web.json_response({"error": "not found"}, status=404)
    quotes = await db.quotes_of_book(bid, 5)
    return web.json_response({
        "id": b["id"], "title": b.get("title"), "author": b.get("author"),
        "category": b.get("category"), "lang": b.get("lang"),
        "publisher": b.get("publisher"), "year": b.get("year"),
        "pages": b.get("pages"), "isbn": b.get("isbn"),
        "cover": b.get("cover_url"), "tags": b.get("tags"),
        "description": (b.get("description") or "")[:2000],
        "downloads": b.get("downloads", 0),
        "rating_avg": b.get("rating_avg", 0), "rating_cnt": b.get("rating_cnt", 0),
        "quotes": [q["text"] for q in quotes],
    })

async def health(_):
    return web.json_response({"ok": True})

async def index(_):
    fp = os.path.join(STATIC, "index.html")
    if not os.path.exists(fp):
        return web.Response(text="reader missing", status=500)
    return web.FileResponse(fp)

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/api/book", api_book)
    app.router.add_get("/", index)
    if os.path.isdir(STATIC):
        # الملفات الثابتة + توجيه /app/ مباشرة لصفحة القارئ (بدل قائمة الملفات)
        app.router.add_get("/app/", index)
        app.router.add_get("/app/index.html", index)
        app.router.add_static("/app/static/", STATIC, show_index=False)
    return app
