"""
بوت مكتبة إلكترونية v3 - aiogram v3
مكتبة مخزنة + بحث إنترنت + مفضلة + سجل + Inline + إدارة + نسخ احتياطي + Webhook
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InlineQuery, InlineQueryResultCachedDocument, InlineQueryResultArticle,
    InputTextMessageContent, FSInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database as db
import keyboards as kb
import utils as U
from internet_search import internet_search

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
log = logging.getLogger("library-bot")

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML")) if config.BOT_TOKEN else None
dp = Dispatcher()
PAGE = config.PAGE_SIZE

# كاش البحث الداخلي: user_id -> آخر استعلام (لتفادي وضع العربي في callback_data)
_searches: dict[int, str] = {}

class Search(StatesGroup):
    local = State()
    net = State()

class AddBook(StatesGroup):
    file = State()
    title = State()
    author = State()
    cat_choice = State()
    cat_new = State()
    desc = State()

class DelBook(StatesGroup):
    waiting_id = State()

class Broadcast(StatesGroup):
    waiting_text = State()

class RequestF(StatesGroup):
    title = State()
    author = State()

class EnrichF(StatesGroup):
    waiting_id = State()

class ProgressF(StatesGroup):
    waiting_page = State()

class QuoteF(StatesGroup):
    waiting_text = State()

class ReviewF(StatesGroup):
    waiting_text = State()

class EditF(StatesGroup):
    waiting_value = State()

WELCOME = """📚 <b>أهلاً بك في المكتبة الإلكترونية!</b>

📂 تصنيفات • 🔍 بحث داخلي • 🌐 بحث إنترنت مجاني
⭐ الأكثر تحميلاً • 🆕 الأحدث • ❤️ مفضلة • 🕘 سجلّك

💡 جرّب البحث السريع من أي محادثة: <code>@botusername اسم الكتاب</code> (فعّل Inline من BotFather)

⚖️ مصادر مجانية وملكية عامة فقط."""

HELP_TXT = """ℹ️ <b>الأوامر:</b>
/start الرئيسية
/search نص + فلتر: <code>/search فلسفة lang:ar</code>
/net إنترنت • /author • /isbn • /random • /today كتاب اليوم
/popular /recent /top /new
/favs /history /mybooks • /request طلب
/id • /cancel

