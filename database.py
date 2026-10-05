"""SQLite v5: FTS5 + WAL + اقتباسات + كتاب اليوم + تصدير. ترحيل آمن من v4."""
import aiosqlite
import re
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT DEFAULT 'غير معروف',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    description TEXT DEFAULT '',
    file_id TEXT NOT NULL,
    file_type TEXT DEFAULT 'pdf',
    file_name TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0,
    lang TEXT DEFAULT 'ar',
    added_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, book_id)
);
CREATE TABLE IF NOT EXISTS downloads_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shelves (
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    shelf TEXT NOT NULL CHECK (shelf IN ('want','reading','done')),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, book_id)
);
CREATE TABLE IF NOT EXISTS ratings (
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
    review TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, book_id)
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    author TEXT DEFAULT '',
    votes INTEGER DEFAULT 1,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS request_votes (
    request_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (request_id, user_id)
);
CREATE TABLE IF NOT EXISTS progress (
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    page INTEGER DEFAULT 0,
    total_pages INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, book_id)
);
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_cat ON books(category_id);
CREATE INDEX IF NOT EXISTS idx_books_dl ON books(downloads DESC);
CREATE INDEX IF NOT EXISTS idx_log_user ON downloads_log(user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_shelf_user ON shelves(user_id, shelf);
CREATE INDEX IF NOT EXISTS idx_rate_book ON ratings(book_id);
CREATE INDEX IF NOT EXISTS idx_quotes_user ON quotes(user_id, id DESC);
"""

FTS_SETUP = """
CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
    title, author, tags, description,
    content='books', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
    INSERT INTO books_fts(rowid, title, author, tags, description)
    VALUES (new.id, new.title, new.author, COALESCE(new.tags,''), COALESCE(new.description,''));
END;
CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
    INSERT INTO books_fts(books_fts, rowid, title, author, tags, description)
    VALUES ('delete', old.id, old.title, old.author, COALESCE(old.tags,''), COALESCE(old.description,''));
END;
CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
    INSERT INTO books_fts(books_fts, rowid, title, author, tags, description)
    VALUES ('delete', old.id, old.title, old.author, COALESCE(old.tags,''), COALESCE(old.description,''));
    INSERT INTO books_fts(rowid, title, author, tags, description)
    VALUES (new.id, new.title, new.author, COALESCE(new.tags,''), COALESCE(new.description,''));
END;
"""

NEW_BOOK_COLS = {
    "isbn": "TEXT DEFAULT ''",
    "publisher": "TEXT DEFAULT ''",
    "year": "INTEGER",
    "pages": "INTEGER DEFAULT 0",
    "cover_url": "TEXT DEFAULT ''",
    "tags": "TEXT DEFAULT ''",
    "file_unique_id": "TEXT DEFAULT ''",
    "source_url": "TEXT DEFAULT ''",
}

async def _has_column(db, table: str, col: str) -> bool:
    cur = await db.execute(f"PRAGMA table_info({table})")
    return col in [r[1] for r in await cur.fetchall()]

async def _has_table(db, name: str) -> bool:
    cur = await db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','virtual table') AND name=?", (name,))
    return bool(await cur.fetchone())

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='books'")
        old_exists = await cur.fetchone()
        if old_exists and await _has_column(db, "books", "category") and not await _has_column(db, "books", "category_id"):
            await db.execute("ALTER TABLE books RENAME TO books_old")
            await db.executescript(SCHEMA)
            await db.execute("""
                INSERT INTO categories (name)
                SELECT DISTINCT category FROM books_old WHERE category IS NOT NULL AND category <> ''
            """)
            await db.execute("""
                INSERT INTO books (id,title,author,category_id,description,file_id,file_type,downloads,lang,added_by,created_at)
                SELECT o.id,o.title,o.author,c.id,o.description,o.file_id,
                       COALESCE(o.file_type,'pdf'),COALESCE(o.downloads,0),COALESCE(o.lang,'ar'),
                       o.added_by,o.created_at
                FROM books_old o LEFT JOIN categories c ON c.name=o.category
            """)
            await db.execute("DROP TABLE books_old")
            await db.commit()
        else:
            await db.executescript(SCHEMA)
            await db.commit()
        for col, ddl in NEW_BOOK_COLS.items():
            if not await _has_column(db, "books", col):
                await db.execute(f"ALTER TABLE books ADD COLUMN {col} {ddl}")
        await db.commit()
        # FTS5: قد لا يتوفر في بعض بيئات SQLite — تجاهل الفشل بهدوء
        try:
            await db.executescript(FTS_SETUP)
            await db.commit()
            await rebuild_fts(db)
        except Exception:
            pass

async def rebuild_fts(db=None):
    """إعادة بناء فهرس البحث. يعيد True عند النجاح."""
    own = db is None
    if own:
        db = await aiosqlite.connect(DB_PATH)
    try:
        if not await _has_table(db, "books_fts"):
            await db.executescript(FTS_SETUP)
        await db.execute("INSERT INTO books_fts(books_fts) VALUES('rebuild')")
        await db.commit()
        return True
    except Exception:
        return False
    finally:
        if own:
            await db.close()

async def add_user(user_id: int, username: str | None, full_name: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?,?,?)",
            (user_id, username, full_name),
        )
        await db.commit()

async def ensure_category(name: str) -> int:
    name = (name or "عام").strip()[:40] or "عام"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        await db.commit()
        cur = await db.execute("SELECT id FROM categories WHERE name=?", (name,))
        return (await cur.fetchone())[0]

async def get_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT c.id, c.name, COUNT(b.id) AS cnt
            FROM categories c LEFT JOIN books b ON b.category_id=c.id
            GROUP BY c.id ORDER BY cnt DESC, c.name
        """)
        return [dict(r) for r in await cur.fetchall()]

