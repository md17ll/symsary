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
ADMIN_WAIT_FORCE_SUB_CHANNEL = "admin_wait_force_sub_channel"

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
BOT_STOPPED_TEXT = "⛔ البوت متوقف حالياً من قبل الإدارة."
FORCE_SUBSCRIBE_TEXT = (
    "🔒 يجب عليك الاشتراك في القناة أولاً لاستخدام البوت.\n\n"
    "اشترك ثم اضغط على زر التحقق من الاشتراك."
)

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
            "forced_sub_channel": "",
            "forced_sub_link": "",
            "bot_enabled": True,
            "referral_enabled": True,
        },
    )
    if "referral_points_per_invite" not in data:
        data["referral_points_per_invite"] = 1
    if "blocked_users" not in data or not isinstance(data["blocked_users"], list):
        data["blocked_users"] = []
    if "forced_sub_channel" not in data:
        data["forced_sub_channel"] = ""
    if "forced_sub_link" not in data:
        data["forced_sub_link"] = ""
    if "bot_enabled" not in data:
        data["bot_enabled"] = True
    if "referral_enabled" not in data:
        data["referral_enabled"] = True
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


def is_bot_enabled() -> bool:
    config = load_config()
    return bool(config.get("bot_enabled", True))


def is_referral_enabled() -> bool:
    config = load_config()
    return bool(config.get("referral_enabled", True))


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


def register_referral(new_user_id: int, referrer_id: int) -> bool:
    if new_user_id == referrer_id:
        return False

    users_data = load_users()
    config = load_config()

    new_uid = str(new_user_id)
    ref_uid = str(referrer_id)

    if new_uid not in users_data["users"] or ref_uid not in users_data["users"]:
        return False

    new_user = users_data["users"][new_uid]
    ref_user = users_data["users"][ref_uid]

    if new_user.get("referred_by"):
        return False

    new_user["referred_by"] = referrer_id

    referrals = ref_user.get("referrals", [])
    if new_user_id not in referrals:
        referrals.append(new_user_id)
    ref_user["referrals"] = referrals

    points = int(config.get("referral_points_per_invite", 1))
    ref_user["points"] = int(ref_user.get("points", 0)) + points
    ref_user["total_points_earned"] = int(ref_user.get("total_points_earned", 0)) + points

    save_users(users_data)
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


def normalize_channel_input(text: str) -> tuple[str, str]:
    t = (text or "").strip()

    if not t:
        raise ValueError("Empty channel")

    if t.startswith("https://t.me/"):
        username = t.replace("https://t.me/", "").strip().strip("/")
        if not username:
            raise ValueError("Invalid channel link")
        if username.startswith("+"):
            raise ValueError("Invite links are not supported")
        return f"@{username}", f"https://t.me/{username}"

    if t.startswith("http://t.me/"):
        username = t.replace("http://t.me/", "").strip().strip("/")
        if not username:
            raise ValueError("Invalid channel link")
        if username.startswith("+"):
            raise ValueError("Invite links are not supported")
        return f"@{username}", f"https://t.me/{username}"

    if t.startswith("@"):
        username = t[1:].strip()
        if not username:
            raise ValueError("Invalid username")
        return f"@{username}", f"https://t.me/{username}"

    if re.fullmatch(r"-?\d+", t):
        return t, ""

    raise ValueError("Invalid channel format")


async def is_user_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    config = load_config()
    forced_sub_channel = (config.get("forced_sub_channel") or "").strip()

    if not forced_sub_channel:
        return True

    try:
        member = await context.bot.get_chat_member(chat_id=forced_sub_channel, user_id=user_id)
        status = getattr(member, "status", "")
        return status in ("member", "administrator", "creator", "restricted")
    except Exception:
        return False


def force_subscribe_menu() -> InlineKeyboardMarkup:
    config = load_config()
    rows = []

    forced_sub_link = (config.get("forced_sub_link") or "").strip()
    if forced_sub_link:
        rows.append([InlineKeyboardButton("📢 الاشتراك في القناة", url=forced_sub_link)])

    rows.append([InlineKeyboardButton("✅ التحقق من الاشتراك", callback_data="check_subscription")])

    return InlineKeyboardMarkup(rows)


