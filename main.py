import json
import os
import re
from decimal import Decimal
from pathlib import Path

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

# ================= ملفات التخزين =================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
CONFIG_FILE = DATA_DIR / "config.json"
REWARDS_FILE = DATA_DIR / "rewards.json"
PENDING_REDEEMS_FILE = DATA_DIR / "pending_redeems.json"

# ================= مفاتيح الحالات =================
ADMIN_ACTION_KEY = "admin_action"
REFERRAL_ACTION_KEY = "referral_action"

ADMIN_WAIT_BAN = "admin_wait_ban"
ADMIN_WAIT_UNBAN = "admin_wait_unban"
ADMIN_WAIT_BROADCAST = "admin_wait_broadcast"
ADMIN_WAIT_REWARD_POINTS = "admin_wait_reward_points"
ADMIN_WAIT_ADD_ITEM_NAME = "admin_wait_add_item_name"
ADMIN_WAIT_ADD_ITEM_COST = "admin_wait_add_item_cost"
ADMIN_WAIT_EDIT_ITEM_NAME = "admin_wait_edit_item_name"
ADMIN_WAIT_EDIT_ITEM_COST = "admin_wait_edit_item_cost"
ADMIN_WAIT_GRANT_POINTS_USER_ID = "admin_wait_grant_points_user_id"
ADMIN_WAIT_GRANT_POINTS_AMOUNT = "admin_wait_grant_points_amount"

REF_WAIT_REDEEM = "ref_wait_redeem"

# ================= النصوص =================
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
    "💰 تحويل قديم → جديد\n"
    "قسمة المبلغ على 100\n"
    "مثال: 50,000 قديم = 500 جديد\n\n"
    "💵 تحويل جديد → قديم\n"
    "ضرب المبلغ × 100\n"
    "مثال: 500 جديد = 50,000 قديم\n\n"
    "اختر نوع التحويل من الأزرار ثم اكتب المبلغ ليتم الحساب مباشرة."
)

BLOCKED_TEXT = "⛔ أنت محظور من استخدام هذا البوت."

# ================= أدوات ملفات =================
def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: Path, data):
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def load_users() -> dict:
    data = _read_json(USERS_FILE, {"users": {}})
    if "users" not in data or not isinstance(data["users"], dict):
        data = {"users": {}}
    return data


def save_users(data: dict):
    _write_json(USERS_FILE, data)


def load_config() -> dict:
    data = _read_json(
        CONFIG_FILE,
        {
            "referral_points_per_invite": 1,
            "blocked_users": [],
        },
    )
    if "referral_points_per_invite" not in data:
        data["referral_points_per_invite"] = 1
    if "blocked_users" not in data or not isinstance(data["blocked_users"], list):
        data["blocked_users"] = []
    return data


def save_config(data: dict):
    _write_json(CONFIG_FILE, data)


def load_rewards() -> dict:
    data = _read_json(REWARDS_FILE, {"items": []})
    if "items" not in data or not isinstance(data["items"], list):
        data["items"] = []
    return data


def save_rewards(data: dict):
    _write_json(REWARDS_FILE, data)


def load_pending_redeems() -> dict:
    data = _read_json(PENDING_REDEEMS_FILE, {"requests": {}})
    if "requests" not in data or not isinstance(data["requests"], dict):
        data["requests"] = {}
    return data


def save_pending_redeems(data: dict):
    _write_json(PENDING_REDEEMS_FILE, data)


# ================= أدوات عامة =================
def _get_admin_id() -> int | None:
    if not ADMIN_ID_RAW:
        return None
    try:
        return int(ADMIN_ID_RAW.strip())
    except Exception:
        return None


def is_admin(user_id: int | None) -> bool:
    admin_id = _get_admin_id()
    return bool(admin_id and user_id and user_id == admin_id)


def is_blocked(user_id: int | None) -> bool:
    if not user_id:
        return False
    config = load_config()
    return int(user_id) in set(config.get("blocked_users", []))


def ensure_user_exists(user) -> dict:
    users_data = load_users()
    uid = str(user.id)
    if uid not in users_data["users"]:
        users_data["users"][uid] = {
            "id": user.id,
            "username": user.username or "",
            "full_name": user.full_name or "",
            "referred_by": None,
            "referrals": [],
            "points": 0,
            "total_points_earned": 0,
            "redeem_count": 0,
            "joined": True,
        }
    else:
        users_data["users"][uid]["username"] = user.username or ""
        users_data["users"][uid]["full_name"] = user.full_name or ""
    save_users(users_data)
    return users_data["users"][uid]


