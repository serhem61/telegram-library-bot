"""اختبار نواة المكتبة بدون توكن: FTS + أرفف + تقييم + اقتباس + تلخيص.
تشغيل: python test_core.py
"""
import asyncio
import os
import tempfile

tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmp, "t.db")

import database as db
from utils import summarize, validate_file

async def main():
    await db.init_db()
    bid = await db.add_book("تاريخ الأندلس", "ابن خلدون", "تاريخ", "مقدمة في تاريخ الأندلس والحضارة.",
                            "fid1", "pdf", "andalus.pdf", 1000, "ar", 1, file_unique_id="u1")
    dup = await db.add_book("مكرر", "x", "عام", "", "fid1", "pdf", "", 0, "ar", 1, file_unique_id="u1")
    assert dup == bid, "dedup failed"
    hits = await db.search_books("الأندلس")
    assert hits, "FTS/LIKE search failed"
    await db.shelf_set(1, bid, "want")
    assert await db.shelf_get(1, bid) == "want"
    await db.rate_set(1, bid, 5)
    b = await db.get_book(bid)
    assert b["rating_avg"] == 5.0, b
    qid = await db.quote_add(1, bid, "العلم في الغربة وطن.")
    assert qid > 0
    s = summarize("الجملة الأولى مهمة جدا. الجملة الثانية تشرح التاريخ. الجملة الثالثة خاتمة.")
    assert "🧾" in s
    ok, ft, _ = validate_file("x.pdf", "application/pdf", 100)
    assert ok and ft == "pdf"
    ok, _, _ = validate_file("x.exe", "", 100)
    assert not ok
    print("OK v5 core: dedup, search, shelf, rating, quote, summarize, validate")

if __name__ == "__main__":
    asyncio.run(main())