async def enforce_access(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int | None) -> bool:
    if not user_id:
        return False

    if is_admin(user_id):
        return True

    if is_blocked(user_id):
        if update.callback_query:
            await update.callback_query.edit_message_text(BLOCKED_TEXT)
        else:
            await update.effective_message.reply_text(BLOCKED_TEXT)
        return False

    if not is_bot_enabled():
        if update.callback_query:
            await update.callback_query.edit_message_text(BOT_STOPPED_TEXT)
        else:
            await update.effective_message.reply_text(BOT_STOPPED_TEXT)
        return False

    subscribed = await is_user_subscribed(context, user_id)
    if not subscribed:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                FORCE_SUBSCRIBE_TEXT,
                reply_markup=force_subscribe_menu(),
            )
        else:
            await update.effective_message.reply_text(
                FORCE_SUBSCRIBE_TEXT,
                reply_markup=force_subscribe_menu(),
            )
        return False

    return True


# ================= واجهة القوائم =================
def main_menu(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []

    if is_referral_enabled():
        rows.append([InlineKeyboardButton("🎁 نظام الإحالة", callback_data="referral_menu")])

    rows.extend(
        [
            [
                InlineKeyboardButton("💰 تحويل قديم → جديد", callback_data="old_to_new"),
                InlineKeyboardButton("💵 تحويل جديد → قديم", callback_data="new_to_old"),
            ],
            [InlineKeyboardButton("ℹ️ شرح سريع", callback_data="quick_help")],
        ]
    )

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
    config = load_config()
    bot_toggle_text = "🛑 إيقاف البوت" if config.get("bot_enabled", True) else "▶️ تشغيل البوت"
    referral_toggle_text = "🙈 إخفاء نظام الإحالة" if config.get("referral_enabled", True) else "👁 إظهار نظام الإحالة"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚫 حظر شخص", callback_data="admin_ban")],
            [InlineKeyboardButton("✅ فك حظر شخص", callback_data="admin_unban")],
            [InlineKeyboardButton("📢 إذاعة للكل", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🎁 إدارة الاستبدال", callback_data="admin_manage_rewards")],
            [InlineKeyboardButton("⭐ تعديل مكافأة الإحالة", callback_data="admin_ref_points")],
            [InlineKeyboardButton("🎯 منح نقاط", callback_data="admin_grant_points")],
            [InlineKeyboardButton("📡 تعيين قناة الاشتراك", callback_data="admin_set_force_sub")],
            [InlineKeyboardButton(referral_toggle_text, callback_data="admin_toggle_referral")],
            [InlineKeyboardButton(bot_toggle_text, callback_data="admin_toggle_bot")],
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

    if not is_admin(user.id) and not is_bot_enabled():
        await update.effective_message.reply_text(BOT_STOPPED_TEXT)
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
            done = register_referral(user.id, referrer_id)
            if done and referrer_id != user.id:
                config = load_config()
                points = int(config.get("referral_points_per_invite", 1))
                username = f"@{user.username}" if user.username else "بدون يوزرنيم"
                full_name = (user.full_name or "").strip() or "مستخدم جديد"
                notify_text = (
                    "🎉 تم تسجيل شخص جديد من خلال رابط إحالتك\n\n"
                    f"👤 الاسم: {full_name}\n"
                    f"🔗 Username: {username}\n"
                    f"⭐ تمت إضافة {points} نقطة إلى رصيدك"
                )
                try:
                    await context.bot.send_message(chat_id=referrer_id, text=notify_text)
                except Exception:
                    pass
        except Exception:
            pass

    context.user_data.pop(MODE_KEY, None)
    context.user_data.pop(ADMIN_ACTION_KEY, None)
    context.user_data.pop(REFERRAL_ACTION_KEY, None)
    context.user_data.pop("new_reward_name", None)
    context.user_data.pop("selected_reward_id", None)
    context.user_data.pop("grant_points_user_id", None)

    if not is_admin(user.id):
        subscribed = await is_user_subscribed(context, user.id)
        if not subscribed:
            await update.effective_message.reply_text(
                FORCE_SUBSCRIBE_TEXT,
                reply_markup=force_subscribe_menu(),
            )
            return

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

    if q.data == "check_subscription":
        if is_admin(user.id):
            await q.edit_message_text(WELCOME_TEXT, reply_markup=main_menu(user.id))
            return

        if is_blocked(user.id):
            await q.edit_message_text(BLOCKED_TEXT)
            return

        if not is_bot_enabled():
            await q.edit_message_text(BOT_STOPPED_TEXT)
            return

        subscribed = await is_user_subscribed(context, user.id)
        if subscribed:
            await q.edit_message_text(
                "✅ تم التحقق من اشتراكك بنجاح.\n\n" + WELCOME_TEXT,
                reply_markup=main_menu(user.id),
            )
        else:
            await q.answer("❌ لم يتم العثور على اشتراكك بعد.", show_alert=True)
            await q.edit_message_text(
                FORCE_SUBSCRIBE_TEXT,
                reply_markup=force_subscribe_menu(),
            )
        return

    allowed = await enforce_access(update, context, user.id)
    if not allowed:
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
        if not is_referral_enabled() and not is_admin(user.id):
            await q.answer("❌ نظام الإحالة مخفي حالياً.", show_alert=True)
            return

        await q.edit_message_text(
            "🎁 نظام الإحالة\n\nاختر القسم الذي تريده:",
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
            f"🎁 عدد مرات الاستبدال: {stats['redeem_count']}",
            reply_markup=referral_menu(),
        )
        return

    if q.data == "my_ref_link":
        bot_username = get_bot_username(context)
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        await q.edit_message_text(
            "🔗 رابط الإحالة الخاص بك:\n\n"
            f"{ref_link}\n\n"
            "📌 أرسل الرابط لأصدقائك، وكل شخص يدخل من خلاله يمنحك نقاطًا حسب مكافأة الإحالة الحالية.",
            reply_markup=referral_menu(),
        )
        return

    if q.data == "ref_leaderboard":
        leaders = get_leaderboard(limit=10)

        if not leaders:
            text = "🏆 المتصدرين\n\nلا يوجد متصدرون حالياً."
        else:
            lines = ["🏆 المتصدرين\n"]
            medals = ["1️⃣", "2️⃣", "3️⃣"]
            for idx, leader in enumerate(leaders, start=1):
                marker = medals[idx - 1] if idx <= 3 else f"{idx}."
                lines.append(f"{marker} {leader['full_name']} — {leader['referrals_count']} إحالة")
            text = "\n".join(lines)

        await q.edit_message_text(text, reply_markup=referral_menu())
        return

    if q.data == "redeem_points":
        rewards = load_rewards().get("items", [])

        if not rewards:
            await q.edit_message_text(
                "🎁 قسم الاستبدال\n\nلا توجد سلع متاحة حاليًا.",
                reply_markup=referral_menu(),
            )
            return

        if user_has_pending_redeem(user.id):
            await q.answer("طلبك قيد المراجعة، انتظر رد الإدارة.", show_alert=True)
            return

        await q.edit_message_text(
            "🎁 استبدال النقاط\n\nاختر الجائزة التي تريد استبدالها:",
            reply_markup=rewards_inline_menu(rewards, "redeem_item", "referral_menu"),
        )
        return

    if q.data.startswith("redeem_item:"):
        try:
            reward_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.answer("❌ حدث خطأ في اختيار السلعة.", show_alert=True)
            return

        item = get_reward_by_id(reward_id)
        if not item:
            await q.answer("❌ هذه السلعة غير موجودة.", show_alert=True)
            return

        if user_has_pending_redeem(user.id):
            await q.answer("طلبك قيد المراجعة، انتظر رد الإدارة.", show_alert=True)
            return

        users_data = load_users()
        user_data = users_data["users"].get(str(user.id))
        if not user_data:
            return

        current_points = int(user_data.get("points", 0))
        cost = int(item.get("cost", 0))

        if current_points < cost:
            await q.answer("❌ نقاطك غير كافية لهذا الاستبدال.", show_alert=True)
            return

        # خصم مباشر
        user_data["points"] = current_points - cost
        save_users(users_data)

        # إنشاء طلب قيد المراجعة
        create_pending_redeem(user, item)

        admin_id = _get_admin_id()
        if admin_id:
            username = f"@{user.username}" if user.username else "بدون"
            full_name = user.full_name or "ㅤ"
            admin_msg = (
                "🚨 طلب استبدال جديد\n"
                f"👤 الاسم: {full_name}\n"
                f"🆔 ID: {user.id}\n"
                f"🔗 Username: {username}\n"
                f"🎁 السلعة: {item['name']}\n"
                f"⭐ التكلفة: {cost} نقطة"
            )
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_msg,
                    reply_markup=admin_redeem_request_menu(user.id),
                )
            except Exception:
                pass

        await q.edit_message_text(
            "✅ تم إرسال طلب الاستبدال إلى الإدارة بنجاح.",
            reply_markup=referral_menu(),
        )
        return

    # ================= لوحة الأدمن =================
    if q.data == "admin_menu":
        if not is_admin(user.id):
            return
        await q.edit_message_text(
            "⚙️ لوحة الأدمن\n\nاختر العملية التي تريدها:",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_ban":
        if not is_admin(user.id):
            return
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_BAN
        await q.edit_message_text(
            "🚫 حظر شخص\n\nأرسل الآن ID المستخدم الذي تريد حظره.",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_unban":
        if not is_admin(user.id):
            return
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_UNBAN
        await q.edit_message_text(
            "✅ فك حظر شخص\n\nأرسل الآن ID المستخدم الذي تريد فك حظره.",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_broadcast":
        if not is_admin(user.id):
            return
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_BROADCAST
        await q.edit_message_text(
            "📢 إذاعة للكل\n\nأرسل الآن الرسالة التي تريد إرسالها لجميع المستخدمين.",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_ref_points":
        if not is_admin(user.id):
            return
        config = load_config()
        current = int(config.get("referral_points_per_invite", 1))
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_REWARD_POINTS
        await q.edit_message_text(
            "⭐ تعديل مكافأة الإحالة\n\n"
            f"المكافأة الحالية: {current} نقطة لكل إحالة\n\n"
            "أرسل الآن العدد الجديد.",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_grant_points":
        if not is_admin(user.id):
            return
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_GRANT_POINTS_USER_ID
        await q.edit_message_text(
            "🎯 منح نقاط\n\nأرسل الآن ID المستخدم.",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_set_force_sub":
        if not is_admin(user.id):
            return
        config = load_config()
        current_channel = (config.get("forced_sub_channel") or "").strip() or "غير معين"
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_FORCE_SUB_CHANNEL
        await q.edit_message_text(
            "📡 تعيين قناة الاشتراك الإجباري\n\n"
            f"القناة الحالية: {current_channel}\n\n"
            "أرسل الآن يوزر القناة بهذا الشكل:\n"
            "@channelusername\n\n"
            "أو رابطها بهذا الشكل:\n"
            "https://t.me/channelusername\n\n"
            "أو أرسل 0 لإلغاء الاشتراك الإجباري.",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_toggle_referral":
        if not is_admin(user.id):
            return

        config = load_config()
        current = bool(config.get("referral_enabled", True))
        config["referral_enabled"] = not current
        save_config(config)

        status_text = "✅ تم إظهار نظام الإحالة." if config["referral_enabled"] else "🙈 تم إخفاء نظام الإحالة."
        await q.edit_message_text(
            status_text,
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_toggle_bot":
        if not is_admin(user.id):
            return

        config = load_config()
        current = bool(config.get("bot_enabled", True))
        config["bot_enabled"] = not current
        save_config(config)

        status_text = "✅ تم تشغيل البوت." if config["bot_enabled"] else "🛑 تم إيقاف البوت."
        await q.edit_message_text(
            status_text,
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_user_count":
        if not is_admin(user.id):
            return
        users_data = load_users()
        blocked = len(load_config().get("blocked_users", []))
        total = len(users_data.get("users", {}))
        await q.edit_message_text(
            "📊 إحصائيات المستخدمين\n\n"
            f"👥 إجمالي المستخدمين: {total}\n"
            f"⛔ عدد المحظورين: {blocked}",
            reply_markup=admin_menu(),
        )
        return

    if q.data == "admin_manage_rewards":
        if not is_admin(user.id):
            return
        await q.edit_message_text(
            "🎁 إدارة الاستبدال\n\nاختر العملية التي تريدها:",
            reply_markup=admin_rewards_menu(),
        )
        return

    if q.data == "admin_add_reward":
        if not is_admin(user.id):
            return
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_ADD_ITEM_NAME
        await q.edit_message_text(
            "➕ إضافة سلعة\n\nأرسل الآن اسم السلعة الجديدة.",
            reply_markup=admin_rewards_menu(),
        )
        return

    if q.data == "admin_list_rewards":
        if not is_admin(user.id):
            return

        rewards = load_rewards().get("items", [])
        if not rewards:
            await q.edit_message_text(
                "📦 عرض السلع\n\nلا توجد سلع حالياً.",
                reply_markup=admin_rewards_menu(),
            )
            return

        await q.edit_message_text(
            "📦 السلع الحالية\n\nاضغط على السلعة التي تريد إدارتها:",
            reply_markup=rewards_inline_menu(rewards, "admin_reward", "admin_manage_rewards"),
        )
        return

    if q.data.startswith("admin_reward:"):
        if not is_admin(user.id):
            return

        try:
            reward_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.answer("❌ خطأ في السلعة.", show_alert=True)
            return

        reward = get_reward_by_id(reward_id)
        if not reward:
            await q.answer("❌ هذه السلعة غير موجودة.", show_alert=True)
            return

        context.user_data["selected_reward_id"] = reward_id
        await q.edit_message_text(
            f"🎁 {reward['name']}\n\n⭐ السعر: {reward['cost']} نقطة",
            reply_markup=selected_reward_menu(reward_id),
        )
        return

    if q.data.startswith("admin_edit_reward_name:"):
        if not is_admin(user.id):
            return

        try:
            reward_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.answer("❌ خطأ.", show_alert=True)
            return

        reward = get_reward_by_id(reward_id)
        if not reward:
            await q.answer("❌ هذه السلعة غير موجودة.", show_alert=True)
            return

        context.user_data["selected_reward_id"] = reward_id
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_EDIT_ITEM_NAME

        await q.edit_message_text(
            f"✏️ تعديل الاسم\n\nالاسم الحالي: {reward['name']}\n\nأرسل الاسم الجديد.",
            reply_markup=selected_reward_menu(reward_id),
        )
        return

    if q.data.startswith("admin_edit_reward_cost:"):
        if not is_admin(user.id):
            return

        try:
            reward_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.answer("❌ خطأ.", show_alert=True)
            return

        reward = get_reward_by_id(reward_id)
        if not reward:
            await q.answer("❌ هذه السلعة غير موجودة.", show_alert=True)
            return

        context.user_data["selected_reward_id"] = reward_id
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_EDIT_ITEM_COST

        await q.edit_message_text(
            f"💰 تعديل السعر\n\nالسلعة: {reward['name']}\nالسعر الحالي: {reward['cost']} نقطة\n\nأرسل السعر الجديد.",
            reply_markup=selected_reward_menu(reward_id),
        )
        return

    if q.data.startswith("admin_delete_reward:"):
        if not is_admin(user.id):
            return

        try:
            reward_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.answer("❌ خطأ.", show_alert=True)
            return

        reward = get_reward_by_id(reward_id)
        if not reward:
            await q.answer("❌ هذه السلعة غير موجودة.", show_alert=True)
            return

        delete_reward_by_id(reward_id)
        context.user_data.pop("selected_reward_id", None)

        await q.edit_message_text(
            f"✅ تم حذف السلعة: {reward['name']}",
            reply_markup=admin_rewards_menu(),
        )
        return

    if q.data.startswith("admin_accept_redeem:"):
        if not is_admin(user.id):
            return

        try:
            target_user_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.answer("❌ خطأ.", show_alert=True)
            return

        req = get_pending_redeem(target_user_id)
        if not req:
            await q.answer("❌ الطلب غير موجود أو تمت معالجته.", show_alert=True)
            return

        set_pending_redeem_status(target_user_id, "accepted")
        remove_pending_redeem(target_user_id)

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="✅ تم قبول طلبك.",
            )
        except Exception:
            pass

        await q.edit_message_text("✅ تم قبول الطلب.")
        return

    if q.data.startswith("admin_reject_redeem:"):
        if not is_admin(user.id):
            return

        try:
            target_user_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.answer("❌ خطأ.", show_alert=True)
            return

        req = get_pending_redeem(target_user_id)
        if not req:
            await q.answer("❌ الطلب غير موجود أو تمت معالجته.", show_alert=True)
            return

        users_data = load_users()
        user_data = users_data["users"].get(str(target_user_id))
        if user_data:
            user_data["points"] = int(user_data.get("points", 0)) + int(req.get("cost", 0))
            save_users(users_data)

        set_pending_redeem_status(target_user_id, "rejected")
        remove_pending_redeem(target_user_id)

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ تم رفض طلبك وتم استرجاع نقاطك.",
            )
        except Exception:
            pass

        await q.edit_message_text("❌ تم رفض الطلب وإرجاع النقاط للمستخدم.")
        return


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    ensure_user_exists(user)

    allowed = await enforce_access(update, context, user.id)
    if not allowed:
        return

    admin_action = context.user_data.get(ADMIN_ACTION_KEY)

    # ================= إجراءات الأدمن =================
    if is_admin(user.id) and admin_action:
        text = update.effective_message.text or ""

        if admin_action == ADMIN_WAIT_BAN:
            try:
                target_id = parse_int(text)
                config = load_config()
                blocked_users = set(config.get("blocked_users", []))
                blocked_users.add(target_id)
                config["blocked_users"] = sorted(blocked_users)
                save_config(config)
                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم حظر المستخدم: {target_id}",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل ID صحيح فقط.",
                    reply_markup=admin_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_UNBAN:
            try:
                target_id = parse_int(text)
                config = load_config()
                blocked_users = set(config.get("blocked_users", []))
                blocked_users.discard(target_id)
                config["blocked_users"] = sorted(blocked_users)
                save_config(config)
                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم فك حظر المستخدم: {target_id}",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل ID صحيح فقط.",
                    reply_markup=admin_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_BROADCAST:
            users_data = load_users()
            users = users_data.get("users", {})
            sent = 0
            failed = 0

            for uid in users:
                try:
                    await context.bot.send_message(chat_id=int(uid), text=text)
                    sent += 1
                except Exception:
                    failed += 1

            context.user_data.pop(ADMIN_ACTION_KEY, None)
            await update.effective_message.reply_text(
                "📢 انتهت الإذاعة\n\n"
                f"✅ تم الإرسال إلى: {sent}\n"
                f"❌ فشل الإرسال إلى: {failed}",
                reply_markup=admin_menu(),
            )
            return

        if admin_action == ADMIN_WAIT_REWARD_POINTS:
            try:
                points = parse_int(text)
                config = load_config()
                config["referral_points_per_invite"] = points
                save_config(config)
                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم تحديث مكافأة الإحالة إلى: {points} نقطة لكل إحالة",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل رقمًا صحيحًا فقط.",
                    reply_markup=admin_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_GRANT_POINTS_USER_ID:
            try:
                target_id = parse_int(text)
                users_data = load_users()
                if str(target_id) not in users_data.get("users", {}):
                    await update.effective_message.reply_text(
                        "❌ هذا المستخدم غير موجود في السجل.",
                        reply_markup=admin_menu(),
                    )
                    return

                context.user_data["grant_points_user_id"] = target_id
                context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_GRANT_POINTS_AMOUNT

                await update.effective_message.reply_text(
                    f"🎯 المستخدم: {target_id}\n\nأرسل الآن عدد النقاط التي تريد منحها.",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل ID صحيح فقط.",
                    reply_markup=admin_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_GRANT_POINTS_AMOUNT:
            try:
                amount = parse_int(text)
                target_id = int(context.user_data.get("grant_points_user_id"))
                users_data = load_users()
                user_data = users_data["users"].get(str(target_id))
                if not user_data:
                    raise ValueError("User not found")

                user_data["points"] = int(user_data.get("points", 0)) + amount
                user_data["total_points_earned"] = int(user_data.get("total_points_earned", 0)) + amount
                save_users(users_data)

                context.user_data.pop("grant_points_user_id", None)
                context.user_data.pop(ADMIN_ACTION_KEY, None)

                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=f"⭐ تم إضافة {amount} نقطة إلى حسابك.",
                    )
                except Exception:
                    pass

                await update.effective_message.reply_text(
                    f"✅ تم منح {amount} نقطة للمستخدم: {target_id}",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل رقمًا صحيحًا فقط.",
                    reply_markup=admin_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_FORCE_SUB_CHANNEL:
            try:
                raw = text.strip()
                config = load_config()

                if raw == "0":
                    config["forced_sub_channel"] = ""
                    config["forced_sub_link"] = ""
                    save_config(config)
                    context.user_data.pop(ADMIN_ACTION_KEY, None)

                    await update.effective_message.reply_text(
                        "✅ تم إلغاء الاشتراك الإجباري.",
                        reply_markup=admin_menu(),
                    )
                    return

                forced_sub_channel, forced_sub_link = normalize_channel_input(raw)

                if forced_sub_channel.startswith("@"):
                    chat = await context.bot.get_chat(forced_sub_channel)
                    bot_info = await context.bot.get_me()
                    member = await context.bot.get_chat_member(chat.id, bot_info.id)
                    status = getattr(member, "status", "")
                    if status not in ("administrator", "creator"):
                        await update.effective_message.reply_text(
                            "❌ يجب إضافة البوت داخل القناة ورفعه أدمن أولاً حتى يتمكن من التحقق من الاشتراك.",
                            reply_markup=admin_menu(),
                        )
                        return

                config["forced_sub_channel"] = forced_sub_channel
                config["forced_sub_link"] = forced_sub_link
                save_config(config)
                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم تعيين قناة الاشتراك الإجباري:\n{forced_sub_channel}",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل يوزر قناة صحيح مثل @channelusername أو رابط صحيح للقناة العامة.",
                    reply_markup=admin_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_ADD_ITEM_NAME:
            item_name = text.strip()
            if not item_name:
                await update.effective_message.reply_text(
                    "❌ أرسل اسم سلعة صحيح.",
                    reply_markup=admin_rewards_menu(),
                )
                return

            context.user_data["new_reward_name"] = item_name
            context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_ADD_ITEM_COST

            await update.effective_message.reply_text(
                f"📝 اسم السلعة: {item_name}\n\nأرسل الآن تكلفة السلعة بالنقاط.",
                reply_markup=admin_rewards_menu(),
            )
            return

        if admin_action == ADMIN_WAIT_ADD_ITEM_COST:
            try:
                cost = parse_int(text)
                item_name = context.user_data.get("new_reward_name", "").strip()
                if not item_name:
                    raise ValueError("Missing item name")

                rewards_data = load_rewards()
                rewards_data["items"].append(
                    {
                        "id": get_next_reward_id(),
                        "name": item_name,
                        "cost": cost,
                    }
                )
                save_rewards(rewards_data)

                context.user_data.pop("new_reward_name", None)
                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم حفظ السلعة:\n• {item_name} — {cost} نقطة",
                    reply_markup=admin_rewards_menu(),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل رقمًا صحيحًا لتكلفة السلعة.",
                    reply_markup=admin_rewards_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_EDIT_ITEM_NAME:
            try:
                reward_id = int(context.user_data.get("selected_reward_id"))
                new_name = text.strip()
                if not new_name:
                    raise ValueError("Empty name")

                done = update_reward_name(reward_id, new_name)
                if not done:
                    raise ValueError("Reward not found")

                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم تعديل اسم السلعة إلى: {new_name}",
                    reply_markup=selected_reward_menu(reward_id),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل اسمًا صحيحًا.",
                    reply_markup=admin_rewards_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_EDIT_ITEM_COST:
            try:
                reward_id = int(context.user_data.get("selected_reward_id"))
                new_cost = parse_int(text)

                done = update_reward_cost(reward_id, new_cost)
                if not done:
                    raise ValueError("Reward not found")

                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم تعديل سعر السلعة إلى: {new_cost} نقطة",
                    reply_markup=selected_reward_menu(reward_id),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل رقمًا صحيحًا فقط.",
                    reply_markup=admin_rewards_menu(),
                )
            return

    # ================= التحويل الأساسي =================
    mode = context.user_data.get(MODE_KEY)
    if mode not in ("old_to_new", "new_to_old"):
        return

    try:
        amount = normalize_amount(update.effective_message.text)
    except Exception:
        await update.effective_message.reply_text(
            "❌ ما قدرت أفهم الرقم.\nاكتب رقم فقط مثل: 125000 أو 125,000",
            reply_markup=back_menu(user.id),
        )
        return

    if amount < 0:
        await update.effective_message.reply_text(
            "❌ رجاءً اكتب مبلغ موجب.",
            reply_markup=back_menu(user.id),
        )
        return

    if mode == "old_to_new":
        old_val = amount
        new_val = amount / FACTOR
        reply = (
            "💱 ✅ نتيجة التحويل\n\n"
            f"• المبلغ القديم: {fmt_number(old_val)} عملة قديمة\n"
            f"• المبلغ الجديد: {fmt_number(new_val)} عملة جديدة"
        )
    else:
        new_val = amount
        old_val = amount * FACTOR
        reply = (
            "💱 ✅ نتيجة التحويل\n\n"
            f"• المبلغ الجديد: {fmt_number(new_val)} عملة جديدة\n"
            f"• المبلغ القديم: {fmt_number(old_val)} عملة قديمة"
        )

    await update.effective_message.reply_text(reply, reply_markup=back_menu(user.id))


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
