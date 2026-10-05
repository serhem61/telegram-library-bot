# 📚 المكتبة v5 — الأقوى عملياً (بدون وهم بنية مدفوعة)

## ما الذي يجعلها "الأقوى" فعلاً؟
- **بحث FTS5 حقيقي** (`books_fts` + triggers + `bm25`) مع fallback LIKE — نفس استعلام `/search` أسرع وأدق عربياً. زر **🔄 فهرسة** + `/reindex` يعيد البناء.
- **WAL mode** للتزامن + فهارس + منع تكرار `file_unique_id` + فحص صيغ PDF/EPUB/TXT/MOBI وحجم.
- **📖 قارئ WebApp**: زر تلقائي في صفحة الكتاب عند ضبط `WEBAPP_URL` + `GET /app/` (وضع ليلي/خط RTL) + `GET /api/book?book=ID` + يعمل مع Polling وWebhook. حد صريح: ملف EPUB الكامل يحتاج S3 لاحقاً — الآن بيانات+وصف+اقتباسات.
- **📅 كتاب اليوم** حتمي (`/today`) + **نشر تلقائي** في `LIB_CHANNEL` عند الإضافة.
- **💬 اقتباسات** (`quote:` → حفظ → `myquotes`) + **🧾 تلخيص استخراجي** محلي بدون API خارجي.
- **📤 تصدير** JSON+CSV (`/export`) + **💾 نسخة** + اختبار نواة `python test_core.py`.

## أوامر v5
`/search /author /isbn /random /today /top /new /mybooks /request /export /reindex`
أزرار الكتاب: تحميل/مفضل/3 أرفف/تقييم/تقدم/تلخيص/اقتباس/قراءة WebApp/مشاركة.

## تشغيل
```powershell
pip install -r requirements.txt
copy .env.example .env
python test_core.py   # تحقق سريع بدون توكن
python bot.py
```
القارئ: `http://localhost:8000/app/` و `http://localhost:8000/api/book?book=1` و `http://localhost:8000/health`.

## نشر
`WEBAPP_URL=https://xxx/app/` + `LIB_CHANNEL=@mylibrary` (اجعله مشرفاً). Render: `MODE=webhook` + `WEBHOOK_URL`.

## الاستيراد بالجملة (قانوني فقط)
`bulk_import.py` يجلب من Gutenberg (ملكية عامة) ويخزن روابط خارجية بلا رفع ملفات:
```
venv/Scripts/python.exe bulk_import.py --query philosophy --limit 20 --dry-run
venv/Scripts/python.exe bulk_import.py --query history --limit 200 --category تاريخ --delay 1.5
```
الكتب المستوردة تظهر في `/search` وزر التحميل يرسل رابطها المجاني. التكرار يُكتشف تلقائياً.

## حدود صريحة عن "الملايين"
- **ملفات:** مستحيل على هذه البنية — مليون PDF × ~3MB ≈ 3 بيتابايت، وتلغرام يحد الملف بـ 50MB (2GB بالخادم المحلي)، والاستضافة المجانية مساحتها GB. الممكن: فهرس روابط + ملفات مرفوعة مختارة.
- **قاعدة البيانات:** SQLite + FTS يكفي حتى ~50 ألف سجل. بعدها: Postgres + Meilisearch + S3.
- **قانونياً:** Gutenberg ≈ 70 ألف كتاب ملكية عامة (إنجليزية غالباً). الكتب العربية الحديثة محمية — لا تستوردها بلا ترخيص ناشر.

## v6: مشاركة وتقييم
- روابط عميقة: `t.me/بوتك?start=book_123` تفتح الكتاب مباشرة (تعمل مع مشاركة القنوات).
- إتمام الطلبات تلقائياً: عند إضافة كتاب يطابق طلباً مفتوحاً يُشعر طالبوه ويُغلق.
- مراجعات نصية: ⭐ ثم ✍️ كتابة مراجعة (تظهر في متوسط التقييم).
- تعديل الكتب: زر ✏️ للأدمن في صفحة الكتاب (عنوان/مؤلف/تصنيف/وسوم/وصف).

## النشر اليومي
- `/setchannel @قناتك` (البوت مشرف) ← `/postnow` للتجربة الفورية ← تلقائياً كل يوم الساعة `POST_HOUR` (9 صباحاً).
- المنشور: غلاف + نبذة + تقييم + ملف PDF للتنزيل المباشر (يُفضّل الكتب المرفوعة بملف حقيقي).
- `/autopost on|off` للتفعيل/التعطيل. يعمل في وضعي polling وwebhook.

## ما زال خارج النطاق الصادق
S3/CDN للملفات الكاملة، Meili/Elastic بعد 50k كتاب، OCR/Calibre Workers، TTS/AI-LLM، تطبيقات. هذه v5 هي السقف الأقوى قبل تلك البنية.
