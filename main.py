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
FACTOR = Decimal("100")  # حذف صفرين
MODE_KEY = "mode"        # old_to_new | new_to_old


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
    "اختر نوع التحويل من الأزرار ثم اكتب المبلغ ليتم الحساب مباشرة."
)


# ================= أدوات =================
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_EASTERN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_amount(text: str) -> Decimal:
    """
    يقبل مثل: 125000 / 125,000 / ١٢٥٠٠٠ / 125000 ليرة
    ويرجع Decimal.
    """
    t = (text or "").strip()
    t = t.translate(_ARABIC_DIGITS).translate(_EASTERN_ARABIC_DIGITS)

    # استخرج أول رقم (يسمح بفواصل وآحاد عشرية)
    m = re.search(r"[-+]?\d[\d,\s]*([.]\d+)?", t)
    if not m:
        raise ValueError("No number found")

    num = m.group(0).replace(" ", "").replace(",", "")
    return Decimal(num)


def fmt_number(d: Decimal) -> str:
    """
    تنسيق لطيف:
    - إذا عدد صحيح: بدون كسور وبفواصل آلاف
    - إذا فيه كسور: يظهر كما هو (ونتركه بسيط)
    """
    if d == d.to_integral_value():
        return f"{int(d):,}"
    s = format(d.normalize(), "f").rstrip("0").rstrip(".")
    if "." in s:
        whole, frac = s.split(".")
        return f"{int(whole):,}.{frac}"
    return f"{int(Decimal(s)):,}"


# ================= Handlers =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    if q.data == "old_to_new":
        context.user_data[MODE_KEY] = "old_to_new"
        await q.edit_message_text("✍️ اكتب المبلغ بالليرة القديمة:", reply_markup=back_menu())
        return

    if q.data == "new_to_old":
        context.user_data[MODE_KEY] = "new_to_old"
        await q.edit_message_text("✍️ اكتب المبلغ بالليرة الجديدة:", reply_markup=back_menu())
        return


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get(MODE_KEY)
    if mode not in ("old_to_new", "new_to_old"):
        # تجاهل إذا لم يحدد وضع
        return

    try:
        amount = normalize_amount(update.effective_message.text)
    except Exception:
        await update.effective_message.reply_text(
            "❌ ما قدرت أفهم الرقم.\n"
            "اكتب رقم فقط مثل: 125000 أو 125,000",
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
            f"• المبلغ القديم: {fmt_number(old_val)}\n"
            f"• المبلغ الجديد: {fmt_number(new_val)}"
        )
    else:
        new_val = amount
        old_val = amount * FACTOR
        reply = (
            "💱 ✅ نتيجة التحويل\n\n"
            f"• المبلغ الجديد: {fmt_number(new_val)}\n"
            f"• المبلغ القديم: {fmt_number(old_val)}"
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