async def add_book(title, author, category_name, description, file_id,
                   file_type="pdf", file_name="", file_size=0, lang="ar", added_by=None,
                   file_unique_id="", source_url=""):
    if file_unique_id:
        dup = await find_duplicate(file_unique_id)
        if dup:
            return dup["id"]
    if source_url:
        dup = await find_by_source(source_url)
        if dup:
            return dup["id"]
    cat_id = await ensure_category(category_name)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO books (title,author,category_id,description,file_id,file_type,file_name,file_size,lang,added_by,file_unique_id,source_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, author, cat_id, description, file_id, file_type, file_name, file_size, lang, added_by, file_unique_id, source_url),
        )
        await db.commit()
        return cur.lastrowid

async def find_duplicate(file_unique_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " WHERE b.file_unique_id=? AND b.file_unique_id<>''", (file_unique_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def find_by_source(source_url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " WHERE b.source_url=? AND b.source_url<>''", (source_url,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def update_book_meta(book_id: int, **fields):
    allowed = {"isbn", "publisher", "year", "pages", "cover_url", "tags", "description", "title", "author", "lang"}
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not data:
        return False
    sets = ", ".join(f"{k}=?" for k in data)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(f"UPDATE books SET {sets} WHERE id=?", (*data.values(), book_id))
        await db.commit()
        return cur.rowcount > 0

def _book_select():
    return """SELECT b.*, c.name AS category FROM books b
              LEFT JOIN categories c ON c.id=b.category_id"""

def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

def _fts_query(query: str) -> str | None:
    toks = re.findall(r"[\w\u0600-\u06FF]{2,}", query or "")
    toks = toks[:6]
    if not toks:
        return None
    return " OR ".join(f'"{t}"*' for t in toks)

async def fts_search(query: str, limit: int = 10, offset: int = 0):
    """بحث FTS5 مرتب بـ bm25. يعيد [] عند عدم التوفر أو خطأ الصياغة."""
    fq = _fts_query(query)
    if not fq:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        if not await _has_table(db, "books_fts"):
            return []
        db.row_factory = aiosqlite.Row
        try:
            cur = await db.execute(
                _book_select() + " JOIN books_fts f ON f.rowid=b.id WHERE books_fts MATCH ? ORDER BY bm25(books_fts) LIMIT ? OFFSET ?",
                (fq, limit, offset),
            )
            return [dict(r) for r in await cur.fetchall()]
        except Exception:
            return []

async def search_books(query: str, limit: int = 10, offset: int = 0):
    if query and len(query.strip()) >= 2:
        hits = await fts_search(query, limit, offset)
        if hits:
            return hits
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            _book_select() + " WHERE b.title LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\' ORDER BY b.downloads DESC LIMIT ? OFFSET ?",
            (_like(query), _like(query), limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]

async def search_advanced(query: str = "", lang: str | None = None, year: int | None = None,
                          tag: str | None = None, limit: int = 10, offset: int = 0):
    conds, args = [], []
    if query:
        conds.append("(b.title LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\' OR b.tags LIKE ? ESCAPE '\\')")
        args += [_like(query), _like(query), _like(query)]
    if lang:
        conds.append("b.lang=?")
        args.append(lang)
    if year:
        conds.append("b.year=?")
        args.append(year)
    if tag:
        conds.append("b.tags LIKE ? ESCAPE '\\'")
        args.append(_like(tag))
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + where + " ORDER BY b.downloads DESC LIMIT ? OFFSET ?",
                               (*args, limit, offset))
        return [dict(r) for r in await cur.fetchall()]

async def get_by_isbn(isbn: str):
    isbn = "".join(ch for ch in (isbn or "") if ch.isdigit() or ch.lower() == "x")
    if not isbn:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " WHERE REPLACE(REPLACE(b.isbn,'-',''),' ','')=? LIMIT 10", (isbn,))
        return [dict(r) for r in await cur.fetchall()]

async def get_by_author(author: str, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " WHERE b.author LIKE ? ESCAPE '\\' ORDER BY b.downloads DESC LIMIT ?",
                               (_like(author), limit))
        return [dict(r) for r in await cur.fetchall()]

async def get_random_book():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " ORDER BY RANDOM() LIMIT 1")
        row = await cur.fetchone()
        return dict(row) if row else None

async def book_of_day(date_str: str):
    """كتاب اليوم حتمي حسب التاريخ (YYYY-MM-DD)."""
    import hashlib
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT COUNT(*) FROM books")
        n = (await cur.fetchone())[0]
        if not n:
            return None
        idx = int(hashlib.sha256(date_str.encode()).hexdigest(), 16) % n
        cur = await db.execute(_book_select() + " ORDER BY b.id LIMIT 1 OFFSET ?", (idx,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def get_all_books(limit: int = 5000):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " ORDER BY b.id LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]

async def get_books_by_category(cat_id: int, limit: int = 20, offset: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            _book_select() + " WHERE b.category_id=? ORDER BY b.id DESC LIMIT ? OFFSET ?",
            (cat_id, limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]

async def list_books(limit: int = 8, offset: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " ORDER BY b.id DESC LIMIT ? OFFSET ?", (limit, offset))
        return [dict(r) for r in await cur.fetchall()]

async def get_book(book_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " WHERE b.id=?", (book_id,))
        row = await cur.fetchone()
        if not row:
            return None
        d = dict(row)
        cur2 = await db.execute("SELECT COALESCE(AVG(stars),0), COUNT(*) FROM ratings WHERE book_id=?", (book_id,))
        avg, cnt = await cur2.fetchone()
        d["rating_avg"] = round(avg or 0, 1)
        d["rating_cnt"] = cnt or 0
        return d

async def increment_download(book_id: int, user_id: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE books SET downloads=downloads+1 WHERE id=?", (book_id,))
        if user_id:
            await db.execute("INSERT INTO downloads_log (user_id, book_id) VALUES (?,?)", (user_id, book_id))
        await db.commit()

async def get_history(user_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            _book_select() + " JOIN downloads_log l ON l.book_id=b.id WHERE l.user_id=? ORDER BY l.id DESC LIMIT ?",
            (user_id, limit),
        )
        seen, out = set(), []
        for r in await cur.fetchall():
            d = dict(r)
            if d["id"] not in seen:
                seen.add(d["id"])
                out.append(d)
        return out

async def get_popular(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " ORDER BY b.downloads DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]

async def get_recent(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_book_select() + " ORDER BY b.id DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]

async def delete_book(book_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM books WHERE id=?", (book_id,))
        await db.execute("DELETE FROM favorites WHERE book_id=?", (book_id,))
        await db.execute("DELETE FROM shelves WHERE book_id=?", (book_id,))
        await db.execute("DELETE FROM ratings WHERE book_id=?", (book_id,))
        await db.commit()
        return cur.rowcount > 0

async def shelf_set(user_id: int, book_id: int, shelf: str):
    assert shelf in ("want", "reading", "done")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO shelves (user_id, book_id, shelf) VALUES (?,?,?)",
                         (user_id, book_id, shelf))
        await db.commit()

async def shelf_get(user_id: int, book_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT shelf FROM shelves WHERE user_id=? AND book_id=?", (user_id, book_id))
        row = await cur.fetchone()
        return row[0] if row else None

async def my_shelves(user_id: int, shelf: str, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            _book_select() + " JOIN shelves s ON s.book_id=b.id WHERE s.user_id=? AND s.shelf=? ORDER BY s.updated_at DESC LIMIT ?",
            (user_id, shelf, limit))
        return [dict(r) for r in await cur.fetchall()]

async def rate_set(user_id: int, book_id: int, stars: int, review: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO ratings (user_id, book_id, stars, review) VALUES (?,?,?,?)",
                         (user_id, book_id, stars, review[:1000]))
        await db.commit()

async def get_reviews(book_id: int, limit: int = 5):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT stars, review FROM ratings WHERE book_id=? AND review<>'' ORDER BY updated_at DESC LIMIT ?", (book_id, limit))
        return [{"stars": r[0], "review": r[1]} for r in await cur.fetchall()]

async def req_add(user_id: int, title: str, author: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO requests (user_id, title, author) VALUES (?,?,?)",
                               (user_id, title[:150], author[:100]))
        await db.commit()
        return cur.lastrowid

async def req_list_open(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM requests WHERE status='open' ORDER BY votes DESC, id DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]

async def req_vote(request_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM request_votes WHERE request_id=? AND user_id=?", (request_id, user_id))
        if await cur.fetchone():
            return False
        await db.execute("INSERT INTO request_votes (request_id, user_id) VALUES (?,?)", (request_id, user_id))
        await db.execute("UPDATE requests SET votes=votes+1 WHERE id=?", (request_id,))
        await db.commit()
        return True

async def req_find_match(title: str, limit: int = 5):
    """طلبات مفتوحة يطابق عنوانها الكتاب الجديد (لإشعار طالبيها)."""
    words = [w for w in title.split() if len(w) > 3][:4]
    if not words:
        return []
    cond = " OR ".join(["title LIKE ? ESCAPE '\\'"] * len(words))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            f"SELECT * FROM requests WHERE status='open' AND ({cond}) ORDER BY votes DESC LIMIT ?",
            (*[_like(w) for w in words], limit))
        return [dict(r) for r in await cur.fetchall()]

async def req_fulfill(request_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE requests SET status='done' WHERE id=?", (request_id,))
        await db.commit()

async def req_voters(request_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM request_votes WHERE request_id=?", (request_id,))
        users = [r[0] for r in await cur.fetchall()]
        cur = await db.execute("SELECT user_id FROM requests WHERE id=?", (request_id,))
        row = await cur.fetchone()
        if row and row[0] not in users:
            users.append(row[0])
        return users

async def get_rating(user_id: int, book_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT stars, review FROM ratings WHERE user_id=? AND book_id=?", (user_id, book_id))
        row = await cur.fetchone()
        return {"stars": row[0], "review": row[1]} if row else None

async def set_book_category(book_id: int, category_name: str) -> bool:
    cat_id = await ensure_category(category_name)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("UPDATE books SET category_id=? WHERE id=?", (cat_id, book_id))
        await db.commit()
        return cur.rowcount > 0

async def progress_set(user_id: int, book_id: int, page: int, total: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO progress (user_id, book_id, page, total_pages) VALUES (?,?,?,?)",
                         (user_id, book_id, page, total))
        await db.commit()

async def progress_get(user_id: int, book_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT page, total_pages FROM progress WHERE user_id=? AND book_id=?", (user_id, book_id))
        row = await cur.fetchone()
        return {"page": row[0], "total": row[1]} if row else None

async def quote_add(user_id: int, book_id: int, text: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO quotes (user_id, book_id, text) VALUES (?,?,?)",
                               (user_id, book_id, text[:1000]))
        await db.commit()
        return cur.lastrowid

async def quotes_of_book(book_id: int, limit: int = 5):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM quotes WHERE book_id=? ORDER BY id DESC LIMIT ?", (book_id, limit))
        return [dict(r) for r in await cur.fetchall()]

async def my_quotes(user_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT q.*, b.title FROM quotes q LEFT JOIN books b ON b.id=q.book_id WHERE q.user_id=? ORDER BY q.id DESC LIMIT ?",
            (user_id, limit))
        return [dict(r) for r in await cur.fetchall()]

async def meta_get(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM meta WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default

async def meta_set(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
        await db.commit()

async def pick_daily_book():
    """كتاب اليوم: يفضل ملفاً حقيقياً (PDF مباشر) ثم أي كتاب."""
    from datetime import date
    import hashlib
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT COUNT(*) FROM books WHERE file_id<>''")
        n = (await cur.fetchone())[0]
        if n:
            idx = int(hashlib.sha256(("pdf" + today).encode()).hexdigest(), 16) % n
            cur = await db.execute(_book_select() + " WHERE b.file_id<>'' ORDER BY b.id LIMIT 1 OFFSET ?", (idx,))
            row = await cur.fetchone()
            if row:
                d = dict(row)
                cur2 = await db.execute("SELECT COALESCE(AVG(stars),0), COUNT(*) FROM ratings WHERE book_id=?", (d["id"],))
                avg, cnt = await cur2.fetchone()
                d["rating_avg"] = round(avg or 0, 1)
                d["rating_cnt"] = cnt or 0
                return d
    return await book_of_day(today)

async def toggle_fav(user_id: int, book_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM favorites WHERE user_id=? AND book_id=?", (user_id, book_id))
        if await cur.fetchone():
            await db.execute("DELETE FROM favorites WHERE user_id=? AND book_id=?", (user_id, book_id))
            await db.commit()
            return False
        await db.execute("INSERT OR IGNORE INTO favorites (user_id, book_id) VALUES (?,?)", (user_id, book_id))
        await db.commit()
        return True

async def is_fav(user_id: int, book_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM favorites WHERE user_id=? AND book_id=?", (user_id, book_id))
        return bool(await cur.fetchone())

async def get_favs(user_id: int, limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            _book_select() + " JOIN favorites f ON f.book_id=b.id WHERE f.user_id=? ORDER BY f.created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]

async def get_all_user_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        return [r[0] for r in await cur.fetchall()]

async def count_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        b = (await (await db.execute("SELECT COUNT(*) FROM books")).fetchone())[0]
        u = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        d = (await (await db.execute("SELECT COALESCE(SUM(downloads),0) FROM books")).fetchone())[0]
        c = (await (await db.execute("SELECT COUNT(*) FROM categories")).fetchone())[0]
        cur = await db.execute("""
            SELECT c.name, COUNT(b.id) AS cnt FROM categories c
            LEFT JOIN books b ON b.category_id=c.id GROUP BY c.id ORDER BY cnt DESC LIMIT 5""")
        top = await cur.fetchall()
        return {"books": b, "users": u, "downloads": d, "cats": c, "top": [(r[0], r[1]) for r in top]}