def register_referral(new_user, referrer_id: int) -> bool:
    new_user_id = new_user.id
    if new_user_id == referrer_id:
        return False

    users_data = load_users()
    config = load_config()

    new_uid = str(new_user_id)
    ref_uid = str(referrer_id)

    if new_uid not in users_data["users"] or ref_uid not in users_data["users"]:
        return False

    new_user_data = users_data["users"][new_uid]
    ref_user = users_data["users"][ref_uid]

    if new_user_data.get("referred_by"):
        return False

    new_user_data["referred_by"] = referrer_id

    referrals = ref_user.get("referrals", [])
    if new_user_id not in referrals:
        referrals.append(new_user_id)
    ref_user["referrals"] = referrals

    points = int(config.get("referral_points_per_invite", 1))
    ref_user["points"] = int(ref_user.get("points", 0)) + points
    ref_user["total_points_earned"] = int(ref_user.get("total_points_earned", 0)) + points

    save_users(users_data)

    admin_id = _get_admin_id()
    try:
        from telegram import Bot
        if referrer_id and BOT_TOKEN:
            bot = Bot(token=BOT_TOKEN)
            name = (new_user.full_name or "").strip() or "مستخدم جديد"
            username = f"@{new_user.username}" if new_user.username else "بدون يوزرنيم"
            text = (
                "🎉 تم تسجيل شخص جديد من خلال رابط إحالتك\n\n"
                f"👤 الاسم: {name}\n"
                f"🔗 Username: {username}\n"
                f"⭐ تمت إضافة {points} نقطة إلى رصيدك"
            )
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(bot.send_message(chat_id=referrer_id, text=text))
            except Exception:
                pass
    except Exception:
        pass

    return True


def get_user_stats(user_id: int) -> dict:
    users_data = load_users()
    user_data = users_data["users"].get(str(user_id), {})
    referrals = user_data.get("referrals", [])
    return {
        "referrals_count": len(referrals),
        "points": int(user_data.get("points", 0)),
        "total_points_earned": int(user_data.get("total_points_earned", 0)),
        "redeem_count": int(user_data.get("redeem_count", 0)),
    }


def get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    bot = context.bot
    username = getattr(bot, "username", None)
    if username:
        return username
    return "YourBot"


def get_leaderboard(limit: int = 10) -> list:
    users_data = load_users()
    items = []

    for user in users_data.get("users", {}).values():
        referrals_count = len(user.get("referrals", []))
        if referrals_count > 0:
            items.append(
                {
                    "full_name": (user.get("full_name") or "").strip() or "مستخدم",
                    "referrals_count": referrals_count,
                }
            )

    items.sort(key=lambda x: x["referrals_count"], reverse=True)
    return items[:limit]


def get_next_reward_id() -> int:
    rewards = load_rewards().get("items", [])
    if not rewards:
        return 1
    return max(int(item.get("id", 0)) for item in rewards) + 1


def get_reward_by_id(reward_id: int):
    rewards = load_rewards().get("items", [])
    for item in rewards:
        if int(item.get("id", 0)) == int(reward_id):
            return item
    return None


def delete_reward_by_id(reward_id: int) -> bool:
    rewards_data = load_rewards()
    old_items = rewards_data.get("items", [])
    new_items = [item for item in old_items if int(item.get("id", 0)) != int(reward_id)]
    if len(new_items) == len(old_items):
        return False
    rewards_data["items"] = new_items
    save_rewards(rewards_data)
    return True


def update_reward_name(reward_id: int, new_name: str) -> bool:
    rewards_data = load_rewards()
    for item in rewards_data.get("items", []):
        if int(item.get("id", 0)) == int(reward_id):
            item["name"] = new_name
            save_rewards(rewards_data)
            return True
    return False


def update_reward_cost(reward_id: int, new_cost: int) -> bool:
    rewards_data = load_rewards()
    for item in rewards_data.get("items", []):
        if int(item.get("id", 0)) == int(reward_id):
            item["cost"] = new_cost
            save_rewards(rewards_data)
            return True
    return False


def user_has_pending_redeem(user_id: int) -> bool:
    pending = load_pending_redeems().get("requests", {})
    return str(user_id) in pending


