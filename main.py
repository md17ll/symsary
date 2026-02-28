import os
import re
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
FACTOR = Decimal("100")  # حذف صفرين
MODE_KEY = "mode"

NOTIFIED_USERS = set()


def _get_admin_id() -> int | None:
    if not ADMIN_ID_RAW:
        return None
    try:
        return int(ADMIN_ID_RAW.strip())
    except Exception:
        return None


# ================= واجهة القوائم =================
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔁 من قديم إلى جديد", callback_data="old_to_new"),
                InlineKeyboardButton("🔁 من جديد إلى قديم", callback_data="new_to_old"),
            ],
            [InlineKeyboardButton("ℹ️ شرح سريع", callback_data="quick_help")],
        ]
    )


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])


WELCOME_TEXT = (
    "👋🇸🇾 أهلاً بك في بوت تحويل الليرة السورية\n\n"
    "بعد حذف صفرين من الليرة السورية قد يحدث بعض الالتباس في الحسابات،\n"
    "هذا البوت يساعدك على تحويل أي مبلغ بين الليرة القديمة والجديدة بسرعة ودقة 💱\n\n"
    "👨‍💻 المطور: @md17l\n\n"
    "📌 اختر نوع التحويل من الأزرار بالأسفل ثم اكتب المبلغ ✍️"
)

HELP_TEXT = (
    "🇸🇾 شرح سريع – تحويل الليرة السورية\n\n"
    "100 ليرة قديمة = 1 ليرة جديدة\n\n"
    "🔁 من قديم إلى جديد → قسمة على 100\n"
    "🔁 من جديد إلى قديم → ضرب × 100\n\n"
    "✅ تقدر تكتب كمان: 150 الف / 2 مليون / 3 مليار"
)


# ================= أدوات =================
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_EASTERN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_amount(text: str) -> Decimal:
    """
    يقبل مثل:
    125000 / 125,000 / ١٢٥٠٠٠ / 150 الف / 2 مليون / 3 مليار
    ويرجع Decimal.
    """
    t = (text or "").strip().lower()
    t = t.translate(_ARABIC_DIGITS).translate(_EASTERN_ARABIC_DIGITS)

    m = re.search(r"[-+]?\d[\d,\s]*([.]\d+)?", t)
    if not m:
        raise ValueError("No number found")

    num = m.group(0).replace(" ", "").replace(",", "")
    value = Decimal(num)

    if "مليار" in t:
        value *= Decimal("1000000000")
    elif "مليون" in t:
        value *= Decimal("1000000")
    elif "الف" in t or "ألف" in t:
        value *= Decimal("1000")

    return value


def fmt_number(d: Decimal) -> str:
    """
    عرض الأرقام:
    - أقل من 10,000: يعرض رقم كامل (مثال: 1500)
    - من 10,000 إلى أقل من مليون: ألف (مثال: 150 ألف)
    - مليون/مليار بنفس الفكرة
    """
    d = d.normalize()
    sign = "-" if d < 0 else ""
    d = abs(d)

    def clean(x: Decimal) -> str:
        s = format(x.normalize(), "f").rstrip("0").rstrip(".")
        return s if s else "0"

    if d < Decimal("10000"):
        if d == d.to_integral_value():
            return sign + str(int(d))
        return sign + clean(d)

    if d < Decimal("1000000"):
        v = d / Decimal("1000")  # ✅ 1000 بالضبط
        return sign + clean(v) + " ألف"

    if d < Decimal("1000000000"):
        v = d / Decimal("1000000")
        return sign + clean(v) + " مليون"

    v = d / Decimal("1000000000")
    return sign + clean(v) + " مليار"


# ================= Handlers =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = _get_admin_id()
    user = update.effective_user
    if admin_id and user and user.id not in NOTIFIED_USERS:
        NOTIFIED_USERS.add(user.id)
        username = f"@{user.username}" if user.username else "بدون"
        full_name = (user.full_name or "").strip() or "بدون"
        msg = (
            "🚨 مستخدم دخل البوت\n"
            f"ID: {user.id}\n"
            f"Username: {username}\n"
            f"Name: {full_name}"
        )
        try:
            await context.bot.send_message(chat_id=admin_id, text=msg)
        except Exception:
            pass

    context.user_data.pop(MODE_KEY, None)
    await update.effective_message.reply_text(WELCOME_TEXT, reply_markup=main_menu())


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "back":
        context.user_data.pop(MODE_KEY, None)
        await q.edit_message_text(WELCOME_TEXT, reply_markup=main_menu())
        return

    if q.data == "quick_help":
        await q.edit_message_text(HELP_TEXT, reply_markup=back_menu())
        return

    if q.data == "new_to_old":
        context.user_data[MODE_KEY] = "new_to_old"
        await q.edit_message_text(
            "🧮 تحويل من جديد إلى قديم\nاكتب المبلغ بالعملة الجديدة الآن:\nمثال: 1250",
            reply_markup=back_menu(),
        )
        return

    if q.data == "old_to_new":
        context.user_data[MODE_KEY] = "old_to_new"
        await q.edit_message_text(
            "🧮 تحويل من قديم إلى جديد\nاكتب المبلغ بالعملة القديمة الآن:\nمثال: 125000",
            reply_markup=back_menu(),
        )
        return


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get(MODE_KEY)
    if mode not in ("old_to_new", "new_to_old"):
        return

    try:
        amount = normalize_amount(update.effective_message.text)
    except Exception:
        await update.effective_message.reply_text(
            "❌ اكتب رقم صحيح مثل: 125000 أو 150 الف",
            reply_markup=back_menu(),
        )
        return

    if amount < 0:
        await update.effective_message.reply_text("❌ اكتب مبلغ موجب.", reply_markup=back_menu())
        return

    # تنبيه بسيط لتجنب الالتباس (لا يغير الحساب)
    warn = ""
    if mode == "old_to_new" and amount < Decimal("1000"):
        warn = "\n\n⚠️ تنبيه: إذا قصدك (ألف/عشرات الألوف) تأكد ما ناقص أصفار."
    if mode == "new_to_old" and amount < Decimal("10"):
        warn = "\n\n⚠️ تنبيه: يبدو المبلغ صغير جداً، تأكد من الرقم."

    if mode == "old_to_new":
        old_val = amount
        new_val = amount / FACTOR
        reply = (
            "💱 ✅ نتيجة التحويل\n\n"
            f"• المبلغ القديم: {fmt_number(old_val)} ليرة\n"
            f"• المبلغ الجديد: {fmt_number(new_val)} ليرة"
            f"{warn}"
        )
    else:
        new_val = amount
        old_val = amount * FACTOR
        reply = (
            "💱 ✅ نتيجة التحويل\n\n"
            f"• المبلغ الجديد: {fmt_number(new_val)} ليرة\n"
            f"• المبلغ القديم: {fmt_number(old_val)} ليرة"
            f"{warn}"
        )

    await update.effective_message.reply_text(reply, reply_markup=back_menu())


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN environment variable")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