🛠 <b>الأدمن:</b> إضافة • إدارة • إثراء • نسخة • تصدير • فهرسة • بث
"""

async def safe_edit(c: CallbackQuery, text: str, reply_markup=None, **kw):
    try:
        await c.message.edit_text(text, reply_markup=reply_markup, **kw)
    except TelegramBadRequest:
        await c.message.answer(text, reply_markup=reply_markup, **kw)

async def need_sub(m_or_c) -> bool:
    """True إذا مشترك أو لا توجد قناة إجبارية."""
    if not config.FORCE_CHANNEL or bot is None:
        return True
    try:
        member = await bot.get_chat_member(config.FORCE_CHANNEL, m_or_c.from_user.id)
        return member.status not in ("left", "kicked")
    except Exception:
        return True

async def sub_prompt(m: Message):
    ch = config.FORCE_CHANNEL.lstrip("@")
    await m.answer(
        f"📢 اشترك أولاً في القناة ثم أرسل /start:\n👉 https://t.me/{ch}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك", url=f"https://t.me/{ch}")],
        ]),
    )

# ---------- أساسية ----------
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await db.add_user(m.from_user.id, m.from_user.username, m.from_user.full_name)
    # bootstrap: أول مستخدم يصبح أدمن إذا لم يُضبط ADMIN_IDS (يصلح مشكلة الرقم المثال)
    if not config.ADMIN_IDS:
        config.ADMIN_IDS.add(m.from_user.id)
        try:
            from pathlib import Path as _P
            _env = _P(".env")
            if _env.exists():
                t = _env.read_text(encoding="utf-8")
                if "ADMIN_IDS=" in t:
                    lines = [f"ADMIN_IDS={m.from_user.id}" if l.startswith("ADMIN_IDS=") else l
                             for l in t.splitlines()]
                    _env.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            log.warning("bootstrap admin persist failed: %s", e)
        await m.answer(f"✅ تم تعيينك كأدمن تلقائياً (أول مستخدم).\n🆔 <code>{m.from_user.id}</code>")
    if not await need_sub(m):
        await sub_prompt(m)
        return
    # رابط عميق: t.me/Bot?start=book_123 يفتح الكتاب مباشرة
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("book_") and parts[1][5:].isdigit():
        b = await db.get_book(int(parts[1][5:]))
        if b:
            fav = await db.is_fav(m.from_user.id, b["id"])
            shelf = await db.shelf_get(m.from_user.id, b["id"])
            await m.answer(U.book_text(b) + f"\n\n🆔 <code>#{b['id']}</code>",
                           reply_markup=kb.book_kb(b["id"], fav, shelf, config.is_admin(m.from_user.id)))
            return
    await m.answer(WELCOME, reply_markup=kb.main_menu(config.is_admin(m.from_user.id)))

@dp.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(HELP_TXT)

@dp.message(Command("id"))
async def cmd_id(m: Message):
    await m.answer(f"🆔 معرفك: <code>{m.from_user.id}</code>")

@dp.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("❌ تم الإلغاء.", reply_markup=kb.main_menu(config.is_admin(m.from_user.id)))

@dp.message(Command("backup"))
async def cmd_backup(m: Message):
    if not config.is_admin(m.from_user.id):
        return await m.answer("للأدمن فقط ⛔")
    if not os.path.exists(config.DB_PATH):
        return await m.answer("لا توجد قاعدة بعد.")
    await m.answer_document(FSInputFile(config.DB_PATH), caption="💾 نسخة احتياطية")

async def do_local(m: Message, q: str, offset: int = 0):
    raw = q.strip()
    query, lang, year, tag = _parse_search_flags(raw)
    if len(query) < 2 and not (lang or year or tag):
        await m.answer("🔍 مثال: <code>/search تاريخ</code> أو <code>/search فلسفة lang:ar tag:فلسفة</code>")
        return
    if not U.flood_ok(m.from_user.id):
        await m.answer("⏳ انتظر ثانية وحاول مجدداً.")
        return
    _searches[m.from_user.id] = raw
    if lang or year or tag:
        books = await db.search_advanced(query, lang, year, tag, limit=11, offset=offset)
    else:
        books = await db.search_books(query, limit=11, offset=offset)
    has_more = len(books) > 10
    books = books[:10]
    if not books:
        if offset == 0:
            await m.answer(f"لا نتائج لـ «{U.esc(q)}».\nجرّب: <code>/net {U.esc(q)}</code>")
        else:
            await m.answer("لا مزيد.")
        return
    await m.answer(f"🔍 نتائج «{U.esc(q)}»:", reply_markup=kb.search_kb(books, offset, has_more))

async def do_net(m: Message, q: str):
    q = q.strip()
    if len(q) < 2:
        await m.answer("🌐 أرسل كلمة من حرفين على الأقل.")
        return
    if not U.flood_ok(m.from_user.id):
        await m.answer("⏳ انتظر ثانية وحاول مجدداً.")
        return
    wait = await m.answer(f"🌐 جارٍ البحث عن «{U.esc(q)}»...")
    results = await internet_search(q)
    if not results:
        await wait.edit_text("لا نتائج. جرّب كلمات إنجليزية للكتب الأجنبية.")
        return
    for part in U.chunk(U.net_text(q, results), 4000):
        await m.answer(part, disable_web_page_preview=True)

@dp.message(Command("search"))
async def cmd_search(m: Message):
    q = m.text.partition(" ")[2].strip()
    if not q:
        await m.answer("اكتب: <code>/search اسم الكتاب</code>")
        return
    await do_local(m, q)

@dp.message(Command("net"))
async def cmd_net(m: Message):
    q = m.text.partition(" ")[2].strip()
    if not q:
        await m.answer("اكتب: <code>/net اسم الكتاب</code>")
        return
    await do_net(m, q)

@dp.message(Command("popular"))
async def cmd_popular(m: Message):
    books = await db.get_popular(10)
    if not books:
        await m.answer("المكتبة فارغة حالياً.")
        return
    await m.answer("⭐ <b>الأكثر تحميلاً:</b>", reply_markup=kb.books_kb(books, back="home"))

@dp.message(Command("recent"))
async def cmd_recent(m: Message):
    books = await db.get_recent(10)
    if not books:
        await m.answer("المكتبة فارغة حالياً.")
        return
    await m.answer("🆕 <b>الأحدث:</b>", reply_markup=kb.books_kb(books, back="home"))

@dp.message(Command("favs"))
async def cmd_favs(m: Message):
    books = await db.get_favs(m.from_user.id)
    if not books:
        await m.answer("❤️ قائمتك فارغة. افتح أي كتاب واضغط ⭐ مفضل.")
        return
    await m.answer("❤️ <b>مفضلتك:</b>", reply_markup=kb.books_kb(books, back="home"))

@dp.message(Command("history"))
async def cmd_history(m: Message):
    books = await db.get_history(m.from_user.id, 10)
    if not books:
        await m.answer("🕘 سجلك فارغ. حمّل أي كتاب وسيظهر هنا.")
        return
    await m.answer("🕘 <b>آخر تحميلاتك:</b>", reply_markup=kb.books_kb(books, back="home"))

# ---------- Inline: بحث من أي محادثة ----------
@dp.inline_query()
async def inline_search(inline: InlineQuery):
    q = (inline.query or "").strip()
    # دعم مشاركة كتاب محدد: book:123
    if q.startswith("book:") and q[5:].isdigit():
        b = await db.get_book(int(q[5:]))
        if b:
            try:
                await inline.answer([
                    InlineQueryResultCachedDocument(
                        id=f"lb{b['id']}", title=b["title"][:60],
                        document_file_id=b["file_id"],
                        description=f"{b.get('author','')} | {b.get('category','')}"[:80],
                        caption=f"📖 {b['title']} — {b.get('author','')}"[:900],
                    )
                ], cache_time=300, is_personal=True)
                return
            except Exception:
                pass
    if len(q) < 2:
        await inline.answer([], cache_time=1, is_personal=True,
            switch_pm_text="اكتب اسم الكتاب للبحث 🔍", switch_pm_parameter="start")
        return
    books = await db.search_books(q, limit=10)
    results = []
    for b in books:
        try:
            results.append(InlineQueryResultCachedDocument(
                id=f"lb{b['id']}", title=b["title"][:60],
                document_file_id=b["file_id"],
                description=f"{b.get('author','')} | {b.get('category','')}"[:80],
                caption=f"📖 {b['title']} — {b.get('author','')}"[:900],
            ))
        except Exception:
            continue
    try:
        net = await internet_search(q, limit_per_source=1)
        for i, r in enumerate(net[:3]):
            results.append(InlineQueryResultArticle(
                id=f"net{i}_{abs(hash(r['link'])) % 10**8}",
                title=f"🌐 {r['title'][:55]}",
                description=f"{r['author']} | {r['source']}"[:80],
                input_message_content=InputTextMessageContent(
                    message_text=f"📖 <b>{U.esc(r['title'])}</b>\n✍️ {U.esc(r['author'])}\n🔗 <a href=\"{r['link']}\">تحميل / قراءة</a>",
                    parse_mode="HTML"),
            ))
    except Exception:
        pass
    try:
        await inline.answer(results[:15], cache_time=60, is_personal=True)
    except Exception:
        pass

# ---------- تنقل ----------
@dp.callback_query(F.data == "home")
async def cb_home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(c, WELCOME, kb.main_menu(config.is_admin(c.from_user.id)))
    await c.answer()

@dp.callback_query(F.data == "help")
async def cb_help(c: CallbackQuery):
    await safe_edit(c, HELP_TXT, kb.back_home())
    await c.answer()

@dp.callback_query(F.data == "cats")
async def cb_cats(c: CallbackQuery):
    cats = await db.get_categories()
    if not cats:
        await safe_edit(c, "المكتبة فارغة حالياً.", kb.back_home())
    else:
        await safe_edit(c, "📚 <b>التصنيفات:</b>", kb.categories_kb(cats))
    await c.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def cb_cat(c: CallbackQuery):
    try:
        _, sid, soff = c.data.split(":")
        cat_id, offset = int(sid), int(soff)
    except ValueError:
        await c.answer("بيانات غير صالحة", show_alert=True)
        return
    books = await db.get_books_by_category(cat_id, limit=PAGE + 1, offset=offset)
    has_more = len(books) > PAGE
    books = books[:PAGE]
    if not books:
        await c.answer("لا مزيد" if offset else "لا كتب هنا", show_alert=True)
        return
    cats = {x["id"]: x["name"] for x in await db.get_categories()}
    await safe_edit(c, f"📂 <b>{U.esc(cats.get(cat_id, ''))}:</b>",
                    kb.books_kb(books, cat_id=cat_id, offset=offset, has_more=has_more))
    await c.answer()

@dp.callback_query(F.data.startswith("sl:"))
async def cb_search_more(c: CallbackQuery):
    try:
        offset = int(c.data.split(":")[1])
    except ValueError:
        return await c.answer("خطأ", show_alert=True)
    q = _searches.get(c.from_user.id, "")
    if not q:
        return await c.answer("انتهت الجلسة، ابحث مجدداً", show_alert=True)
    books = await db.search_books(q, limit=11, offset=offset)
    has_more = len(books) > 10
    books = books[:10]
    if not books:
        return await c.answer("لا مزيد", show_alert=True)
    await safe_edit(c, f"🔍 نتائج «{U.esc(q)}»:", kb.search_kb(books, offset, has_more))
    await c.answer()

@dp.callback_query(F.data == "popular")
async def cb_popular(c: CallbackQuery):
    books = await db.get_popular(10)
    if not books:
        await safe_edit(c, "المكتبة فارغة.", kb.back_home())
    else:
        await safe_edit(c, "⭐ <b>الأكثر تحميلاً:</b>", kb.books_kb(books, back="home"))
    await c.answer()

@dp.callback_query(F.data == "recent")
async def cb_recent(c: CallbackQuery):
    books = await db.get_recent(10)
    if not books:
        await safe_edit(c, "المكتبة فارغة.", kb.back_home())
    else:
        await safe_edit(c, "🆕 <b>الأحدث:</b>", kb.books_kb(books, back="home"))
    await c.answer()

@dp.callback_query(F.data == "myfavs")
async def cb_myfavs(c: CallbackQuery):
    books = await db.get_favs(c.from_user.id)
    if not books:
        await safe_edit(c, "❤️ قائمتك فارغة.", kb.back_home())
    else:
        await safe_edit(c, "❤️ <b>مفضلتك:</b>", kb.books_kb(books, back="home"))
    await c.answer()

@dp.callback_query(F.data == "history")
async def cb_history(c: CallbackQuery):
    books = await db.get_history(c.from_user.id, 10)
    if not books:
        await safe_edit(c, "🕘 سجلك فارغ.", kb.back_home())
    else:
        await safe_edit(c, "🕘 <b>آخر تحميلاتك:</b>", kb.books_kb(books, back="home"))
    await c.answer()

@dp.callback_query(F.data.startswith("book:"))
async def cb_book(c: CallbackQuery):
    try:
        bid = int(c.data.split(":")[1])
    except ValueError:
        return await c.answer("خطأ", show_alert=True)
    b = await db.get_book(bid)
    if not b:
        return await c.answer("الكتاب محذوف", show_alert=True)
    fav = await db.is_fav(c.from_user.id, bid)
    shelf = await db.shelf_get(c.from_user.id, bid)
    txt = U.book_text(b) + f"\n\n🆔 <code>#{bid}</code>"
    await safe_edit(c, txt, kb.book_kb(bid, fav, shelf, _need_admin(c)))
    await c.answer()

@dp.callback_query(F.data.startswith("dl:"))
async def cb_dl(c: CallbackQuery):
    try:
        bid = int(c.data.split(":")[1])
    except ValueError:
        return await c.answer("خطأ", show_alert=True)
    b = await db.get_book(bid)
    if not b:
        return await c.answer("محذوف", show_alert=True)
    await db.increment_download(bid, c.from_user.id)
    # كتاب خارجي (فهرس فقط بلا ملف مرفوع): نرسل الرابط القانوني بدل الملف
    if not b.get("file_id") and b.get("source_url"):
        await c.message.answer(f"🌐 تحميل خارجي (مصدر مجاني):\n📖 {b['title']}\n🔗 {b['source_url']}")
        await c.answer("تم ✅")
        return
    try:
        await c.message.answer_document(b["file_id"], caption=f"📖 {b['title']} — {b['author']}"[:1000])
    except (TelegramBadRequest, TelegramForbiddenError):
        await c.message.answer("تعذر إرسال الملف (file_id قديم). أعد رفع الكتاب.")
    await c.answer("تم الإرسال ✅")

@dp.callback_query(F.data.startswith("fav:"))
async def cb_fav(c: CallbackQuery):
    bid = int(c.data.split(":")[1])
    now_fav = await db.toggle_fav(c.from_user.id, bid)
    b = await db.get_book(bid)
    if b:
        shelf = await db.shelf_get(c.from_user.id, bid)
        await safe_edit(c, U.book_text(b) + f"\n\n🆔 <code>#{bid}</code>", kb.book_kb(bid, now_fav, shelf, _need_admin(c)))
    await c.answer("⭐ أضيف للمفضلة" if now_fav else "💔 أزيل من المفضلة")

@dp.callback_query(F.data == "ask_local")
async def cb_ask_local(c: CallbackQuery, state: FSMContext):
    await state.set_state(Search.local)
    await c.message.answer("🔍 أرسل اسم الكتاب أو المؤلف:")
    await c.answer()

@dp.callback_query(F.data == "ask_net")
async def cb_ask_net(c: CallbackQuery, state: FSMContext):
    await state.set_state(Search.net)
    await c.message.answer("🌐 أرسل اسم الكتاب (عربي/إنجليزي):")
    await c.answer()

@dp.message(StateFilter(Search.local))
async def on_local(m: Message, state: FSMContext):
    await state.clear()
    if m.text and m.text.startswith("/"):
        return
    await do_local(m, m.text or "")

@dp.message(StateFilter(Search.net))
async def on_net(m: Message, state: FSMContext):
    await state.clear()
    if m.text and m.text.startswith("/"):
        return
    await do_net(m, m.text or "")

# ---------- أدمن ----------
def _need_admin(c_or_m) -> bool:
    return config.is_admin(c_or_m.from_user.id)

@dp.callback_query(F.data == "admin")
async def cb_admin(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط ⛔", show_alert=True)
    s = await db.count_stats()
    top = "\n".join(f"• {n}: {cnt}" for n, cnt in s["top"]) or "—"
    await safe_edit(c, f"🛠 <b>لوحة الأدمن</b>\n📚 {s['books']} | 👥 {s['users']} | ⬇️ {s['downloads']} | 📂 {s['cats']}\n\n<b>الأعلى:</b>\n{top}",
                    kb.admin_menu())
    await c.answer()

@dp.callback_query(F.data == "stats")
async def cb_stats(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    s = await db.count_stats()
    await c.message.answer(f"📊 كتب: {s['books']}\n👥 مستخدمون: {s['users']}\n⬇️ تحميلات: {s['downloads']}\n📂 تصنيفات: {s['cats']}")
    await c.answer()

@dp.callback_query(F.data == "backup")
async def cb_backup(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    if not os.path.exists(config.DB_PATH):
        return await c.answer("لا توجد قاعدة بعد", show_alert=True)
    try:
        await c.message.answer_document(FSInputFile(config.DB_PATH), caption="💾 نسخة احتياطية من المكتبة")
    except Exception as e:
        await c.message.answer(f"فشل النسخ: {e}")
    await c.answer()

@dp.callback_query(F.data.startswith("manage:"))
async def cb_manage(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    try:
        offset = int(c.data.split(":")[1])
    except ValueError:
        offset = 0
    books = await db.list_books(limit=PAGE, offset=offset)
    # كشف هل يوجد المزيد
    nxt = await db.list_books(limit=1, offset=offset + PAGE)
    if not books and offset == 0:
        await safe_edit(c, "لا كتب بعد. أضف من ➕.", kb.admin_menu())
    else:
        await safe_edit(c, f"📋 <b>إدارة الكتب</b> (اضغط للحذف السريع):",
                        kb.manage_kb(books, offset, bool(nxt)))
    await c.answer()

@dp.callback_query(F.data.startswith("mdel:"))
async def cb_mdel(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    try:
        _, sid, soff = c.data.split(":")
        bid, offset = int(sid), int(soff)
    except ValueError:
        return await c.answer("خطأ", show_alert=True)
    ok = await db.delete_book(bid)
    await c.answer("✅ حُذف" if ok else "غير موجود", show_alert=True)
    books = await db.list_books(limit=PAGE, offset=offset)
    nxt = await db.list_books(limit=1, offset=offset + PAGE)
    if not books and offset > 0:
        offset = max(0, offset - PAGE)
        books = await db.list_books(limit=PAGE, offset=offset)
        nxt = await db.list_books(limit=1, offset=offset + PAGE)
    await safe_edit(c, "📋 <b>إدارة الكتب:</b>", kb.manage_kb(books, offset, bool(nxt)))

@dp.callback_query(F.data == "addbook")
async def cb_addbook(c: CallbackQuery, state: FSMContext):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    await state.set_state(AddBook.file)
    await c.message.answer(f"➕ أرسل ملف الكتاب (PDF/EPUB حتى {config.MAX_FILE_MB}MB):", reply_markup=kb.cancel_kb())
    await c.answer()

@dp.callback_query(F.data == "cancel_add")
async def cb_cancel_add(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(c, WELCOME, kb.main_menu(True))
    await c.answer("تم الإلغاء")

@dp.message(StateFilter(AddBook.file), F.document)
async def add_file(m: Message, state: FSMContext):
    if not _need_admin(m):
        return
    doc = m.document
    ok, ftype, err = U.validate_file(doc.file_name or "", doc.mime_type or "", doc.file_size or 0)
    if not ok:
        await m.answer(err)
        return
    await state.update_data(file_id=doc.file_id, file_type=ftype, file_name=doc.file_name or "", file_size=doc.file_size or 0,
                            file_unique_id=getattr(doc, "file_unique_id", "") or "")
    # كشف التكرار مبكراً
    if getattr(doc, "file_unique_id", ""):
        dup = await db.find_duplicate(doc.file_unique_id)
        if dup:
            await m.answer(f"⚠️ هذا الملف موجود مسبقاً: 📖 {dup['title']} (#{dup['id']})")
            return
    await state.set_state(AddBook.title)
    await m.answer("✅ تم استلام الملف.\nالآن أرسل <b>عنوان الكتاب:</b>")

@dp.message(StateFilter(AddBook.file))
async def add_file_wrong(m: Message):
    if m.text and m.text.startswith("/"):
        return
    await m.answer("📎 أرسل الملف كـ Document وليس نصاً.")

@dp.message(StateFilter(AddBook.title))
async def add_title(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if len(t) < 2 or len(t) > 150:
        await m.answer("⚠️ العنوان من 2 إلى 150 حرفاً.")
        return
    await state.update_data(title=t)
    await state.set_state(AddBook.author)
    await m.answer("الآن أرسل <b>اسم المؤلف</b> (أو - للتخطي):")

@dp.message(StateFilter(AddBook.author))
async def add_author(m: Message, state: FSMContext):
    a = (m.text or "").strip()
    if a == "-":
        a = "غير معروف"
    if len(a) > 100:
        await m.answer("⚠️ الاسم طويل جداً.")
        return
    await state.update_data(author=a)
    cats = await db.get_categories()
    await state.set_state(AddBook.cat_choice)
    if cats:
        await m.answer("اختر <b>التصنيف</b> أو أنشئ جديداً:", reply_markup=kb.cat_choice_kb(cats))
    else:
        await state.set_state(AddBook.cat_new)
        await m.answer("أرسل <b>اسم التصنيف الجديد</b> (مثال: روايات):")

@dp.callback_query(StateFilter(AddBook.cat_choice), F.data.startswith("pickcat:"))
async def pick_cat(c: CallbackQuery, state: FSMContext):
    val = c.data.split(":")[1]
    if val == "new":
        await state.set_state(AddBook.cat_new)
        await c.message.answer("أرسل <b>اسم التصنيف الجديد:</b>")
    else:
        cats = {str(x["id"]): x["name"] for x in await db.get_categories()}
        name = cats.get(val, "عام")
        await state.update_data(category=name)
        await state.set_state(AddBook.desc)
        await c.message.answer("اختر <b>اللغة</b>:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇸🇦 عربي", callback_data="picklang:ar"),
             InlineKeyboardButton(text="🇬🇧 English", callback_data="picklang:en")],
        ]))
    await c.answer()

@dp.message(StateFilter(AddBook.cat_new))
async def add_cat_new(m: Message, state: FSMContext):
    name = (m.text or "").strip()[:40]
    if len(name) < 2:
        await m.answer("⚠️ اسم قصير جداً.")
        return
    await state.update_data(category=name)
    await state.set_state(AddBook.desc)
    await m.answer("اختر <b>اللغة</b>:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇸🇦 عربي", callback_data="picklang:ar"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="picklang:en")],
    ]))

@dp.callback_query(StateFilter(AddBook.desc), F.data.startswith("picklang:"))
async def pick_lang(c: CallbackQuery, state: FSMContext):
    lang = c.data.split(":")[1]
    await state.update_data(lang=lang if lang in ("ar", "en") else "ar")
    await c.message.answer("أرسل <b>وصفاً مختصراً</b> (أو - للتخطي):")
    await state.update_data(_need_desc=True)
    await c.answer()

@dp.message(StateFilter(AddBook.desc))
async def add_desc(m: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("_need_desc"):
        await m.answer("⚠️ اختر اللغة من الأزرار أولاً.")
        return
    d = (m.text or "").strip()
    if d == "-":
        d = ""
    await state.update_data(description=d[:800], _need_desc=False)
    preview = (f"📖 <b>{U.esc(data.get('title'))}</b>\n✍️ {U.esc(data.get('author'))}\n"
               f"📂 {U.esc(data.get('category'))} | 🌍 {data.get('lang')}\n"
               f"📎 {U.esc(data.get('file_name'))}\n\n{U.esc(d)[:400]}\n\nتأكيد الحفظ؟")
    await m.answer(preview, reply_markup=kb.confirm_kb())

@dp.callback_query(F.data == "confirm_add")
async def confirm_add(c: CallbackQuery, state: FSMContext):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    data = await state.get_data()
    if not data.get("file_id") or not data.get("title"):
        await c.answer("البيانات ناقصة، أعد المحاولة", show_alert=True)
        await state.clear()
        return
    bid = await db.add_book(data["title"], data.get("author", "غير معروف"),
                            data.get("category", "عام"), data.get("description", ""),
                            data["file_id"], data.get("file_type", "pdf"),
                            data.get("file_name", ""), data.get("file_size", 0),
                            data.get("lang", "ar"), c.from_user.id,
                            file_unique_id=data.get("file_unique_id", ""))
    if bid is None:
        await c.answer("الملف مكرر", show_alert=True)
        await state.clear()
        return
    await state.clear()
    await safe_edit(c, f"✅ تم الحفظ برقم <b>{bid}</b>:\n📖 {U.esc(data['title'])}", kb.main_menu(True))
    await c.answer()
    # إتمام الطلبات المطابقة تلقائياً + إشعار طالبيها
    try:
        for req in await db.req_find_match(data["title"]):
            for uid in await db.req_voters(req["id"]):
                try:
                    await bot.send_message(uid, f"🎉 طلبك توفر!\n📖 <b>{U.esc(data['title'])}</b> (#{bid})\nأرسل /start لعرضه.")
                except Exception:
                    pass
            await db.req_fulfill(req["id"])
    except Exception as e:
        log.warning("req fulfill failed: %s", e)
    # نشر تلقائي في قناة المكتبة إن ضُبطت
    if getattr(config, "LIB_CHANNEL", "") and bot is not None:
        try:
            await bot.send_document(config.LIB_CHANNEL, data["file_id"],
                                    caption=f"📖 {data['title']} — {data.get('author','')}\n#{bid}")
        except Exception as e:
            log.warning("auto-publish failed: %s", e)

@dp.callback_query(F.data == "delbook")
async def cb_delbook(c: CallbackQuery, state: FSMContext):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    await state.set_state(DelBook.waiting_id)
    await c.message.answer("🗑 أرسل <b>رقم الكتاب (ID)</b> — أو استخدم 📋 إدارة الكتب للحذف بالأزرار.")
    await c.answer()

@dp.message(StateFilter(DelBook.waiting_id))
async def del_confirm(m: Message, state: FSMContext):
    if not _need_admin(m):
        return
    txt = (m.text or "").strip()
    if not txt.isdigit():
        await m.answer("⚠️ أرسل رقماً صحيحاً.")
        return
    ok = await db.delete_book(int(txt))
    await state.clear()
    await m.answer("✅ تم الحذف." if ok else "❌ الرقم غير موجود.")

@dp.callback_query(F.data == "broadcast")
async def cb_bcast(c: CallbackQuery, state: FSMContext):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    await state.set_state(Broadcast.waiting_text)
    await c.message.answer("📢 أرسل نص الرسالة الجماعية (تدعم HTML):")
    await c.answer()

@dp.message(StateFilter(Broadcast.waiting_text))
async def do_bcast(m: Message, state: FSMContext):
    if not _need_admin(m):
        return
    await state.clear()
    ids = await db.get_all_user_ids()
    ok = fail = 0
    prog = await m.answer(f"📤 جارٍ البث لـ {len(ids)}...")
    for uid in ids:
        try:
            await bot.send_message(uid, m.text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await prog.edit_text(f"✅ تم: {ok} | ❌ فشل: {fail}")

# ---------- v4: أوامر ذكية + أرفف + تقييم + طلبات + إثراء ----------
def _parse_search_flags(text: str):
    """يدعم: /search تاريخ lang:ar year:2020 tag:فلسفة"""
    lang = year = tag = None
    words = []
    for w in text.split():
        if w.startswith("lang:"):
            lang = w[5:].strip() or None
        elif w.startswith("year:") and w[5:].isdigit():
            year = int(w[5:])
        elif w.startswith("tag:"):
            tag = w[4:].strip() or None
        else:
            words.append(w)
    return " ".join(words), lang, year, tag

@dp.message(Command("author"))
async def cmd_author(m: Message):
    q = m.text.partition(" ")[2].strip()
    if len(q) < 2:
        return await m.answer("اكتب: <code>/author اسم المؤلف</code>")
    books = await db.get_by_author(q, 10)
    if not books:
        return await m.answer(f"لا كتب للمؤلف «{U.esc(q)}».")
    await m.answer(f"✍️ كتب <b>{U.esc(q)}</b>:", reply_markup=kb.books_kb(books, back="home"))

@dp.message(Command("isbn"))
async def cmd_isbn(m: Message):
    q = m.text.partition(" ")[2].strip()
    if not q:
        return await m.answer("اكتب: <code>/isbn 978...</code>")
    books = await db.get_by_isbn(q)
    if books:
        await m.answer("🔖 موجود في المكتبة:", reply_markup=kb.books_kb(books, back="home"))
        return
    # بحث خارجي تلقائي ثم عرض الإثراء
    from metadata import enrich
    info = await enrich(isbn=q)
    if not info:
        return await m.answer("لا نتائج لهذا ISBN.")
    txt = f"🔖 <b>{U.esc(info.get('title',''))}</b>\n🏛 {U.esc(info.get('publisher',''))} | 📅 {info.get('year','?')}"
    await m.answer(txt + "\n\nغير مخزّن بعد — اطلبه بـ /request")

@dp.message(Command("random"))
async def cmd_random(m: Message):
    b = await db.get_random_book()
    if not b:
        return await m.answer("المكتبة فارغة.")
    fav = await db.is_fav(m.from_user.id, b["id"])
    shelf = await db.shelf_get(m.from_user.id, b["id"])
    await m.answer("🎲 <b>كتاب عشوائي لك:</b>\n\n" + U.book_text(b), reply_markup=kb.book_kb(b["id"], fav, shelf, _need_admin(m)))

@dp.message(Command("top"))
async def cmd_top(m: Message):
    await cmd_popular(m)

@dp.message(Command("new"))
async def cmd_new(m: Message):
    await cmd_recent(m)

@dp.message(Command("mybooks"))
async def cmd_mybooks(m: Message):
    await m.answer("📖 <b>مكتبتي:</b> اختر الرف:", reply_markup=kb.mybooks_kb())

@dp.callback_query(F.data == "random")
async def cb_random(c: CallbackQuery):
    b = await db.get_random_book()
    if not b:
        return await c.answer("فارغة", show_alert=True)
    fav = await db.is_fav(c.from_user.id, b["id"])
    shelf = await db.shelf_get(c.from_user.id, b["id"])
    await safe_edit(c, "🎲 <b>كتاب عشوائي:</b>\n\n" + U.book_text(b), kb.book_kb(b["id"], fav, shelf, _need_admin(c)))
    await c.answer()

@dp.callback_query(F.data == "mybooks")
async def cb_mybooks(c: CallbackQuery):
    await safe_edit(c, "📖 <b>مكتبتي:</b>", kb.mybooks_kb())
    await c.answer()

@dp.callback_query(F.data.startswith("shelf_list:"))
async def cb_shelf_list(c: CallbackQuery):
    shelf = c.data.split(":")[1]
    books = await db.my_shelves(c.from_user.id, shelf, 15)
    name = {"want": "📥 أريد القراءة", "reading": "📖 أقرأ الآن", "done": "✅ أنهيت"}.get(shelf, shelf)
    if not books:
        await safe_edit(c, f"{name}: فارغ.", kb.mybooks_kb())
    else:
        await safe_edit(c, f"<b>{name}:</b>", kb.books_kb(books, back="home"))
    await c.answer()

@dp.callback_query(F.data.startswith("shelf:"))
async def cb_shelf_set(c: CallbackQuery):
    _, shelf, sid = c.data.split(":")
    bid = int(sid)
    await db.shelf_set(c.from_user.id, bid, shelf)
    b = await db.get_book(bid)
    fav = await db.is_fav(c.from_user.id, bid)
    if b:
        await safe_edit(c, U.book_text(b) + f"\n\n🆔 <code>#{bid}</code>", kb.book_kb(bid, fav, shelf, _need_admin(c)))
    await c.answer("تمت الإضافة لرفّك ✅")

@dp.callback_query(F.data.startswith("rate:"))
async def cb_rate(c: CallbackQuery):
    bid = int(c.data.split(":")[1])
    await safe_edit(c, "قيّم الكتاب (1-5 ⭐):", kb.rate_kb(bid))
    await c.answer()

@dp.callback_query(F.data.startswith("rate_set:"))
async def cb_rate_set(c: CallbackQuery):
    _, sid, sstars = c.data.split(":")
    bid, stars = int(sid), max(1, min(5, int(sstars)))
    await db.rate_set(c.from_user.id, bid, stars)
    b = await db.get_book(bid)
    fav = await db.is_fav(c.from_user.id, bid)
    shelf = await db.shelf_get(c.from_user.id, bid)
    if b:
        await safe_edit(c, U.book_text(b) + f"\n\n🆔 <code>#{bid}</code>", kb.book_kb(bid, fav, shelf, _need_admin(c)))
    await c.answer(f"شكراً! قيّمت بـ {stars}⭐")

@dp.callback_query(F.data.startswith("prog:"))
async def cb_prog(c: CallbackQuery, state: FSMContext):
    bid = int(c.data.split(":")[1])
    await state.update_data(prog_book=bid)
    await state.set_state(ProgressF.waiting_page)
    cur = await db.progress_get(c.from_user.id, bid)
    hint = f" (الحالي: {cur['page']}/{cur['total']})" if cur else ""
    await c.message.answer(f"📝 أرسل تقدمك: <code>صفحة/إجمالي</code> مثال <code>30/200</code>{hint}")
    await c.answer()

@dp.message(StateFilter(ProgressF.waiting_page))
async def prog_save(m: Message, state: FSMContext):
    data = await state.get_data()
    bid = data.get("prog_book")
    txt = (m.text or "").replace(" ", "")
    try:
        page, total = (txt.split("/") + ["0"])[:2]
        await db.progress_set(m.from_user.id, bid, int(page), int(total))
        await state.clear()
        await m.answer(f"✅ حُفظ تقدمك: {page}/{total} للكتاب #{bid}")
    except (ValueError, TypeError):
        await m.answer("⚠️ الصيغة: <code>30/200</code>")

# طلبات الكتب
@dp.message(Command("request"))
async def cmd_request(m: Message, state: FSMContext):
    await state.set_state(RequestF.title)
    await m.answer("📝 أرسل <b>عنوان الكتاب المطلوب:</b>")

@dp.message(StateFilter(RequestF.title))
async def req_title(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if len(t) < 2:
        return await m.answer("عنوان قصير جداً.")
    await state.update_data(req_title=t)
    await state.set_state(RequestF.author)
    await m.answer("اسم المؤلف؟ (أو - للتخطي)")

@dp.message(StateFilter(RequestF.author))
async def req_author(m: Message, state: FSMContext):
    data = await state.get_data()
    a = (m.text or "").strip()
    if a == "-":
        a = ""
    rid = await db.req_add(m.from_user.id, data["req_title"], a)
    await state.clear()
    await m.answer(f"✅ سُجّل طلبك #{rid}. سنُشعر عند توفره. صوّت الآخرون من 📝 طلب كتاب.")

@dp.callback_query(F.data == "req_list")
async def cb_req_list(c: CallbackQuery):
    reqs = await db.req_list_open(10)
    if not reqs:
        rows = [[InlineKeyboardButton(text="➕ طلب جديد", callback_data="req_add")]]
    else:
        rows = []
        for r in reqs:
            rows.append([InlineKeyboardButton(
                text=f"📝 {r['title'][:30]} ({r['votes']}🗳)", callback_data=f"req_vote:{r['id']}")])
        rows.append([InlineKeyboardButton(text="➕ طلب جديد", callback_data="req_add")])
    rows.append([InlineKeyboardButton(text="🔙 الرئيسية", callback_data="home")])
    await safe_edit(c, "📝 <b>طلبات الكتب المفتوحة</b> (اضغط للتصويت):",
                    InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()

@dp.callback_query(F.data == "req_add")
async def cb_req_add(c: CallbackQuery, state: FSMContext):
    await state.set_state(RequestF.title)
    await c.message.answer("📝 أرسل <b>عنوان الكتاب المطلوب:</b>")
    await c.answer()

@dp.callback_query(F.data.startswith("req_vote:"))
async def cb_req_vote(c: CallbackQuery):
    rid = int(c.data.split(":")[1])
    ok = await db.req_vote(rid, c.from_user.id)
    await c.answer("✅ صوّت!" if ok else "صوّت مسبقاً", show_alert=True)

# إثراء بيانات (أدمن): يجلب ISBN/ناشر/غلاف/وصف تلقائياً
@dp.callback_query(F.data == "enrich_ask")
async def cb_enrich_ask(c: CallbackQuery, state: FSMContext):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    await state.set_state(EnrichF.waiting_id)
    await c.message.answer("✨ أرسل <b>رقم الكتاب</b> لإثراء بياناته تلقائياً (ISBN/ناشر/سنة/غلاف).")
    await c.answer()

@dp.message(StateFilter(EnrichF.waiting_id))
async def enrich_do(m: Message, state: FSMContext):
    if not _need_admin(m):
        return
    if not (m.text or "").strip().isdigit():
        return await m.answer("أرسل رقماً.")
    bid = int(m.text.strip())
    b = await db.get_book(bid)
    if not b:
        await state.clear()
        return await m.answer("غير موجود.")
    from metadata import enrich
    info = await enrich(title=b["title"], author=b.get("author", ""), isbn=b.get("isbn", ""))
    if not info:
        await state.clear()
        return await m.answer("تعذّر الإثراء.")
    await db.update_book_meta(bid, **{k: info[k] for k in ("isbn", "publisher", "year", "pages", "cover_url", "tags", "description") if k in info})
    await state.clear()
    nb = await db.get_book(bid)
    if nb.get("cover_url"):
        try:
            await m.answer_photo(nb["cover_url"], caption=U.book_text(nb)[:1000])
            return
        except Exception:
            pass
    await m.answer(U.book_text(nb))

# ---------- v5: كتاب اليوم + تلخيص + اقتباسات + تصدير + فهرسة ----------
@dp.message(Command("today"))
async def cmd_today(m: Message):
    from datetime import date
    b = await db.book_of_day(date.today().isoformat())
    if not b:
        return await m.answer("المكتبة فارغة.")
    fav = await db.is_fav(m.from_user.id, b["id"])
    shelf = await db.shelf_get(m.from_user.id, b["id"])
    await m.answer("📅 <b>كتاب اليوم:</b>\n\n" + U.book_text(b), reply_markup=kb.book_kb(b["id"], fav, shelf, _need_admin(m)))

@dp.callback_query(F.data == "today")
async def cb_today(c: CallbackQuery):
    from datetime import date
    b = await db.book_of_day(date.today().isoformat())
    if not b:
        return await c.answer("فارغة", show_alert=True)
    fav = await db.is_fav(c.from_user.id, b["id"])
    shelf = await db.shelf_get(c.from_user.id, b["id"])
    await safe_edit(c, "📅 <b>كتاب اليوم:</b>\n\n" + U.book_text(b), kb.book_kb(b["id"], fav, shelf, _need_admin(c)))
    await c.answer()

@dp.callback_query(F.data.startswith("sum:"))
async def cb_sum(c: CallbackQuery):
    bid = int(c.data.split(":")[1])
    b = await db.get_book(bid)
    if not b:
        return await c.answer("محذوف", show_alert=True)
    await c.message.answer(U.summarize(b.get("description", "") or b.get("title", "")))
    await c.answer()

@dp.callback_query(F.data.startswith("quote:"))
async def cb_quote_ask(c: CallbackQuery, state: FSMContext):
    bid = int(c.data.split(":")[1])
    await state.update_data(quote_book=bid)
    await state.set_state(QuoteF.waiting_text)
    await c.message.answer(f"💬 أرسل اقتباسك من الكتاب #{bid} (حتى 1000 حرف):")
    await c.answer()

@dp.message(StateFilter(QuoteF.waiting_text))
async def quote_save(m: Message, state: FSMContext):
    data = await state.get_data()
    bid = data.get("quote_book")
    txt = (m.text or "").strip()
    if len(txt) < 5 or len(txt) > 1000:
        return await m.answer("⚠️ من 5 إلى 1000 حرف.")
    qid = await db.quote_add(m.from_user.id, bid, txt)
    await state.clear()
    await m.answer(f"✅ حُفظ اقتباسك #{qid} للكتاب #{bid}.")

@dp.callback_query(F.data == "myquotes")
async def cb_myquotes(c: CallbackQuery):
    qs = await db.my_quotes(c.from_user.id, 8)
    if not qs:
        await safe_edit(c, "💬 لا اقتباسات بعد. افتح كتاباً واضغط 💬 اقتباس.", kb.back_home())
    else:
        t = "💬 <b>اقتباساتك:</b>\n\n" + "\n\n".join(f"• {U.esc(q['text'][:200])}\n<i>{U.esc(q.get('title',''))} #{q['book_id']}</i>" for q in qs)
        await safe_edit(c, t, kb.back_home())
    await c.answer()

@dp.message(Command("export"))
async def cmd_export(m: Message):
    if not config.is_admin(m.from_user.id):
        return await m.answer("للأدمن فقط ⛔")
    import csv, json, tempfile
    books = await db.get_all_books(5000)
    if not books:
        return await m.answer("فارغة.")
    tmp = tempfile.gettempdir()
    jp = os.path.join(tmp, "books.json")
    cp = os.path.join(tmp, "books.csv")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump([{"id": b["id"], "title": b["title"], "author": b.get("author"), "isbn": b.get("isbn"),
                    "year": b.get("year"), "category": b.get("category")} for b in books],
                   f, ensure_ascii=False, indent=1)
    with open(cp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "title", "author", "isbn", "year", "category", "downloads"])
        for b in books:
            w.writerow([b["id"], b["title"], b.get("author"), b.get("isbn"), b.get("year"), b.get("category"), b.get("downloads")])
    from aiogram.types import FSInputFile as _F
    await m.answer_document(_F(jp), caption=f"📤 {len(books)} كتاب JSON")
    await m.answer_document(_F(cp), caption=f"📤 {len(books)} كتاب CSV")

@dp.callback_query(F.data == "export")
async def cb_export(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    await c.message.answer("استخدم /export لاستلام JSON+CSV.")
    await c.answer()

@dp.callback_query(F.data == "reindex")
async def cb_reindex(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    ok = await db.rebuild_fts()
    await c.answer("✅ أُعيد بناء فهرس FTS" if ok else "⚠️ FTS غير متاح، البحث LIKE يعمل", show_alert=True)

@dp.message(Command("reindex"))
async def cmd_reindex(m: Message):
    if not config.is_admin(m.from_user.id):
        return
    ok = await db.rebuild_fts()
    await m.answer("✅ FTS" if ok else "⚠️ LIKE فقط")

# ---------- v6: مراجعات نصية + تعديل الكتب ----------
@dp.callback_query(F.data.startswith("rate_rev:"))
async def cb_rate_rev(c: CallbackQuery, state: FSMContext):
    bid = int(c.data.split(":")[1])
    cur = await db.get_rating(c.from_user.id, bid)
    if not cur:
        await c.message.answer("قيّم بالنجوم أولاً ثم اكتب مراجعتك.")
    else:
        await state.update_data(rev_book=bid, rev_stars=cur["stars"])
        await state.set_state(ReviewF.waiting_text)
        await c.message.answer("✍️ أرسل مراجعتك النصية (حتى 1000 حرف، أو - للإلغاء):")
    await c.answer()

@dp.message(StateFilter(ReviewF.waiting_text))
async def rev_save(m: Message, state: FSMContext):
    if (m.text or "").strip() == "-":
        await state.clear()
        return await m.answer("أُلغيت المراجعة.")
    data = await state.get_data()
    txt = (m.text or "").strip()
    if len(txt) < 5 or len(txt) > 1000:
        return await m.answer("⚠️ من 5 إلى 1000 حرف.")
    await db.rate_set(m.from_user.id, data["rev_book"], data["rev_stars"], txt)
    await state.clear()
    await m.answer(f"✅ نُشرت مراجعتك للكتاب #{data['rev_book']}. شكراً لمشاركتك!")

EDIT_FIELDS = {"title": "العنوان", "author": "المؤلف", "category": "التصنيف", "tags": "الوسوم (بفواصل)", "description": "الوصف"}

@dp.callback_query(F.data.startswith("edit:"))
async def cb_edit_menu(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    bid = int(c.data.split(":")[1])
    rows = [[InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"editf:{k}:{bid}")] for k, label in EDIT_FIELDS.items()]
    rows.append([InlineKeyboardButton(text="🔙 للكتاب", callback_data=f"book:{bid}")])
    await safe_edit(c, f"✏️ تعديل الكتاب #{bid} — اختر الحقل:", InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()

@dp.callback_query(F.data.startswith("editf:"))
async def cb_edit_field(c: CallbackQuery, state: FSMContext):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    _, field, sid = c.data.split(":")
    await state.update_data(edit_book=int(sid), edit_field=field)
    await state.set_state(EditF.waiting_value)
    await c.message.answer(f"أرسل القيمة الجديدة لـ <b>{EDIT_FIELDS[field]}</b>:")
    await c.answer()

@dp.message(StateFilter(EditF.waiting_value))
async def edit_save(m: Message, state: FSMContext):
    if not _need_admin(m):
        return
    data = await state.get_data()
    bid, field = data["edit_book"], data["edit_field"]
    val = (m.text or "").strip()[:800]
    if len(val) < 2:
        return await m.answer("⚠️ قيمة قصيرة جداً.")
    if field == "category":
        await db.set_book_category(bid, val)
    else:
        await db.update_book_meta(bid, **{field: val})
    await state.clear()
    b = await db.get_book(bid)
    fav = await db.is_fav(m.from_user.id, bid)
    shelf = await db.shelf_get(m.from_user.id, bid)
    await m.answer("✅ تم التعديل:\n\n" + U.book_text(b), reply_markup=kb.book_kb(bid, fav, shelf, True))

# ---------- النشر اليومي في القناة: كتاب + PDF مباشر ----------
_BOT_UNAME = ""

async def post_channel() -> str:
    ch = await db.meta_get("post_channel", "")
    return ch or getattr(config, "LIB_CHANNEL", "")

def format_post(b: dict) -> str:
    stars = f"⭐ {b.get('rating_avg', 0)} ({b.get('rating_cnt', 0)})" if b.get("rating_cnt") else "⭐ جديد"
    tag = "#" + str(b.get("category") or "عام").replace(" ", "_")
    lines = [
        f"📚 <b>كتاب اليوم</b> {tag}",
        "",
        f"📖 <b>{U.esc(b.get('title'))}</b>",
        f"✍️ {U.esc(b.get('author'))}",
        f"{stars} | ⬇️ {b.get('downloads', 0)}",
    ]
    if b.get("year") or b.get("pages"):
        lines.append(f"📅 {b.get('year') or '?'} | 📄 {b.get('pages') or '?'} صفحة")
    desc = (b.get("description") or "")[:400]
    if desc:
        lines += ["", U.esc(desc)]
    if _BOT_UNAME:
        lines += ["", f"📥 التحميل + التفاصيل: https://t.me/{_BOT_UNAME}?start=book_{b['id']}"]
    return "\n".join(lines)[:1000]

async def send_daily_post(channel: str, book: dict | None = None) -> str | None:
    """يعيد None عند النجاح أو نص سبب الفشل (يُعرض للأدمن)."""
    b = book or await db.pick_daily_book()
    if not b:
        return "المكتبة فارغة"
    caption = format_post(b)
    try:
        # الغلاف أولاً (إن وجد) ثم ملف PDF للتنزيل المباشر داخل تلغرام
        if b.get("cover_url"):
            try:
                await bot.send_photo(channel, b["cover_url"], caption=caption)
            except Exception:
                await bot.send_message(channel, caption)
        elif not b.get("file_id"):
            await bot.send_message(channel, caption + (f"\n\n🔗 {b.get('source_url')}" if b.get("source_url") else ""))
        if b.get("file_id"):
            await bot.send_document(channel, b["file_id"], caption=f"📥 {b['title']}"[:1000])
        return None
    except Exception as e:
        log.warning("daily post failed: %s", e)
        s = str(e)
        if "chat not found" in s:
            return "القناة غير موجودة — تحقق من الاسم (أو استخدم -100... للخاصة)"
        if "bot was kicked" in s or "not enough rights" in s or "CHAT_WRITE_FORBIDDEN" in s:
            return "البوت ليس مشرفاً بصلاحية النشر في القناة"
        return f"خطأ تلغرام: {s[:120]}"

async def daily_loop():
    import datetime
    while True:
        try:
            now = datetime.datetime.now()
            nxt = now.replace(hour=config.POST_HOUR % 24, minute=0, second=0, microsecond=0)
            if nxt <= now:
                nxt += datetime.timedelta(days=1)
            await asyncio.sleep((nxt - now).total_seconds())
            ch = await post_channel()
            auto = await db.meta_get("autopost", "on")
            if ch and auto != "off":
                err = await send_daily_post(ch)
                log.info("daily post: %s", "sent" if err is None else f"failed: {err}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("daily loop: %s", e)
            await asyncio.sleep(3600)

@dp.message(Command("postnow"))
async def cmd_postnow(m: Message):
    if not config.is_admin(m.from_user.id):
        return await m.answer("للأدمن فقط ⛔")
    ch = await post_channel()
    if not ch:
        return await m.answer("⚠️ لا قناة مربوطة. استخدم: <code>/setchannel @قناتك</code> (والبوت مشرف فيها)")
    parts = m.text.split()
    book = await db.get_book(int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else None
    err = await send_daily_post(ch, book)
    await m.answer("✅ نُشر في القناة." if err is None else f"❌ {err}")

@dp.message(Command("setchannel"))
async def cmd_setchannel(m: Message):
    if not config.is_admin(m.from_user.id):
        return await m.answer("للأدمن فقط ⛔")
    parts = m.text.split()
    if len(parts) < 2:
        return await m.answer("اكتب: <code>/setchannel @اسم_القناة</code> أو <code>/setchannel -100xxxx</code> للخاصة")
    raw = parts[1].strip()
    # يقبل: @name أو رابط t.me/name أو ID رقمي -100... (للقنوات الخاصة)
    if raw.startswith("https://t.me/") or raw.startswith("t.me/"):
        raw = "@" + raw.rstrip("/").split("/")[-1].split("?")[0]
    if not (raw.startswith("@") or (raw.startswith("-100") and raw[1:].isdigit())):
        return await m.answer("⚠️ الصيغة: <code>@اسم_القناة</code> (عامة) أو <code>-100xxxx</code> (خاصة)")
    # تحقق فوري: موجودة؟ البوت مشرف؟
    try:
        chat = await bot.get_chat(raw)
        mem = await bot.get_chat_member(raw, (await bot.get_me()).id)
        if mem.status != "administrator":
            return await m.answer(f"⚠️ أرى القناة «{U.esc(getattr(chat, 'title', raw))}» لكن البوت <b>ليس مشرفاً</b>.\nرقيه مشرفاً (صلاحية النشر) ثم أعد الأمر.")
    except Exception:
        return await m.answer("⚠️ لم أجد القناة.\nتأكد: الاسم صحيح + القناة <b>عامة</b>، أو استخدم <code>-100...</code> للخاصة.")
    await db.meta_set("post_channel", raw)
    await m.answer(f"✅ تم ربط القناة: {raw}\nالنشر اليومي الساعة {config.POST_HOUR}:00. جرّب /postnow")

@dp.message(Command("autopost"))
async def cmd_autopost(m: Message):
    if not config.is_admin(m.from_user.id):
        return await m.answer("للأدمن فقط ⛔")
    parts = m.text.split()
    if len(parts) > 1 and parts[1] in ("on", "off"):
        await db.meta_set("autopost", parts[1])
    st = await db.meta_get("autopost", "on")
    ch = await post_channel()
    await m.answer(f"⏰ النشر اليومي: <b>{'مفعّل' if st != 'off' else 'معطّل'}</b>\n📣 القناة: {ch or '—'}\n(/autopost on|off)")

@dp.callback_query(F.data == "postnow")
async def cb_postnow(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    ch = await post_channel()
    if not ch:
        await c.message.answer("⚠️ اربط قناة أولاً: /setchannel @قناتك")
    else:
        err = await send_daily_post(ch)
        await c.message.answer("✅ نُشر." if err is None else f"❌ {err}")
    await c.answer()

@dp.callback_query(F.data == "autopost")
async def cb_autopost(c: CallbackQuery):
    if not _need_admin(c):
        return await c.answer("للأدمن فقط", show_alert=True)
    cur = await db.meta_get("autopost", "on")
    new = "off" if cur != "off" else "on"
    await db.meta_set("autopost", new)
    ch = await post_channel()
    await safe_edit(c, f"⏰ النشر اليومي: <b>{'مفعّل ✅' if new != 'off' else 'معطّل ❌'}</b>\n📣 {ch or 'لا قناة'} — الساعة {config.POST_HOUR}:00", kb.admin_menu())
    await c.answer()

@dp.error()
async def err_handler(event):
    log.exception("handler error: %s", event)
    return True

async def main():
    errs = config.validate()
    if bot is None:
        print("❌ BOT_TOKEN مفقود في .env")
        return
    for e in errs:
        print("⚠️", e)
    if "غير صالح" in " ".join(errs):
        return
    await db.init_db()
    try:
        me = await bot.get_me()
        global _BOT_UNAME
        _BOT_UNAME = me.username or ""
    except Exception:
        pass
    await bot.delete_webhook(drop_pending_updates=True)
    # قارئ WebApp يعمل في الوضعين: مدمج مع Webhook أو كخدمة جانبية مع Polling
    from webapp_server import create_app as _reader_app
    reader = _reader_app()
    if config.MODE == "webhook":
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        from aiohttp import web

        async def _on_startup(_app):
            asyncio.create_task(daily_loop())

        reader.on_startup.append(_on_startup)
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=None).register(reader, path=config.WEBHOOK_PATH)
        setup_application(reader, dp, bot=bot)
        await bot.set_webhook(f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH}", drop_pending_updates=True)
        print(f"🌐 Webhook + Reader on port {config.PORT}")
        web.run_app(reader, host="0.0.0.0", port=config.PORT)
        return
    # polling + reader جانبي (لا يوقف البوت عند فشل المنفذ)
    async def _serve_reader():
        from aiohttp.web import AppRunner, TCPSite
        try:
            runner = AppRunner(reader)
            await runner.setup()
            await TCPSite(runner, "0.0.0.0", config.PORT).start()
            print(f"📖 Reader on port {config.PORT}/app/")
            await asyncio.Event().wait()
        except OSError as e:
            log.warning("reader port busy: %s", e)
    print("📚 Bot v5 started (polling + FTS)...")
    await asyncio.gather(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()),
        _serve_reader(),
        daily_loop(),
    )

if __name__ == "__main__":
    asyncio.run(main())
