import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
_raw_admins = os.getenv("ADMIN_IDS", "")
# تجاهل القيم المثال الشائعة حتى لا يظن المستخدم أن الإعداد تم
_PLACEHOLDERS = {"123456789", "0", "111111111"}
ADMIN_IDS = set()
for part in _raw_admins.replace(";", ",").split(","):
    part = part.strip()
    if part.isdigit() and part not in _PLACEHOLDERS:
        ADMIN_IDS.add(int(part))

DB_PATH = os.getenv("DB_PATH", "library.db").strip() or "library.db"
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "8") or 8)
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "49") or 49)
CACHE_TTL = int(os.getenv("CACHE_TTL", "600") or 600)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# v3: وضع التشغيل والنشر
MODE = os.getenv("MODE", "polling").strip().lower()  # polling | webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook").strip() or "/webhook"
PORT = int(os.getenv("PORT", "8000") or 8000)
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "").strip()  # مثال: @mychannel (اختياري)

# v5: قارئ WebApp + قناة نشر تلقائي
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")  # مثال: https://your-app.onrender.com/app (اختياري)
LIB_CHANNEL = os.getenv("LIB_CHANNEL", "").strip()  # مثال: @mylibrary لنشر الكتب الجديدة (اختياري)

# النشر اليومي: ساعة النشر (0-23 بتوقيت السيرفر)
POST_HOUR = int(os.getenv("POST_HOUR", "9") or 9)

def is_admin(user_id: int | None) -> bool:
    return bool(user_id) and user_id in ADMIN_IDS

def validate() -> list[str]:
    errs = []
    if not BOT_TOKEN or len(BOT_TOKEN) < 20 or ":" not in BOT_TOKEN:
        errs.append("BOT_TOKEN مفقود أو غير صالح (احصل عليه من @BotFather)")
    if not ADMIN_IDS:
        errs.append("ADMIN_IDS فارغ — لن تعمل لوحة الأدمن")
    if MODE == "webhook" and not WEBHOOK_URL:
        errs.append("MODE=webhook لكن WEBHOOK_URL فارغ")
    return errs