def create_pending_redeem(user, reward_item: dict) -> dict:
    pending_data = load_pending_redeems()
    request = {
        "user_id": user.id,
        "username": user.username or "",
        "full_name": user.full_name or "",
        "reward_id": int(reward_item["id"]),
        "reward_name": reward_item["name"],
        "cost": int(reward_item["cost"]),
        "status": "pending",
    }
    pending_data["requests"][str(user.id)] = request
    save_pending_redeems(pending_data)
    return request


def get_pending_redeem(user_id: int):
    pending = load_pending_redeems().get("requests", {})
    return pending.get(str(user_id))


def remove_pending_redeem(user_id: int):
    pending_data = load_pending_redeems()
    pending_data.get("requests", {}).pop(str(user_id), None)
    save_pending_redeems(pending_data)


def set_pending_redeem_status(user_id: int, status: str):
    pending_data = load_pending_redeems()
    req = pending_data.get("requests", {}).get(str(user_id))
    if req:
        req["status"] = status
        save_pending_redeems(pending_data)


# ================= واجهة القوائم =================
def main_menu(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🎁 نظام الإحالة", callback_data="referral_menu")],
        [
            InlineKeyboardButton("💰 تحويل قديم → جديد", callback_data="old_to_new"),
            InlineKeyboardButton("💵 تحويل جديد → قديم", callback_data="new_to_old"),
        ],
        [InlineKeyboardButton("ℹ️ شرح سريع", callback_data="quick_help")],
    ]

    if is_admin(user_id):
        rows.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_menu")])

    return InlineKeyboardMarkup(rows)


def back_menu(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_menu")])
    return InlineKeyboardMarkup(rows)


def referral_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👥 إحالاتي", callback_data="my_referrals")],
            [InlineKeyboardButton("🔗 رابط الإحالة", callback_data="my_ref_link")],
            [InlineKeyboardButton("🏆 المتصدرين", callback_data="ref_leaderboard")],
            [InlineKeyboardButton("🎁 استبدال النقاط", callback_data="redeem_points")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")],
        ]
    )


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚫 حظر شخص", callback_data="admin_ban")],
            [InlineKeyboardButton("✅ فك حظر شخص", callback_data="admin_unban")],
            [InlineKeyboardButton("📢 إذاعة للكل", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🎁 إدارة الاستبدال", callback_data="admin_manage_rewards")],
            [InlineKeyboardButton("⭐ تعديل مكافأة الإحالة", callback_data="admin_ref_points")],
            [InlineKeyboardButton("🎯 منح نقاط", callback_data="admin_grant_points")],
            [InlineKeyboardButton("📊 عدد المستخدمين", callback_data="admin_user_count")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")],
        ]
    )


def admin_rewards_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ إضافة سلعة", callback_data="admin_add_reward")],
            [InlineKeyboardButton("📦 عرض السلع", callback_data="admin_list_rewards")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_menu")],
        ]
    )


def selected_reward_menu(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"admin_edit_reward_name:{item_id}")],
            [InlineKeyboardButton("💰 تعديل السعر", callback_data=f"admin_edit_reward_cost:{item_id}")],
            [InlineKeyboardButton("❌ حذف السلعة", callback_data=f"admin_delete_reward:{item_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_list_rewards")],
        ]
    )


def rewards_inline_menu(items: list, prefix: str, back_callback: str) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{item['name']} — {item['cost']} نقطة",
                    callback_data=f"{prefix}:{item['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=back_callback)])
    return InlineKeyboardMarkup(rows)


def admin_redeem_request_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ قبول", callback_data=f"admin_accept_redeem:{user_id}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"admin_reject_redeem:{user_id}"),
            ]
        ]
    )


# ================= أدوات أرقام =================
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_EASTERN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_amount(text: str) -> Decimal:
    """
    يقبل مثل: 125000 / 125,000 / ١٢٥٠٠٠ / 125000 ليرة
    ويرجع Decimal.
    """
    t = (text or "").strip()
    t = t.translate(_ARABIC_DIGITS).translate(_EASTERN_ARABIC_DIGITS)

    m = re.search(r"[-+]?\d[\d,\s]*([.]\d+)?", t)
    if not m:
        raise ValueError("No number found")

    num = m.group(0).replace(" ", "").replace(",", "")
    return Decimal(num)


def fmt_number(d: Decimal) -> str:
    d = d.normalize()
    if d == d.to_integral_value():
        return str(int(d))
    return format(d, "f").rstrip("0").rstrip(".")


