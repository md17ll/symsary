import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ===== إعدادات التحويل =====
FACTOR = Decimal("100")  # حذف صفرين

# مفاتيح الحالة
MODE_KEY = "mode"  # "old_to_new" | "new_to_old"


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔁 قديم → جديد", callback_data="old_to_new"),
                InlineKeyboardButton("🔁 جديد → قديم", callback_data="new_to_old"),
            ],
            [InlineKeyboardButton("ℹ️ شرح سريع", callback_data="quick_help")],
        ]
    )


WELCOME_TEXT = (
    "👋 <b>أهلاً بك في بوت تحويل العملة</b>\n\n"
    "بعد حذف صفرين من العملة قد يصير لَخبَطة بالحسابات.\n"
    "هذا البوت يحوّل أي مبلغ بسرعة ودقة.\n\n"
    "📌 اختر نوع التحويل من الأزرار بالأسفل ثم اكتب المبلغ."
)

QUICK_HELP_TEXT = (
    "ℹ️ <b>شرح سريع – حذف صفرين من الليرة</b>\n\n"
    "✅ تم حذف <b>صفرين</b> من العملة.\n"
    "يعني: <b>كل 100 ليرة قديمة = 1 ليرة جديدة</b>\n\n"
    "🔁 <b>التحويل:</b>\n"
    "• <b>قديم → جديد:</b> ÷ 100  (مثال: 1,000 قديم = 10 جديد)\n"
    "• <b>جديد → قديم:</b> × 100  (مثال: 10 جديد = 1,000 قديم)\n\n"
    "✍️ <b>طريقة الاستخدام:</b>\n"
    "1) اختر نوع التحويل\n"
    "2) اكتب المبلغ بالأرقام فقط (مسموح فواصل مثل 1,250)\n\n"
    "للرجوع للقائمة ارسل /start"
)


# تحويل الأرقام العربية (٠١٢٣...) إلى إنجليزية
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_EASTERN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_amount(text: str) -> Decimal:
    """
    يقبل مثل: 125000 / 125,000 / ١٢٥٠٠٠ / 125000 ليرة
    ويرجع Decimal.
    """
    t = text.strip()
    t = t.translate(_ARABIC_DIGITS).translate(_EASTERN_ARABIC_DIGITS)

    # استخرج أول رقم/قيمة (يسمح بفواصل وآحاد عشرية)
    # مثال: "1,250.50 ليرة" -> "1,250.50"
    m = re.search(r"[-+]?\d[\d,\s]*([.]\d+)?", t)
    if not m:
        raise InvalidOperation("No number found")

    num = m.group(0)

    # إزالة الفراغات والفواصل
    num = num.replace(" ", "").replace(",", "")

    # منع أرقام فارغة
    if num in ("", "+", "-"):
        raise InvalidOperation("Empty")

    return Decimal(num)


def fmt_number(d: Decimal) -> str:
    """
    تنسيق رقم بشكل لطيف:
    - إذا عدد صحيح: بدون كسور
    - إذا فيه كسور: حتى 2 رقم عشري (قابل للتعديل)
    """
    # تطبيع لإزالة -0
    if d == 0:
        d = Decimal("0")

    if d == d.to_integral_value():
        # فواصل آلاف
        return f"{int(d):,}"
    # تقريب إلى خانتين
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # إزالة أصفار زائدة
    s = format(q, "f").rstrip("0").rstrip(".")
    # فواصل آلاف للجزء الصحيح
    if "." in s:
        whole, frac = s.split(".")
        whole_fmt = f"{int(whole):,}"
        return f"{whole_fmt}.{frac}"
    return f"{int(Decimal(s)):,}"


async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit: bool = False):
    if update.callback_query and edit:
        await update.callback_query.edit_message_text(
            WELCOME_TEXT,
            reply_markup=_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.effective_message.reply_text(
            WELCOME_TEXT,
            reply_markup=_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(MODE_KEY, None)
    await send_menu(update, context, edit=False)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    data = q.data

    if data in ("old_to_new", "new_to_old"):
        context.user_data[MODE_KEY] = data

        if data == "old_to_new":
            prompt = (
                "🧮 <b>تحويل قديم → جديد</b>\n\n"
                "اكتب المبلغ <b>بالعملة القديمة</b> الآن:\n"
                "مثال: 125000"
            )
        else:
            prompt = (
                "🧮 <b>تحويل جديد → قديم</b>\n\n"
                "اكتب المبلغ <b>بالعملة الجديدة</b> الآن:\n"
                "مثال: 1250"
            )

        await q.edit_message_text(prompt, parse_mode=ParseMode.HTML)
        return

    if data == "quick_help":
        await q.edit_message_text(
            QUICK_HELP_TEXT,
            reply_markup=_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    # fallback
    await send_menu(update, context, edit=True)


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get(MODE_KEY)
    if mode not in ("old_to_new", "new_to_old"):
        # المستخدم كتب رقم بدون اختيار وضع
        await update.effective_message.reply_text(
            "اختَر نوع التحويل أولاً من القائمة 👇\n\n/send /start",
        )
        await send_menu(update, context, edit=False)
        return

    text = update.effective_message.text or ""
    try:
        amount = normalize_amount(text)
    except Exception:
        await update.effective_message.reply_text(
            "❌ ما قدرت أفهم الرقم.\n"
            "اكتب رقم فقط مثل: 125000 أو 125,000\n\n"
            "للرجوع للقائمة: /start"
        )
        return

    if amount < 0:
        await update.effective_message.reply_text(
            "❌ رجاءً اكتب مبلغ موجب.\n\nللرجوع: /start"
        )
        return

    if mode == "old_to_new":
        old_val = amount
        new_val = (amount / FACTOR)
        rule = "تم حذف صفرين (÷100)"
        title = "✅ نتيجة التحويل (قديم → جديد)"
    else:
        new_val = amount
        old_val = (amount * FACTOR)
        rule = "إرجاع صفرين (×100)"
        title = "✅ نتيجة التحويل (جديد → قديم)"

    reply = (
        f"{title}\n\n"
        f"• المبلغ القديم: <b>{fmt_number(old_val)}</b>\n"
        f"• المبلغ الجديد: <b>{fmt_number(new_val)}</b>\n"
        f"• القاعدة: <i>{rule}</i>\n\n"
        "🔁 لتحويل رقم آخر اضغط زر من القائمة أو ارسل /start"
    )

    await update.effective_message.reply_text(reply, parse_mode=ParseMode.HTML)

    # خليه يبقى على نفس الوضع (إذا بدك يرجع للقائمة مباشرة احذف السطرين تحت)
    # context.user_data.pop(MODE_KEY, None)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(QUICK_HELP_TEXT, parse_mode=ParseMode.HTML)


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing BOT_TOKEN environment variable")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount))

    # Railway: الأفضل Polling (أسهل)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
