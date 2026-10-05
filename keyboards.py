from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import config as _cfg

def main_menu(is_admin: bool = False):
    rows = [
        [InlineKeyboardButton(text="📚 التصنيفات", callback_data="cats")],
        [InlineKeyboardButton(text="🔍 بحث مكتبة", callback_data="ask_local"),
         InlineKeyboardButton(text="🌐 بحث إنترنت", callback_data="ask_net")],
        [InlineKeyboardButton(text="⭐ الأكثر تحميلاً", callback_data="popular"),
         InlineKeyboardButton(text="🆕 الأحدث", callback_data="recent")],
        [InlineKeyboardButton(text="🎲 كتاب عشوائي", callback_data="random"),
         InlineKeyboardButton(text="📖 مكتبتي", callback_data="mybooks")],
        [InlineKeyboardButton(text="📅 كتاب اليوم", callback_data="today"),
         InlineKeyboardButton(text="💬 اقتباساتي", callback_data="myquotes")],
        [InlineKeyboardButton(text="❤️ مفضلتي", callback_data="myfavs"),
         InlineKeyboardButton(text="🕘 سجلّي", callback_data="history")],
        [InlineKeyboardButton(text="📝 طلب كتاب", callback_data="req_list"),
         InlineKeyboardButton(text="ℹ️ مساعدة", callback_data="help")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 لوحة الأدمن", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إضافة كتاب", callback_data="addbook")],
        [InlineKeyboardButton(text="📋 إدارة الكتب", callback_data="manage:0")],
        [InlineKeyboardButton(text="🗑 حذف برقم", callback_data="delbook"),
         InlineKeyboardButton(text="✨ إثراء بيانات", callback_data="enrich_ask")],
        [InlineKeyboardButton(text="📝 الطلبات", callback_data="req_list"),
         InlineKeyboardButton(text="📊 إحصائيات", callback_data="stats")],
        [InlineKeyboardButton(text="🔄 فهرسة البحث", callback_data="reindex"),
         InlineKeyboardButton(text="📤 تصدير", callback_data="export")],
        [InlineKeyboardButton(text="💾 نسخة احتياطية", callback_data="backup"),
         InlineKeyboardButton(text="📢 بث جماعي", callback_data="broadcast")],
        [InlineKeyboardButton(text="📣 نشر الآن", callback_data="postnow"),
         InlineKeyboardButton(text="⏰ اليومي", callback_data="autopost")],
        [InlineKeyboardButton(text="🔙 الرئيسية", callback_data="home")],
    ])

def categories_kb(cats: list[dict]):
    rows = []
    for c in cats:
        rows.append([InlineKeyboardButton(text=f"📂 {c['name']} ({c['cnt']})", callback_data=f"cat:{c['id']}:0")])
    rows.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def cat_choice_kb(cats: list[dict]):
    rows = []
    for c in cats[:10]:
        rows.append([InlineKeyboardButton(text=c["name"], callback_data=f"pickcat:{c['id']}")])
    rows.append([InlineKeyboardButton(text="🆕 تصنيف جديد", callback_data="pickcat:new")])
    rows.append([InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _book_label(b: dict) -> str:
    t = f"📖 {b['title'][:35]}"
    if b.get("author"):
        t += f" - {b['author'][:18]}"
    return t

def books_kb(books, cat_id=None, offset=0, has_more=False, back="cats"):
    rows = []
    for b in books:
        rows.append([InlineKeyboardButton(text=_book_label(b), callback_data=f"book:{b['id']}")])
    nav = []
    if cat_id is not None:
        if offset > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"cat:{cat_id}:{max(0, offset - 8)}"))
        if has_more:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"cat:{cat_id}:{offset + 8}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 رجوع", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def search_kb(books, offset=0, has_more=False):
    rows = []
    for b in books:
        rows.append([InlineKeyboardButton(text=_book_label(b), callback_data=f"book:{b['id']}")])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sl:{max(0, offset - 10)}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="▶️ المزيد", callback_data=f"sl:{offset + 10}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def manage_kb(books, offset=0, has_more=False):
    rows = []
    for b in books:
        rows.append([InlineKeyboardButton(text=f"#{b['id']} {b['title'][:30]}", callback_data=f"book:{b['id']}")])
    if books:
        rows.append([InlineKeyboardButton(text=f"🗑 #{b['id']}", callback_data=f"mdel:{b['id']}:{offset}") for b in books[:4]])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"manage:{max(0, offset - 8)}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"manage:{offset + 8}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 لوحة الأدمن", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

SHELVES = {"want": "📥 أريد", "reading": "📖 أقرأ", "done": "✅ أنهيت"}

def book_kb(book_id: int, fav: bool = False, shelf: str | None = None, admin: bool = False):
    shelf_row = [
        InlineKeyboardButton(
            text=f"{label}{' ✓' if shelf == key else ''}",
            callback_data=f"shelf:{key}:{book_id}")
        for key, label in SHELVES.items()
    ]
    rows = [
        [InlineKeyboardButton(text="⬇️ تحميل", callback_data=f"dl:{book_id}"),
         InlineKeyboardButton(text="⭐ مفضل" if not fav else "💔 إزالة", callback_data=f"fav:{book_id}")],
        shelf_row,
        [InlineKeyboardButton(text="⭐ قيّم", callback_data=f"rate:{book_id}"),
         InlineKeyboardButton(text="📝 تقدّمي", callback_data=f"prog:{book_id}")],
        [InlineKeyboardButton(text="🧾 تلخيص", callback_data=f"sum:{book_id}"),
         InlineKeyboardButton(text="💬 اقتباس", callback_data=f"quote:{book_id}")],
        [InlineKeyboardButton(text="🔗 مشاركة", switch_inline_query=f"book:{book_id}"),
         InlineKeyboardButton(text="🔙 الرئيسية", callback_data="home")],
    ]
    if admin:
        rows.insert(4, [InlineKeyboardButton(text="✏️ تعديل (أدمن)", callback_data=f"edit:{book_id}")])
    if getattr(_cfg, "WEBAPP_URL", ""):
        try:
            rows.insert(0, [InlineKeyboardButton(text="📖 قراءة WebApp", web_app=WebAppInfo(url=f"{_cfg.WEBAPP_URL}?book={book_id}"))])
        except Exception:
            pass
    return InlineKeyboardMarkup(inline_keyboard=rows)

def rate_kb(book_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'⭐' * i}", callback_data=f"rate_set:{book_id}:{i}") for i in (1, 2, 3)],
        [InlineKeyboardButton(text=f"{'⭐' * i}", callback_data=f"rate_set:{book_id}:{i}") for i in (4, 5)],
        [InlineKeyboardButton(text="✍️ كتابة مراجعة", callback_data=f"rate_rev:{book_id}")],
        [InlineKeyboardButton(text="🔙 للكتاب", callback_data=f"book:{book_id}")],
    ])

def mybooks_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 أريد القراءة", callback_data="shelf_list:want"),
         InlineKeyboardButton(text="📖 أقرأ الآن", callback_data="shelf_list:reading")],
        [InlineKeyboardButton(text="✅ أنهيت", callback_data="shelf_list:done"),
         InlineKeyboardButton(text="❤️ المفضلة", callback_data="myfavs")],
        [InlineKeyboardButton(text="🔙 الرئيسية", callback_data="home")],
    ])

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تأكيد الحفظ", callback_data="confirm_add")],
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_add")],
    ])

def back_home():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 الرئيسية", callback_data="home")]
    ])

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_add")]
    ])