def parse_int(text: str) -> int:
    t = (text or "").strip()
    t = t.translate(_ARABIC_DIGITS).translate(_EASTERN_ARABIC_DIGITS)
    m = re.search(r"\d+", t)
    if not m:
        raise ValueError("No int found")
    return int(m.group(0))


# ================= Handlers =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    ensure_user_exists(user)

    if is_blocked(user.id):
        await update.effective_message.reply_text(BLOCKED_TEXT)
        return

    admin_id = _get_admin_id()
    if admin_id and user.id not in NOTIFIED_USERS:
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

    # تسجيل الإحالة عند أول دخول فقط
    if context.args:
        try:
            referrer_id = int(context.args[0])
            register_referral(user, referrer_id)
        except Exception:
            pass

    context.user_data.pop(MODE_KEY, None)
    context.user_data.pop(ADMIN_ACTION_KEY, None)
    context.user_data.pop(REFERRAL_ACTION_KEY, None)
    context.user_data.pop("new_reward_name", None)
    context.user_data.pop("selected_reward_id", None)
    context.user_data.pop("grant_points_user_id", None)

    await update.effective_message.reply_text(
        WELCOME_TEXT,
        reply_markup=main_menu(user.id),
    )
    async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user = update.effective_user
    if not user:
        return

    if is_blocked(user.id):
        await q.edit_message_text(BLOCKED_TEXT)
        return

    context.user_data.pop(ADMIN_ACTION_KEY, None)
    context.user_data.pop(REFERRAL_ACTION_KEY, None)

    if q.data == "back":
        context.user_data.pop(MODE_KEY, None)
        await q.edit_message_text(WELCOME_TEXT, reply_markup=main_menu(user.id))
        return

    if q.data == "quick_help":
        await q.edit_message_text(HELP_TEXT, reply_markup=back_menu(user.id))
        return

    if q.data == "new_to_old":
        context.user_data[MODE_KEY] = "new_to_old"
        await q.edit_message_text(
            "🧮 تحويل جديد → قديم\n"
            "اكتب المبلغ بالعملة الجديدة الآن:\n"
            "مثال: 1250",
            reply_markup=back_menu(user.id),
        )
        return

    if q.data == "old_to_new":
        context.user_data[MODE_KEY] = "old_to_new"
        await q.edit_message_text(
            "🧮 تحويل قديم → جديد\n"
            "اكتب المبلغ بالعملة القديمة الآن:\n"
            "مثال: 125000",
            reply_markup=back_menu(user.id),
        )
        return

    # ================= نظام الإحالة =================

    if q.data == "referral_menu":
        await q.edit_message_text(
            "🎁 نظام الإحالة\n\nاختر القسم:",
            reply_markup=referral_menu(),
        )
        return

    if q.data == "my_referrals":
        stats = get_user_stats(user.id)

        await q.edit_message_text(
            "📊 إحصائيات الإحالة\n\n"
            f"👥 عدد الإحالات: {stats['referrals_count']}\n"
            f"⭐ نقاطك الحالية: {stats['points']}\n"
            f"💰 إجمالي النقاط المكتسبة: {stats['total_points_earned']}\n"
            f"🎁 مرات الاستبدال: {stats['redeem_count']}",
            reply_markup=referral_menu(),
        )
        return

    if q.data == "my_ref_link":
        bot_username = get_bot_username(context)

        link = f"https://t.me/{bot_username}?start={user.id}"

        await q.edit_message_text(
            "🔗 رابط الإحالة الخاص بك:\n\n"
            f"{link}\n\n"
            "أرسل الرابط لأصدقائك لتحصل على نقاط.",
            reply_markup=referral_menu(),
        )
        return

    if q.data == "ref_leaderboard":

        leaders = get_leaderboard()

        if not leaders:
            text = "🏆 لا يوجد متصدرين بعد."
        else:

            lines = ["🏆 المتصدرين\n"]

            for i, item in enumerate(leaders, 1):
                lines.append(f"{i} — {item['full_name']} ({item['referrals_count']})")

            text = "\n".join(lines)

        await q.edit_message_text(text, reply_markup=referral_menu())
        return

    # ================= الاستبدال =================

    if q.data == "redeem_points":

        rewards = load_rewards().get("items", [])

        if not rewards:
            await q.edit_message_text(
                "🎁 لا توجد سلع حالياً.",
                reply_markup=referral_menu(),
            )
            return

        if user_has_pending_redeem(user.id):

            await q.answer("طلبك قيد المراجعة، انتظر رد الإدارة.", show_alert=True)
            return

        await q.edit_message_text(
            "🎁 اختر السلعة:",
            reply_markup=rewards_inline_menu(rewards, "redeem_item", "referral_menu"),
        )

        return

    if q.data.startswith("redeem_item:"):

        reward_id = int(q.data.split(":")[1])

        item = get_reward_by_id(reward_id)

        if not item:
            await q.answer("السلعة غير موجودة")
            return

        users_data = load_users()
        user_data = users_data["users"].get(str(user.id))

        if not user_data:
            return

        points = int(user_data.get("points", 0))
        cost = int(item["cost"])

        if points < cost:

            await q.answer("❌ نقاطك غير كافية.", show_alert=True)
            return

        user_data["points"] = points - cost
        save_users(users_data)

        req = create_pending_redeem(user, item)

        admin_id = _get_admin_id()

        if admin_id:

            text = (
                "🚨 طلب استبدال جديد\n\n"
                f"👤 الاسم: {user.full_name}\n"
                f"🆔 ID: {user.id}\n"
                f"🔗 Username: @{user.username}\n"
                f"🎁 السلعة: {item['name']}\n"
                f"⭐ التكلفة: {item['cost']} نقطة"
            )

            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=admin_redeem_request_menu(user.id),
            )

        await q.edit_message_text(
            "✅ تم إرسال طلب الاستبدال للإدارة.",
            reply_markup=referral_menu(),
        )

        return
        # ================= لوحة الأدمن =================

    if q.data == "admin_menu":
        if not is_admin(user.id):
            return

        await q.edit_message_text(
            "⚙️ لوحة الأدمن",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_user_count":

        users = load_users()

        total = len(users.get("users", {}))

        config = load_config()

        blocked = len(config.get("blocked_users", []))

        await q.edit_message_text(
            "📊 إحصائيات المستخدمين\n\n"
            f"👥 إجمالي المستخدمين: {total}\n"
            f"⛔ المحظورين: {blocked}",
            reply_markup=admin_menu(),
        )
        return

    # ================= قبول الاستبدال =================

    if q.data.startswith("admin_accept_redeem:"):

        if not is_admin(user.id):
            return

        uid = int(q.data.split(":")[1])

        req = get_pending_redeem(uid)

        if not req:
            await q.answer("الطلب غير موجود")
            return

        set_pending_redeem_status(uid, "accepted")

        remove_pending_redeem(uid)

        await context.bot.send_message(
            chat_id=uid,
            text="✅ تم قبول طلبك.",
        )

        await q.edit_message_text("تم قبول الطلب.")

        return

    # ================= رفض الاستبدال =================

    if q.data.startswith("admin_reject_redeem:"):

        if not is_admin(user.id):
            return

        uid = int(q.data.split(":")[1])

        req = get_pending_redeem(uid)

        if not req:
            await q.answer("الطلب غير موجود")
            return

        users = load_users()

        user_data = users["users"].get(str(uid))

        if user_data:

            user_data["points"] = int(user_data.get("points", 0)) + int(req["cost"])

            save_users(users)

        remove_pending_redeem(uid)

        await context.bot.send_message(
            chat_id=uid,
            text="❌ تم رفض طلبك وتم استرجاع نقاطك.",
        )

        await q.edit_message_text("تم رفض الطلب.")

        return


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user:
        return

    ensure_user_exists(user)

    if is_blocked(user.id):
        await update.effective_message.reply_text(BLOCKED_TEXT)
        return

    mode = context.user_data.get(MODE_KEY)

    if mode not in ("old_to_new", "new_to_old"):
        return

    try:

        amount = normalize_amount(update.effective_message.text)

    except Exception:

        await update.effective_message.reply_text(
            "❌ اكتب رقم صحيح.",
            reply_markup=back_menu(user.id),
        )

        return

    if mode == "old_to_new":

        old_val = amount
        new_val = amount / FACTOR

        text = (
            "💱 نتيجة التحويل\n\n"
            f"قديم: {fmt_number(old_val)}\n"
            f"جديد: {fmt_number(new_val)}"
        )

    else:

        new_val = amount
        old_val = amount * FACTOR

        text = (
            "💱 نتيجة التحويل\n\n"
            f"جديد: {fmt_number(new_val)}\n"
            f"قديم: {fmt_number(old_val)}"
        )

    await update.effective_message.reply_text(
        text,
        reply_markup=back_menu(user.id),
    )


def main():

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(on_button))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_amount,
        )
    )

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
