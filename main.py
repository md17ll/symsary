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


def get_leaderboard(limit: int = 10) -> list[dict]:
    users_data = load_users()
    results = []
    for user in users_data.get("users", {}).values():
        referrals_count = len(user.get("referrals", []))
        if referrals_count <= 0:
            continue
        name = (user.get("full_name") or "").strip() or "مستخدم"
        results.append(
            {
                "name": name,
                "referrals_count": referrals_count,
            }
        )

    results.sort(key=lambda x: x["referrals_count"], reverse=True)
    return results[:limit]


def find_reward_by_id(item_id: int):
    rewards = load_rewards()
    for item in rewards.get("items", []):
        if int(item.get("id", 0)) == int(item_id):
            return item
    return None


def get_next_reward_id(items: list[dict]) -> int:
    if not items:
        return 1
    return max(int(item.get("id", 0)) for item in items) + 1


def build_rewards_buttons(prefix: str, items: list[dict], include_back_to: str):
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
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=include_back_to)])
    return InlineKeyboardMarkup(rows)


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
            register_referral(user.id, referrer_id)
        except Exception:
            pass

    context.user_data.pop(MODE_KEY, None)
    context.user_data.pop(ADMIN_ACTION_KEY, None)
    context.user_data.pop(REFERRAL_ACTION_KEY, None)
    context.user_data.pop("new_reward_name", None)
    context.user_data.pop("selected_reward_id", None)

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

    if q.data == "back":
        context.user_data.pop(MODE_KEY, None)
        context.user_data.pop(ADMIN_ACTION_KEY, None)
        context.user_data.pop(REFERRAL_ACTION_KEY, None)
        context.user_data.pop("new_reward_name", None)
        context.user_data.pop("selected_reward_id", None)
        await q.edit_message_text(WELCOME_TEXT, reply_markup=main_menu(user.id))
        return

    if q.data == "quick_help":
        context.user_data.pop(ADMIN_ACTION_KEY, None)
        context.user_data.pop(REFERRAL_ACTION_KEY, None)
        await q.edit_message_text(HELP_TEXT, reply_markup=back_menu(user.id))
        return

    if q.data == "new_to_old":
        context.user_data.pop(ADMIN_ACTION_KEY, None)
        context.user_data.pop(REFERRAL_ACTION_KEY, None)
        context.user_data[MODE_KEY] = "new_to_old"
        await q.edit_message_text(
            "🧮 تحويل جديد → قديم\n"
            "اكتب المبلغ بالعملة الجديدة الآن:\n"
            "مثال: 1250",
            reply_markup=back_menu(user.id),
        )
        return

    if q.data == "old_to_new":
        context.user_data.pop(ADMIN_ACTION_KEY, None)
        context.user_data.pop(REFERRAL_ACTION_KEY, None)
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
        context.user_data.pop(ADMIN_ACTION_KEY, None)
        context.user_data.pop(REFERRAL_ACTION_KEY, None)
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
                lines.append(f"{marker} {leader['name']} — {leader['referrals_count']} إحالة")
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

        context.user_data.pop(REFERRAL_ACTION_KEY, None)
        await q.edit_message_text(
            "🎁 استبدال النقاط\n\nاختر الجائزة التي تريد استبدالها:",
            reply_markup=build_rewards_buttons(
                prefix="redeem_reward",
                items=rewards,
                include_back_to="referral_menu",
            ),
        )
        return

    if q.data.startswith("redeem_reward:"):
        try:
            item_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.edit_message_text("❌ حدث خطأ في اختيار السلعة.", reply_markup=referral_menu())
            return

        selected_item = find_reward_by_id(item_id)
        if not selected_item:
            await q.edit_message_text("❌ هذه السلعة غير موجودة.", reply_markup=referral_menu())
            return

        users_data = load_users()
        uid = str(user.id)
        user_data = users_data["users"].get(uid)
        if not user_data:
            ensure_user_exists(user)
            users_data = load_users()
            user_data = users_data["users"].get(uid)

        current_points = int(user_data.get("points", 0))
        cost = int(selected_item["cost"])

        if current_points < cost:
            await q.edit_message_text(
                "❌ نقاطك غير كافية لهذا الاستبدال.",
                reply_markup=build_rewards_buttons(
                    prefix="redeem_reward",
                    items=load_rewards().get("items", []),
                    include_back_to="referral_menu",
                ),
            )
            return

        user_data["points"] = current_points - cost
        user_data["redeem_count"] = int(user_data.get("redeem_count", 0)) + 1
        save_users(users_data)

        admin_id = _get_admin_id()
        if admin_id:
            username = f"@{user.username}" if user.username else "بدون"
            full_name = user.full_name or "بدون"
            admin_msg = (
                "🚨 طلب استبدال جديد\n\n"
                f"👤 الاسم: {full_name}\n"
                f"🆔 ID: {user.id}\n"
                f"🔗 Username: {username}\n"
                f"🎁 السلعة: {selected_item['name']}\n"
                f"⭐ التكلفة: {cost} نقطة"
            )
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_msg)
            except Exception:
                pass

        await q.edit_message_text(
            "✅ تم إرسال طلب الاستبدال إلى الأدمن بنجاح.\n"
            f"🎁 السلعة: {selected_item['name']}\n"
            f"⭐ تم خصم: {cost} نقطة",
            reply_markup=referral_menu(),
        )
        return

    # ================= لوحة الأدمن =================
    if q.data == "admin_menu":
        if not is_admin(user.id):
            return
        context.user_data.pop(ADMIN_ACTION_KEY, None)
        context.user_data.pop(REFERRAL_ACTION_KEY, None)
        context.user_data.pop("new_reward_name", None)
        context.user_data.pop("selected_reward_id", None)
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
        context.user_data.pop(ADMIN_ACTION_KEY, None)
        context.user_data.pop("new_reward_name", None)
        context.user_data.pop("selected_reward_id", None)
        await q.edit_message_text(
            "🎁 إدارة الاستبدال\n\nاختر العملية التي تريدها:",
            reply_markup=admin_rewards_menu(),
        )
        return

    if q.data == "admin_add_reward":
        if not is_admin(user.id):
            return
        context.user_data.pop("selected_reward_id", None)
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
            reply_markup=build_rewards_buttons(
                prefix="admin_select_reward",
                items=rewards,
                include_back_to="admin_manage_rewards",
            ),
        )
        return

    if q.data.startswith("admin_select_reward:"):
        if not is_admin(user.id):
            return
        try:
            item_id = int(q.data.split(":", 1)[1])
        except Exception:
            await q.edit_message_text("❌ حدث خطأ في اختيار السلعة.", reply_markup=admin_rewards_menu())
            return

        item = find_reward_by_id(item_id)
        if not item:
            await q.edit_message_text("❌ هذه السلعة غير موجودة.", reply_markup=admin_rewards_menu())
            return

        context.user_data["selected_reward_id"] = item_id
        context.user_data.pop(ADMIN_ACTION_KEY, None)

        await q.edit_message_text(
            f"🎁 {item['name']}\n\nالسعر: {item['cost']} نقطة",
            reply_markup=selected_reward_menu(item_id),
        )
        return

    if q.data.startswith("admin_edit_reward_name:"):
        if not is_admin(user.id):
            return
        try:
            item_id = int(q.data.split(":", 1)[1])
        except Exception:
            return

        item = find_reward_by_id(item_id)
        if not item:
            await q.edit_message_text("❌ هذه السلعة غير موجودة.", reply_markup=admin_rewards_menu())
            return

        context.user_data["selected_reward_id"] = item_id
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_EDIT_ITEM_NAME

        await q.edit_message_text(
            f"✏️ تعديل اسم السلعة\n\nالاسم الحالي: {item['name']}\n\nأرسل الآن الاسم الجديد.",
            reply_markup=selected_reward_menu(item_id),
        )
        return

    if q.data.startswith("admin_edit_reward_cost:"):
        if not is_admin(user.id):
            return
        try:
            item_id = int(q.data.split(":", 1)[1])
        except Exception:
            return

        item = find_reward_by_id(item_id)
        if not item:
            await q.edit_message_text("❌ هذه السلعة غير موجودة.", reply_markup=admin_rewards_menu())
            return

        context.user_data["selected_reward_id"] = item_id
        context.user_data[ADMIN_ACTION_KEY] = ADMIN_WAIT_EDIT_ITEM_COST

        await q.edit_message_text(
            f"💰 تعديل سعر السلعة\n\nالسلعة: {item['name']}\nالسعر الحالي: {item['cost']} نقطة\n\nأرسل الآن السعر الجديد.",
            reply_markup=selected_reward_menu(item_id),
        )
        return

    if q.data.startswith("admin_delete_reward:"):
        if not is_admin(user.id):
            return
        try:
            item_id = int(q.data.split(":", 1)[1])
        except Exception:
            return

        rewards = load_rewards()
        items = rewards.get("items", [])
        item = None
        new_items = []

        for entry in items:
            if int(entry.get("id", 0)) == item_id:
                item = entry
            else:
                new_items.append(entry)

        if not item:
            await q.edit_message_text("❌ هذه السلعة غير موجودة.", reply_markup=admin_rewards_menu())
            return

        rewards["items"] = new_items
        save_rewards(rewards)
        context.user_data.pop("selected_reward_id", None)
        context.user_data.pop(ADMIN_ACTION_KEY, None)

        await q.edit_message_text(
            f"✅ تم حذف السلعة: {item['name']}",
            reply_markup=admin_rewards_menu(),
        )
        return


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    ensure_user_exists(user)

    if is_blocked(user.id):
        await update.effective_message.reply_text(BLOCKED_TEXT)
        return

    admin_action = context.user_data.get(ADMIN_ACTION_KEY)
    referral_action = context.user_data.get(REFERRAL_ACTION_KEY)

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

                rewards = load_rewards()
                items = rewards.get("items", [])

                items.append(
                    {
                        "id": get_next_reward_id(items),
                        "name": item_name,
                        "cost": cost,
                    }
                )

                rewards["items"] = items
                save_rewards(rewards)

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
                item_id = int(context.user_data.get("selected_reward_id"))
                new_name = text.strip()
                if not new_name:
                    raise ValueError("Empty name")

                rewards = load_rewards()
                item = None
                for entry in rewards.get("items", []):
                    if int(entry.get("id", 0)) == item_id:
                        entry["name"] = new_name
                        item = entry
                        break

                if not item:
                    raise ValueError("Item not found")

                save_rewards(rewards)
                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم تعديل اسم السلعة إلى: {new_name}",
                    reply_markup=selected_reward_menu(item_id),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل اسمًا صحيحًا.",
                    reply_markup=admin_rewards_menu(),
                )
            return

        if admin_action == ADMIN_WAIT_EDIT_ITEM_COST:
            try:
                item_id = int(context.user_data.get("selected_reward_id"))
                new_cost = parse_int(text)

                rewards = load_rewards()
                item = None
                for entry in rewards.get("items", []):
                    if int(entry.get("id", 0)) == item_id:
                        entry["cost"] = new_cost
                        item = entry
                        break

                if not item:
                    raise ValueError("Item not found")

                save_rewards(rewards)
                context.user_data.pop(ADMIN_ACTION_KEY, None)

                await update.effective_message.reply_text(
                    f"✅ تم تعديل سعر السلعة إلى: {new_cost} نقطة",
                    reply_markup=selected_reward_menu(item_id),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "❌ أرسل رقمًا صحيحًا فقط.",
                    reply_markup=admin_rewards_menu(),
                )
            return

    # ================= استبدال النقاط =================
    if referral_action == REF_WAIT_REDEEM:
        item_name = (update.effective_message.text or "").strip()
        rewards = load_rewards().get("items", [])
        selected_item = None

        for item in rewards:
            if item["name"].strip().lower() == item_name.lower():
                selected_item = item
                break

        if not selected_item:
            await update.effective_message.reply_text(
                "❌ لم أجد سلعة بهذا الاسم.\nأرسل الاسم تمامًا كما هو موجود في القائمة.",
                reply_markup=referral_menu(),
            )
            return

        users_data = load_users()
        uid = str(user.id)
        user_data = users_data["users"].get(uid)
        if not user_data:
            ensure_user_exists(user)
            users_data = load_users()
            user_data = users_data["users"].get(uid)

        current_points = int(user_data.get("points", 0))
        cost = int(selected_item["cost"])

        if current_points < cost:
            await update.effective_message.reply_text(
                "❌ نقاطك غير كافية لهذا الاستبدال.",
                reply_markup=referral_menu(),
            )
            return

        user_data["points"] = current_points - cost
        user_data["redeem_count"] = int(user_data.get("redeem_count", 0)) + 1
        save_users(users_data)

        context.user_data.pop(REFERRAL_ACTION_KEY, None)

        admin_id = _get_admin_id()
        if admin_id:
            username = f"@{user.username}" if user.username else "بدون"
            full_name = user.full_name or "بدون"
            admin_msg = (
                "🚨 طلب استبدال جديد\n\n"
                f"👤 الاسم: {full_name}\n"
                f"🆔 ID: {user.id}\n"
                f"🔗 Username: {username}\n"
                f"🎁 السلعة: {selected_item['name']}\n"
                f"⭐ التكلفة: {cost} نقطة"
            )
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_msg)
            except Exception:
                pass

        await update.effective_message.reply_text(
            "✅ تم إرسال طلب الاستبدال إلى الأدمن بنجاح.\n"
            f"🎁 السلعة: {selected_item['name']}\n"
            f"⭐ تم خصم: {cost} نقطة",
            reply_markup=referral_menu(),
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
