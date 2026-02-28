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
FACTOR = Decimal("100")
MODE_KEY = "mode"

NOTIFIED_USERS = set()


def _get_admin_id() -> int | None:
    if not ADMIN_ID_RAW:
        return None
    try:
        return int(ADMIN_ID_RAW.strip())
    except Exception:
        return None


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
    "100 ليرة قديمة = 1 ليرة جديدة\n\n"
    "اختر نوع التحويل ثم اكتب المبلغ."
)

HELP_TEXT = (
    "100 ليرة قديمة = 1 ليرة جديدة\n\n"
    "يمكنك كتابة:\n"
    "150000\n"
    "150 الف\n"
    "2 مليون"
)


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_EASTERN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_amount(text: str) -> Decimal:
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


# ✅ تنسيق صحيح بدون أي نقص أصفار
def fmt_number(d: Decimal) -> str:
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

    # أقل من ألف → رقم فقط
    if d_abs < Decimal("1000"):
        return full

    # ألف
    if d_abs < Decimal("1000000"):
        short = clean(d_abs / Decimal("1000")) + " ألف"
    elif d_abs < Decimal("1000000000"):
        short = clean(d_abs / Decimal("1000000")) + " مليون"
    else:
        short = clean(d_abs / Decimal("1000000000")) + " مليار"

    return f"{full} ({short})"


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

    context.user_data[MODE_KEY] = q.data
    if q.data == "old_to_new":
        text = "اكتب المبلغ القديم:"
    else:
        text = "اكتب المبلغ الجديد:"

    await q.edit_message_text(text, reply_markup=back_menu())


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get(MODE_KEY)
    if mode not in ("old_to_new", "new_to_old"):
        return

    try:
        amount = normalize_amount(update.effective_message.text)
    except Exception:
        await update.effective_message.reply_text("❌ اكتب رقم صحيح.", reply_markup=back_menu())
        return

    if mode == "old_to_new":
        old_val = amount
        new_val = amount / FACTOR
    else:
        new_val = amount
        old_val = amount * FACTOR

    reply = (
        "💱 ✅ نتيجة التحويل\n\n"
        f"• المبلغ القديم: {fmt_number(old_val)} ليرة\n"
        f"• المبلغ الجديد: {fmt_number(new_val)} ليرة"
    )

    await update.effective_message.reply_text(reply, reply_markup=back_menu())


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
