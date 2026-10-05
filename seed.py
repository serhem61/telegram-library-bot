"""إضافة تصنيفات تجريبية فارغة (بدون ملفات) للمعاينة السريعة."""
import asyncio
import database as db

async def main():
    await db.init_db()
    for name in ["روايات", "دين", "تطوير ذات", "برمجة", "تاريخ", "علوم"]:
        cid = await db.ensure_category(name)
        print(f"OK {cid}: {name}")

if __name__ == "__main__":
    asyncio.run(main())
