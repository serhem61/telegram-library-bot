"""إعادة تصنيف كل كتب المكتبة احترافياً من الوسوم المخزنة."""
import asyncio
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import database as db
from categorize import classify


async def main():
    await db.init_db()
    books = await db.get_all_books(100000)
    fixed = 0
    for b in books:
        tags = [t.strip() for t in (b.get("tags") or "").split(",") if t.strip()]
        cat = classify(tags, [])
        if cat != (b.get("category") or "عام"):
            await db.set_book_category(b["id"], cat)
            fixed += 1
    cats = await db.get_categories()
    print(f"OK fixed={fixed} total={len(books)}")
    for c in cats:
        print(f" - {c['name']}: {c['cnt']}")


if __name__ == "__main__":
    asyncio.run(main())
