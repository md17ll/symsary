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
ADMIN_ID_RAW = os.getenv("ADMIN_ID")  # ضعه في Variables على Railway
FACTOR = Decimal("100")  # حذف صفرين
MODE_KEY = "mode"        # old_to_new | new_to_old

# إشعار دخول المستخدم (مرة واحدة لكل تشغيل للبوت)
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
    "تم حذف صفرين من الليرة السورية، أي أن:\n"
    "100 ليرة قديمة = 1 ليرة جديدة\n\n"
    "طريقة التحويل:\n\n"
    "🔁 من قديم إلى جديد\n"
    "قسمة المبلغ على 100\n"
    "مثال: 50,000 قديم = 500 جديد\n\n"
    "🔁 من جديد إلى قديم\n"
    "ضرب المبلغ × 100\n"
    "مثال: 500 جديد = 50,000 قديم\n\n"
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
    يعرض الرقم بطريقتين لمنع أي لبس:
    - الرقم الكامل بدون فواصل
    - وبين قوسين صيغة (ألف/مليون/مليار) إذا كان >= 10,000
    مثال: 100000 -> 100000 (100 ألف)
    """
    d = d.normalize()
    sign = "-" if d < 0 else ""
    d_abs = abs(d)

    def clean(x: Decimal) -> str:
        s = format(x.normalize(), "f").rstrip("0").rstrip(".")
        return s if s else "0"

    # الرقم الكامل
    if d_abs == d_abs.to_integral_value():
        full = sign + str(int(d_abs))
    else:
        full = sign + clean(d_abs)

    # أقل من 10 آلاف: اعرض الرقم فقط (مثال: 1500)
    if d_abs < Decimal("10000"):
        return full

    # صيغة ألف/مليون/مليار
    if d_abs < Decimal("1000000"):
        short = clean(d_abs / Decimal("1000")) + " ألف"
    elif d_abs < Decimal("1000000000"):
        short = clean(d_abs / Decimal("1000000")) + " مليون"
    else:
        short = clean(d_abs / Decimal("1000000000")) + " مليار"

    return f"{full} ({sign}{short})"


# ================= Handlers =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # إشعار للأدمن عند دخول مستخدم (مرة واحدة لكل تشغيل)
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
            "🧮 تحويل من جديد إلى قديم\n"
            "اكتب المبلغ بالعملة الجديدة الآن:\n"
            "مثال: 1250",
            reply_markup=back_menu(),
        )
        return

    if q.data == "old_to_new":
        context.user_data[MODE_KEY] = "old_to_new"
        await q.edit_message_text(
            "🧮 تحويل من قديم إلى جديد\n"
            "اكتب المبلغ بالعملة القديمة الآن:\n"
            "مثال: 125000",
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
        await update.effective_message.reply_text("❌ رجاءً اكتب مبلغ موجب.", reply_markup=back_menu())
        return

    if mode == "old_to_new":
        old_val = amount
        new_val = amount / FACTOR
        reply = (
            "💱 ✅ نتيجة التحويل\n\n"
            f"• المبلغ القديم: {fmt_number(old_val)} ليرة\n"
            f"• المبلغ الجديد: {fmt_number(new_val)} ليرة"
        )
    else:
        new_val = amount
        old_val = amount * FACTOR
        reply = (
            "💱 ✅ نتيجة التحويل\n\n"
            f"• المبلغ الجديد: {fmt_number(new_val)} ليرة\n"
            f"• المبلغ القديم: {fmt_number(old_val)} ليرة"
        )

    await update.effective_message.reply_text(reply, reply_markup=back_menu())


# ================= تشغيل =================
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
