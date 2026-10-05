"""فحص ما قبل التشغيل: يعمل بدون توكن تلغرام. خروج 0 = جاهز."""
import os
import socket
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ok = True

def item(name, cond, hint=""):
    global ok
    print(("[OK] " if cond else "[X] ") + name + ("" if cond else f" - {hint}"))
    if not cond:
        ok = False

here = os.path.dirname(os.path.abspath(__file__))
envp = os.path.join(here, ".env")
vals = {}
if os.path.exists(envp):
    for line in open(envp, encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            vals[k.strip()] = v.strip()

tok = vals.get("BOT_TOKEN", "")
item("ملف .env موجود", os.path.exists(envp), "انسخ .env.example إلى .env")
item("BOT_TOKEN بصيغة صحيحة", len(tok) > 20 and ":" in tok and "ضع_التوكن" not in tok, "احصل عليه من @BotFather")
admins = [p for p in vals.get("ADMIN_IDS", "").replace(";", ",").split(",") if p.strip().isdigit() and p.strip() not in {"123456789", "0"}]
item("ADMIN_IDS حقيقي (أو سيتم التعيين تلقائياً لأول مستخدم)", bool(admins), "اتركه فارغاً وسيرسل البوت لك التعيين عند /start")

try:
    import aiogram, aiohttp, aiosqlite, dotenv  # noqa
    item("المكتبات مثبتة", True)
except ImportError as e:
    item("المكتبات مثبتة", False, f"نفذ: venv\\Scripts\\python -m pip install -r requirements.txt ({e})")

try:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    item("SQLite FTS5 متاح", True)
except Exception:
    item("SQLite FTS5 متاح", False, "البحث سيعمل بوضع LIKE الاحتياطي")

s = socket.socket()
try:
    s.bind(("0.0.0.0", int(vals.get("PORT", "8000"))))
    s.close()
    item("المنفذ متاح للقارئ", True)
except OSError:
    item("المنفذ متاح للقارئ", False, "البوت سيعمل والقارئ سيتعطل — غيّر PORT")

for f in ["bot.py", "config.py", "database.py", "keyboards.py", "utils.py", "webapp_server.py", "static/index.html"]:
    item(f"ملف {f}", os.path.exists(os.path.join(here, f)))

print("\nالنتيجة: جاهز ✅" if ok else "\nالنتيجة: أصلح ❌ بالأعلى ثم أعد الفحص")
sys.exit(0 if ok else 1)
