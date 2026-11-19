import os
import json
import time
import random
import html
import asyncio
import hashlib
import hmac
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError, TimedOut
IST = ZoneInfo("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)

from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)


# ============================================================
# BOT CONFIGURATION — for Wisbyte hosting, set values directly here
# ============================================================
# Paste your real values between the quotes below before starting the bot.
# Get bot tokens from @BotFather. Never publish this file or share your tokens.
BOT_TOKEN = "9128364392:AAFi7sB--5RQFIkqliPsXhaESRYDSREtEkM"
ADMIN_ID = 8385172584  # Enter your numeric Telegram user ID
OTP_BOT_TOKEN = "9221803182:AAHekoZw8sePDCDZiFll0KTPuyIBzHopanA"
RESELLER_BOT_TOKEN = "9250607625:AAHhSzXlQfvTGt57QjE7socWbgUx6jj8UR0"
RESELLER_BOT_LINK = "https://t.me/Tb_ResellerPanelBot"  # Replace with your reseller bot username

BOT_TOKEN = BOT_TOKEN.strip()
OTP_BOT_TOKEN = OTP_BOT_TOKEN.strip()
RESELLER_BOT_TOKEN = RESELLER_BOT_TOKEN.strip()
if not BOT_TOKEN or BOT_TOKEN.startswith("PASTE_"):
    raise RuntimeError("Set BOT_TOKEN directly near the top of main.py before starting the bot.")
if not ADMIN_ID:
    raise RuntimeError("Set your numeric Telegram user ID in ADMIN_ID near the top of main.py.")

DATA_FILES = [
    "balances.json", "balances.json", "reseller_panel_users.json", "orders.json", "temp.json", "users.json",
    "settings.json", "categories.json", "products.json", "coupons.json", "game_stats.json", "daily_tasks.json", "password_reset_requests.json", "tickets.json"
]

DEFAULT_SETTINGS = {
    "proof_link": "https://t.me/YourProofChannel",
    "howto_link": "https://t.me/YourHowToVideo",
    "support_user": "@YourSupportUsername",
    "whatsapp_support_link": "",
    "download_link": "https://t.me/YourDownloadChannel",
    "bot_enabled": True,
    "maintenance_message": "🛠️ <b>STORE IS CURRENTLY UNDER MAINTENANCE</b>\n\nPlease wait for a few minutes and try again.",
    "order_channel_id": "-1004301332161",
    "shop_bot_link": "https://t.me/TurboPaidPanelStoreBot",
    "reseller_enabled": True,
    "reseller_discount_percent": 50,
    "reseller_plans": [],
    "auto_broadcast_channel_id": "",
    "auto_broadcast_interval": "10M",
    "auto_broadcast_enabled": False,
    "auto_broadcast_items": [],
    "auto_broadcast_index": 0,
    "auto_broadcast_next_at": 0,
    "auto_broadcast_channels": {},
    "auto_broadcast_selected_channel": "",
    "auto_broadcast_bot": {"enabled": False, "interval": "10M", "items": [], "index": 0, "next_at": 0, "last_error": ""},
    "start_menu_buttons": {},
}

DEFAULT_CATEGORIES = {
    "c1": {"name": "Non-Root Mobile", "style": "success"},
    "c2": {"name": "Root Mobile", "style": "success"},
    "c3": {"name": "PC / Computer", "style": "success"},
    "c4": {"name": "iOS / iPhone", "style": "success"},
}

for filename in DATA_FILES:
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({}, f)

def load_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            value = json.load(f)
            return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

def save_json(filename, value):
    # Write to a temporary file and atomically replace the old JSON.
    # This prevents a host restart during a write from leaving settings.json
    # truncated and silently erasing saved broadcast channels/messages.
    temp_name = f"{filename}.tmp"
    with open(temp_name, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_name, filename)

settings = load_json("settings.json")
settings.pop("api_key", None)
for k, v in DEFAULT_SETTINGS.items():
    if k not in settings:
        settings[k] = v
settings.setdefault("ticket_daily_limit", 5)
if "lucky_spin_min_reward" not in settings: settings["lucky_spin_min_reward"] = 1.0
if "lucky_spin_max_reward" not in settings: settings["lucky_spin_max_reward"] = 5.0
# Play & Earn rewards are independently configurable from the Admin Panel.
settings.setdefault("tt_min_reward", 0.01)
settings.setdefault("tt_max_reward", 0.75)
settings.setdefault("rps_min_reward", 0.01)
settings.setdefault("rps_max_reward", 0.75)
settings.setdefault("tt_enabled", True)
settings.setdefault("rps_enabled", True)
settings.setdefault("tt_cooldown_hours", 24)
settings.setdefault("rps_cooldown_hours", 24)
# Daily Task settings: number of completed games, daily rewarded-user cap, and reward amount.
settings.setdefault("daily_task_games", 2)
settings.setdefault("daily_task_max_users", 100)
settings.setdefault("daily_task_reward", 1.0)
settings.setdefault("daily_task_enabled", True)
save_json("settings.json", settings)

categories = load_json("categories.json")
if not categories:
    categories = DEFAULT_CATEGORIES.copy()
    save_json("categories.json", categories)

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

async def get_bot_username(bot):
    """Return the current bot username without the @ prefix."""
    try:
        me = await bot.get_me()
        return (me.username or "").strip().lstrip("@")
    except Exception:
        link = str(load_json("settings.json").get("shop_bot_link", ""))
        if "t.me/" in link:
            return link.split("t.me/", 1)[1].split("?", 1)[0].strip("/")
        return ""

def product_deep_link(bot_username, pid):
    """Telegram deep link for a product."""
    if not bot_username:
        return ""
    return f"https://t.me/{bot_username}?start=product_{pid}"

def plan_deep_link(bot_username, pid, plan_index):
    """Telegram deep link for a specific product plan."""
    if not bot_username:
        return ""
    return f"https://t.me/{bot_username}?start=plan_{pid}_{plan_index}"

# Telegram button styles:
#   danger  = red
#   success = green
#   primary = blue
#   omitted = transparent/default
BUTTON_STYLES = {
    "shop": "danger",       # 🛒 Shop/Buy Products — Red
    "orders": "success",    # 📦 My Orders — Green
    "profile": "primary",   # 👤 Profile — Blue
    "addbal": "success",
    "claim_coupon": "success",
    "lucky_spin": "primary",    # 💰 Add Balance — Green
    "referral": "primary",
    "mykeys": "success",
    "proof": "success",     # 📜 Payment Proof — Green
    # "support" intentionally omitted -> transparent
}

GREEN_CATEGORY_NAMES = {
    "non-root mobile",
    "root mobile",
    "pc / computer",
    "ios / iphone",
}

def _button_style(text, data):
    if data in BUTTON_STYLES:
        return BUTTON_STYLES[data]

    # Admin panel button colours: action-based styling.
    ADMIN_BUTTON_STYLES = {
        "bot_status_info": "primary",
        "bot_toggle": "danger",
        "search_order": "primary",
        "products_toggle": "primary",
        "addcat": "success",
        "addprod": "success",
        "addplan": "success",
        "addplankeys": "success",
        "editplan": "primary",
        "delplan": "danger",
        "editprod": "primary",
        "delprod": "danger",
        "product_links": "primary",
        "broadcast": "primary",
        "userlist": "primary",
        "create_coupon": "success",
        "lucky_spin_settings": "primary",
        "adduserbal": "success",
        "setproof": "success",
        "sethowto": "primary",
        "setsupport": "success",
        "setdownload": "primary",
        "set_order_channel": "primary",
        "reseller_settings": "primary",
        "reseller_add_plan": "success",
        "reseller_edit_plan": "primary",
        "reseller_delete_plan": "danger",
        "reseller_add_user": "success",
        "reseller_remove_user": "danger",
        "reseller_list": "primary",
        "upgrade_reseller": "primary",
    }
    if data in ADMIN_BUTTON_STYLES:
        # Bot ON/OFF gets the colour matching the action.
        if data == "bot_toggle":
            normalized_toggle = " ".join(str(text).lower().split())
            return "danger" if "off" in normalized_toggle else "success"
        return ADMIN_BUTTON_STYLES[data]

    normalized = " ".join(str(text).lower().split())
    if normalized in GREEN_CATEGORY_NAMES:
        return "primary"

    # All Back-style buttons should be red/danger.
    if (
        str(data).lower().startswith("Back")
        or "back" in normalized
    ):
        return "danger"

    # Support is intentionally transparent.
    if data == "support" or normalized == "support" or "support" in normalized:
        return None

    return None

def btn(rows):
    keyboard = []
    for row in rows:
        buttons = []
        for item in row:
            text, data = item[:2]
            style = item[2] if len(item) >= 3 else _button_style(text, data)
            kwargs = {"text": text, "callback_data": data}
            if style is not None:
                kwargs["style"] = style
            buttons.append(InlineKeyboardButton(**kwargs))
        keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard)



START_MENU_BUTTON_DEFAULTS = {
    "shop": ("🛒 Shop/Buy Products", "primary"), "orders": ("📦 My Orders", "primary"),
    "profile": ("👤 Profile", "primary"), "addbal": ("💰 Add Balance", "primary"),
    "coupon": ("🎟️ Claim Coupon Code", "primary"), "lucky_spin": ("🎡 Lucky Spin", "primary"),
    "referral": ("🔵 Refer & Earn", "primary"), "mykeys": ("🔑 My Keys", "primary"),
    "play_earn": ("🚀 Play And Earn", "success"), "daily_task": ("🎯 Daily Task", "primary"),
    "proof": ("📜 Payment Proof", "success"), "howto": ("📖 How to Use", "primary"),
    "support": ("💬 Support", "success"), "upgrade_reseller": ("💎 Upgrade to Reseller", "primary"),
    "reseller": ("Access Reseller", "success"), "download": ("📥 Download Files", "primary"),
}
def start_menu_button(key, callback_data=None, url=None):
    cfg = load_json("settings.json").get("start_menu_buttons", {})
    default_text, default_style = START_MENU_BUTTON_DEFAULTS[key]
    item = cfg.get(key, {}) if isinstance(cfg, dict) else {}
    style = str(item.get("style") or default_style).lower()
    if style not in ("primary", "success", "danger"): style = default_style
    kwargs = {"text": str(item.get("text") or default_text), "style": style}
    if url: kwargs["url"] = url
    else: kwargs["callback_data"] = callback_data
    return InlineKeyboardButton(**kwargs)

async def start_menu_buttons_admin(bot, chat_id, message_id):
    rows = []
    cfg = load_json("settings.json").get("start_menu_buttons", {})
    for key, (label, _) in START_MENU_BUTTON_DEFAULTS.items():
        rows.append([(str(cfg.get(key, {}).get("text") or label)[:35], f"smb_edit:{key}")])
    rows.append([("🔙 Back", "backadmin")])
    await edit_msg(bot, chat_id, message_id, "<b>START MENU BUTTON SETTINGS</b>\n\nSelect a button to edit its name or style.", btn(rows))

async def start_menu_button_editor(bot, chat_id, message_id, key):
    if key not in START_MENU_BUTTON_DEFAULTS: return
    cfg = load_json("settings.json").get("start_menu_buttons", {}).get(key, {})
    label, default_style = START_MENU_BUTTON_DEFAULTS[key]
    name = cfg.get("text") or label
    style = cfg.get("style") or default_style
    rows = [[("✏️ Change Button Name", f"smb_name:{key}")],
            [("Primary", f"smb_style:{key}:primary"), ("Success", f"smb_style:{key}:success")],
            [("Danger", f"smb_style:{key}:danger")],
            [("🔙 Back", "start_menu_buttons_admin")]]
    await edit_msg(bot, chat_id, message_id,
        f"<b>EDIT START MENU BUTTON</b>\n\n<b>Name:</b> {html.escape(name)}\n<b>Style:</b> {html.escape(str(style).title())}", btn(rows))

def normalize_duration(value):
    """Keep exactly the unit the admin enters (e.g. 1 hour, 5 hours, 1 day, 30 days)."""
    value = str(value).strip()
    if not value:
        raise ValueError("Duration cannot be empty")
    return value

def duration_text(plan):
    # New plans use 'duration'. Old plans using 'days' continue to work.
    return str(plan.get("duration") or plan.get("days") or "").strip()

def normalize_message_newlines(text):
    """Convert escaped newline sequences to real line breaks before sending."""
    if isinstance(text, str):
        return text.replace("\\n", "\n")
    return text

async def send_message(bot, chat_id, text, reply_markup=None):
    text = normalize_message_newlines(text)
    return await bot.send_message(
        chat_id=chat_id, text=text, parse_mode="HTML",
        disable_web_page_preview=True, reply_markup=reply_markup
    )

async def edit_msg(bot, chat_id, message_id, text, reply_markup=None):
    text = normalize_message_newlines(text)
    if not message_id:
        return await send_message(bot, chat_id, text, reply_markup)
    try:
        return await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text,
            parse_mode="HTML", disable_web_page_preview=True,
            reply_markup=reply_markup
        )
    except Exception:
        # Profile screens may be sent as photos with captions. Telegram cannot
        # edit a photo message using edit_message_text, so update its caption.
        try:
            return await bot.edit_message_caption(
                chat_id=chat_id, message_id=message_id, caption=text,
                parse_mode="HTML", reply_markup=reply_markup
            )
        except Exception:
            # If the new content is too long for a caption (or the old message
            # is not editable), replace it with a normal text message so that
            # the next screen and its inline buttons remain usable.
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass
            try:
                return await send_message(bot, chat_id, text, reply_markup)
            except Exception:
                return None

async def delete_msg(bot, chat_id, message_id):
    try:
        return await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        return None

def save_balance(user_id, balance):
    balances = load_json("balances.json")
    balances[str(user_id)] = balance
    save_json("balances.json", balances)

def save_temp(user_id, key, value):
    temp = load_json("temp.json")
    uid = str(user_id)
    temp.setdefault(uid, {})[key] = value
    save_json("temp.json", temp)

def get_temp(user_id):
    return load_json("temp.json").get(str(user_id), {})


async def reward_referrer(bot, user_id, reward_type):
    """Reward the referrer once for a specific milestone."""
    users = load_json("users.json")
    uid = str(user_id)
    user = users.get(uid, {})
    referrer = str(user.get("referrer", "")).strip()
    if not referrer or referrer == uid or referrer not in users:
        return
    rewards = user.setdefault("referral_rewards", {})
    if rewards.get(reward_type):
        return
    balances = load_json("balances.json")
    balances[referrer] = round(float(balances.get(referrer, 0) or 0) + 2.0, 2)
    save_json("balances.json", balances)
    rewards[reward_type] = True
    user["referral_rewards"] = rewards
    save_json("users.json", users)

    ref_user = users.get(referrer, {})
    ref_user.setdefault("referrals", [])
    if uid not in ref_user["referrals"]:
        ref_user["referrals"].append(uid)
    ref_user["referral_earned"] = round(float(ref_user.get("referral_earned", 0) or 0) + 2.0, 2)
    users[referrer] = ref_user
    save_json("users.json", users)

    try:
        await send_message(
            bot, int(referrer),
            f"🎉 <b>Referral Reward!</b>\n\n"
            f"Your friend completed a referral milestone.\n"
            f"💰 <b>₹2.00 added to your balance.</b>"
        )
    except Exception:
        pass


async def send_referral(bot, chat_id, message_id, user_id):
    users = load_json("users.json")
    u = users.get(str(user_id), {})
    referrals = u.get("referrals", []) or []
    earned = float(u.get("referral_earned", 0) or 0)
    try:
        me = await bot.get_me()
        bot_username = me.username or ""
    except Exception:
        bot_username = ""
    link = f"https://t.me/{bot_username}?start=ref_{user_id}" if bot_username else ""
    share_text = "Join this bot and start earning rewards!"
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_text)}" if link else ""

    msg = (
        "<blockquote><b>Refer &amp; Earn\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Invite Your Friends Using The Link Below And Earn For Free!\n\n"
        "➕ You Will Get:\n"
        "• ₹2.00 — When You Invited A Friend\n"
        "• ₹2.00 — When A Friend Adds Balance For The First Time\n"
        "• ₹2.00 — When A Friend Makes A Purchase For The First Time\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Total Referrals: {len(referrals)}\n"
        f"💰 Total Earned: ₹{earned:.2f}\n\n"
        f"🔗 Your Referral Link: <code>{html.escape(link)}</code></b></blockquote>"
    )
    rows = []
    if share_url:
        rows.append([InlineKeyboardButton("📤 Share Link", url=share_url, style="primary")])
    rows.append([InlineKeyboardButton("Back To Menu", callback_data="back", style="danger")])
    await edit_msg(bot, chat_id, message_id, msg, InlineKeyboardMarkup(rows))


async def send_my_keys(bot, chat_id, message_id, user_id):
    orders = load_json("orders.json")
    mine = [o for o in orders.values() if str(o.get("user")) == str(user_id) and o.get("key")]
    if not mine:
        msg = "🔑 <b>My Keys</b>\n\nYou haven't purchased any keys yet."
        await edit_msg(bot, chat_id, message_id, msg, btn([[("Back To Menu", "back")]]))
        return
    msg = "🔑 <b>MY KEYS</b>\n\n"
    rows = []
    for i, o in enumerate(reversed(mine), 1):
        key = str(o.get("key", ""))
        msg += (
            f"{i}. <b>{html.escape(str(o.get('product_name','Product')))}</b>\n"
            f"📅 {html.escape(str(o.get('duration') or o.get('days') or ''))}\n"
            f"🔑 <code>{html.escape(key)}</code>\n\n"
        )
        rows.append([InlineKeyboardButton("📋 Copy Key", copy_text=CopyTextButton(text=key))])
    rows.append([InlineKeyboardButton("Back To Menu", callback_data="back", style="danger")])
    await edit_msg(bot, chat_id, message_id, msg, InlineKeyboardMarkup(rows))


# ============================================================
# USER MENUS
# ============================================================
async def send_main_menu(bot, chat_id, name, balance, message_id=0, telegram_user=None):
    settings_now = load_json("settings.json")
    custom_template = settings_now.get("start_menu_template")
    start_media = settings_now.get("start_menu_media") if custom_template is not None else None
    if custom_template is not None:
        tg_user = telegram_user
        first_name = getattr(tg_user, "first_name", None) or str(name or "")
        second_name = getattr(tg_user, "last_name", None) or ""
        username = getattr(tg_user, "username", None) or ""
        user_id_value = getattr(tg_user, "id", None) or chat_id
        replacements = {
            "[FIRST_NAME]": html.escape(str(first_name)),
            "[SECOND_NAME]": html.escape(str(second_name)),
            "[USERNAME]": html.escape(str(username)),
            "[BALANCE]": html.escape(f"{float(balance or 0):.2f}"),
            "[USER_ID]": f"<code>{html.escape(str(user_id_value))}</code>",
        }
        msg = str(custom_template)
        # HTML generated from Telegram entities is saved as HTML, preserving all
        # supported formatting (bold, italic, underline, strike, quote, links, etc.).
        for token, value in replacements.items():
            msg = msg.replace(token, value)
        if isinstance(start_media, dict):
            start_caption = str(start_media.get("caption") or "")
            for token, value in replacements.items():
                start_caption = start_caption.replace(token, value)
            start_media = dict(start_media)
            start_media["caption"] = start_caption
    else:
        msg = (
    "🛒 ───── <b>TURBO PANEL STORE</b> ───── 🛒\n\n"

    f"<blockquote>🧡 Yo — ꨄ <b>{html.escape(str(name))}</b>, Welcome Back!!</blockquote>\n\n"

    "<blockquote><b>"
    "🔥 ── WHY CHOOSING US ── 🔥\n\n"
    "🔑 Genuine Premium Keys\n"
    "⚡ Instant Auto Delivery\n"
    "🛡️ Secure UPI Payments\n"
    "💎 Unbeatable Prices\n"
    "👊 Real 24/7 Support"
    "</b></blockquote>\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━\n"

    f"<blockquote><b>💲 Your Balance: ₹{balance:.2f}</b></blockquote>\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    "🛒 <b>Shop / Buy Products</b> — Explore Premium Products\n"
    "📦 <b>My Orders</b> — View Your Purchase History\n"
    "👤 <b>Profile</b> — Check Your Account Details\n"
    "💰 <b>Add Balance</b> — Recharge Your Wallet\n"
    "📜 <b>Payment Proof</b> — View Payment Information\n"
    "🎟️ <b>Claim Coupon Code</b> — Redeem Exclusive Offers\n"
    "🎁 <b>Lucky Spin</b> — Try Your Luck &amp; Win Rewards\n"
    "🔵 <b>Refer &amp; Earn</b> — Invite Friends &amp; Earn Rewards\n"
    "🔑 <b>My Keys</b> — Access Your Purchased Keys\n"
    "🚀 <b>Play And Earn</b> — Play &amp; Earn Rewards\n"
    "🎯 <b>Daily Task</b> — Complete Tasks &amp; Get Rewards\n"
    "📖 <b>How to Use</b> — Learn How to Use Our Bot\n"
    "💬 <b>Support</b> — Get Help Anytime\n"
    "💎 <b>Upgrade to Reseller</b> — Become a Reseller\n"
    "🔐 <b>Reseller Login</b> — Access Your Reseller Account\n"
    "📥 <b>Download Files</b> — Download Your Purchased Files\n\n"

    "🛍️ ━━━━ <b>Tap Shop To Start Now!</b> ━━━━ 🛍️"
)
    # Payment Proof is a direct URL button. The URL is controlled from the Admin Panel.
    proof_link = str(settings_now.get("proof_link", "")).strip()
    if proof_link:
        proof_button = start_menu_button("proof", url=proof_link)
    else:
        proof_button = start_menu_button("proof", callback_data="proof")
    kb = InlineKeyboardMarkup([
        [start_menu_button("shop", callback_data="shop")],
        [start_menu_button("orders", callback_data="orders"), start_menu_button("profile", callback_data="profile")],
        [start_menu_button("addbal", callback_data="addbal")],
        [start_menu_button("coupon", callback_data="claim_coupon"), start_menu_button("lucky_spin", callback_data="lucky_spin")],
        [start_menu_button("referral", callback_data="referral"), start_menu_button("mykeys", callback_data="mykeys")],
    ])
    # Show Play And Earn and Daily Task side-by-side in the same row.
    # Daily Task progress/rewards are only activated after the user accepts it.
    game_rows = [list(row) for row in kb.inline_keyboard]
    game_rows.append([
        start_menu_button("play_earn", callback_data="play_earn_menu"),
        start_menu_button("daily_task", callback_data="daily_task"),
    ])
    kb = InlineKeyboardMarkup(game_rows)
    # Keep Payment Proof beside Add Balance in the same row.
    # python-telegram-bot exposes keyboard rows as tuples, so make the
    # rows mutable before appending the direct URL button.
    keyboard_rows = [list(row) for row in kb.inline_keyboard]
    if len(keyboard_rows) > 2:
        keyboard_rows[2].append(proof_button)
    else:
        keyboard_rows.append([proof_button])
    kb = InlineKeyboardMarkup(keyboard_rows)

    # How To Use remains a direct link, but Support opens the in-bot ticket menu.
    howto_link = str(settings_now.get("howto_link", "")).strip()
    link_row = []
    if howto_link:
        link_row.append(start_menu_button("howto", url=howto_link))
    link_row.append(start_menu_button("support", callback_data="support"))
    keyboard_rows = list(kb.inline_keyboard)
    keyboard_rows.append(link_row)
    kb = InlineKeyboardMarkup(keyboard_rows)

    # Access Reseller is always visible and opens the separate Reseller Panel bot.
    keyboard_rows = list(kb.inline_keyboard)
    keyboard_rows.append([
        start_menu_button("upgrade_reseller", callback_data="upgrade_reseller"),
        start_menu_button("reseller", url=RESELLER_BOT_LINK),
    ])
    kb = InlineKeyboardMarkup(keyboard_rows)

    download_link = settings_now.get("download_link", "").strip()
    if download_link:
        # python-telegram-bot may expose inline_keyboard as a tuple, so
        # rebuild the markup instead of calling .append() on it.
        keyboard_rows = list(kb.inline_keyboard)
        keyboard_rows.append([start_menu_button("download", url=download_link)])
        kb = InlineKeyboardMarkup(keyboard_rows)
    if isinstance(start_media, dict) and start_media.get("file_id"):
        # A media-based Start Menu keeps its original media and caption entities.
        # Replace an existing text menu when the user returns via the Back button.
        if message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass
        media_type = start_media.get("type")
        media_file_id = start_media["file_id"]
        caption = start_media.get("caption") or None
        if media_type == "photo":
            await bot.send_photo(chat_id=chat_id, photo=media_file_id, caption=caption, parse_mode="HTML", reply_markup=kb)
        elif media_type == "video":
            await bot.send_video(chat_id=chat_id, video=media_file_id, caption=caption, parse_mode="HTML", reply_markup=kb)
        elif media_type == "animation":
            await bot.send_animation(chat_id=chat_id, animation=media_file_id, caption=caption, parse_mode="HTML", reply_markup=kb)
        else:
            await send_message(bot, chat_id, msg, kb)
    elif message_id:
        await edit_msg(bot, chat_id, message_id, msg, kb)
    else:
        await send_message(bot, chat_id, msg, kb)
async def send_categories(bot, chat_id, message_id, name="User"):
    categories = load_json("categories.json")
    rows = [[(c["name"], f"cat_{cid}", c.get("style", _button_style(c.get("name", ""), f"cat_{cid}")))] for cid, c in categories.items()]
    rows.append([("Back", "back")])

    await edit_msg(
        bot, chat_id, message_id,
        (
            '<blockquote><b>🛒 SELECT YOUR DEVICE TYPE ✨</b></blockquote>\n'
            '<b>━━━━━━━━━━━━━━━━━━━━━</b>\n\n'
            f'<b>👋 Yoo {html.escape(name)}!</b>\n'
            '<blockquote><i><b>First, select your device type; then, the products will appear.</b></i></blockquote>\n'
            '<b>━━━━━━━━━━━━━━━━━━━━━</b>'
        ),
        btn(rows)
    )

async def send_products(bot, chat_id, message_id, cid, name="User"):
    products = load_json("products.json")
    categories = load_json("categories.json")
    cat_name = categories.get(cid, {}).get("name", "Category")
    safe_name = html.escape(str(name or "User"))
    msg = (
        f"<blockquote><b>🛒 {html.escape(str(cat_name))}</b></blockquote>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>👋 Yoo {safe_name}!</b>\n\n"
        "<blockquote><i><b>✨ Explore our exclusive products below and discover the perfect plan for you! 🚀</b></i></blockquote>\n\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    rows = []
    for pid, product in products.items():
        if product.get("cat") == cid:
            # Show only the product name; do not reveal the number of plans.
            # ON = default Primary/blue, OFF = Danger/red.
            product_style = "primary" if product.get("enabled", True) else "danger"
            rows.append([(f"{product.get('name','')}", f"buy_{pid}", product_style)])
    if not rows:
        msg += "\n\n❌ No Products Available In This Category"
    rows.append([("Back", "backcat")])
    await edit_msg(bot, chat_id, message_id, msg, btn(rows))

def _orders_pin_hash(pin, salt_hex=None):
    """Return a salted PBKDF2 hash for a numeric My Orders PIN."""
    salt_hex = salt_hex or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", str(pin).encode("utf-8"), bytes.fromhex(salt_hex), 160000).hex()
    return salt_hex, digest


def _orders_pin_matches(pin, salt_hex, expected_hash):
    try:
        _, actual = _orders_pin_hash(pin, salt_hex)
        return hmac.compare_digest(actual, str(expected_hash))
    except (ValueError, TypeError):
        return False


def _orders_pin_state(user_id, mode=None, digits=None, **extra):
    temp_all = load_json("temp.json")
    uid = str(user_id)
    temp = temp_all.setdefault(uid, {})
    if mode is not None:
        temp["waiting"] = "orders_pin"
        temp["orders_pin_mode"] = mode
    # In-progress PIN digits are intentionally kept in memory only, not in JSON files.
    temp.pop("orders_pin_digits", None)
    for key, value in extra.items():
        if value is None:
            temp.pop(key, None)
        else:
            temp[key] = value
    temp_all[uid] = temp
    save_json("temp.json", temp_all)
    return temp


def _clear_orders_pin_state(user_id):
    temp_all = load_json("temp.json")
    uid = str(user_id)
    temp = temp_all.get(uid, {})
    for key in ("orders_pin_mode", "orders_pin_digits", "orders_pin_pending_salt", "orders_pin_pending_hash", "orders_pin_target"):
        temp.pop(key, None)
    if temp.get("waiting") == "orders_pin":
        temp["waiting"] = ""
    temp_all[uid] = temp
    save_json("temp.json", temp_all)


def _otp_keyboard(digits):
    """Blue numeric OTP keypad, red edit/cancel keys, green verify."""
    rows = [
        [InlineKeyboardButton("1", callback_data="orders_pin_otp_digit_1", style="primary"), InlineKeyboardButton("2", callback_data="orders_pin_otp_digit_2", style="primary"), InlineKeyboardButton("3", callback_data="orders_pin_otp_digit_3", style="primary")],
        [InlineKeyboardButton("4", callback_data="orders_pin_otp_digit_4", style="primary"), InlineKeyboardButton("5", callback_data="orders_pin_otp_digit_5", style="primary"), InlineKeyboardButton("6", callback_data="orders_pin_otp_digit_6", style="primary")],
        [InlineKeyboardButton("7", callback_data="orders_pin_otp_digit_7", style="primary"), InlineKeyboardButton("8", callback_data="orders_pin_otp_digit_8", style="primary"), InlineKeyboardButton("9", callback_data="orders_pin_otp_digit_9", style="primary")],
        [InlineKeyboardButton("⌫ Delete", callback_data="orders_pin_otp_del", style="danger"), InlineKeyboardButton("0", callback_data="orders_pin_otp_digit_0", style="primary"), InlineKeyboardButton("🧹 Clear", callback_data="orders_pin_otp_clear", style="danger")],
        [InlineKeyboardButton("✅ Confirm", callback_data="orders_pin_otp_verify", style="success")],
        [InlineKeyboardButton("❌Cancel", callback_data="orders_pin_otp_cancel", style="danger")],
    ]
    return InlineKeyboardMarkup(rows)


def _orders_pin_keyboard(user_id, digits, mode):
    # Numeric keys are blue, delete/clear/cancel are red, submit is green.
    rows = [
        [InlineKeyboardButton("1", callback_data="orders_pin_digit_1", style="primary"), InlineKeyboardButton("2", callback_data="orders_pin_digit_2", style="primary"), InlineKeyboardButton("3", callback_data="orders_pin_digit_3", style="primary")],
        [InlineKeyboardButton("4", callback_data="orders_pin_digit_4", style="primary"), InlineKeyboardButton("5", callback_data="orders_pin_digit_5", style="primary"), InlineKeyboardButton("6", callback_data="orders_pin_digit_6", style="primary")],
        [InlineKeyboardButton("7", callback_data="orders_pin_digit_7", style="primary"), InlineKeyboardButton("8", callback_data="orders_pin_digit_8", style="primary"), InlineKeyboardButton("9", callback_data="orders_pin_digit_9", style="primary")],
        [InlineKeyboardButton("⌫ Delete", callback_data="orders_pin_del", style="danger"), InlineKeyboardButton("0", callback_data="orders_pin_digit_0", style="primary"), InlineKeyboardButton("🧹 Clear", callback_data="orders_pin_clear", style="danger")],
        [InlineKeyboardButton("✅ Confirm", callback_data="orders_pin_submit", style="success")],
        [InlineKeyboardButton("❌Cancel", callback_data="orders_pin_cancel", style="danger")],
    ]
    if mode == "login":
        rows.append([InlineKeyboardButton("🔑 Forgot Password?", callback_data="orders_pin_forgot", style="primary")])
    shown = "•" * len(str(digits)) if digits else "—"
    return shown, InlineKeyboardMarkup(rows)


async def _show_orders_pin(bot, chat_id, message_id, user_id, mode, user_data, notice=""):
    _orders_pin_state(user_id, mode=mode, digits="")
    user_data["orders_pin_digits"] = ""
    labels = {
        "setup": "🔐 <b>Set Profile & Orders Password</b>\n\nCreate a numeric PIN with 4–12 digits.",
        "confirm": "🔐 <b>Confirm Your Password</b>\n\nEnter the same 4–12 digit PIN again.",
        "login": "🔒 <b>Profile & Orders — Password Required</b>\n\nEnter your numeric PIN to continue.",
    }
    _, keyboard = _orders_pin_keyboard(user_id, "", mode)
    text = (notice + "\n\n" if notice else "") + labels.get(mode, labels["login"]) + "\n\n🔢 <b>PIN:</b> <code>—</code>"
    await edit_msg(bot, chat_id, message_id, text, keyboard)


async def _send_protected_area(bot, chat_id, message_id, user_id, target, user_data=None):
    """Require the shared numeric PIN before opening Profile or My Orders."""
    users = load_json("users.json")
    user = users.get(str(user_id), {})
    user_data = user_data if user_data is not None else {}
    # OTP verification remains valid until the user completes password setup.
    # There is deliberately no timeout for this pending reset state.
    temp_all = load_json("temp.json")
    session = temp_all.get(str(user_id), {})
    if session.get("waiting") == "orders_pin_reset_ready":
        account = users.setdefault(str(user_id), {})
        account.pop("orders_pin_hash", None)
        account.pop("orders_pin_salt", None)
        users[str(user_id)] = account
        save_json("users.json", users)
        session.pop("orders_pin_reset_ready_expires", None)  # clean up legacy data
        session["waiting"] = ""
        temp_all[str(user_id)] = session
        save_json("temp.json", temp_all)
        _clear_orders_pin_state(user_id)
        user_data.pop("orders_pin_digits", None)
        _orders_pin_state(user_id, mode="setup", orders_pin_target=target)
        await _show_orders_pin(
            bot, chat_id, message_id, user_id, "setup", user_data,
            "✅ <b>OTP verified earlier.</b> Please set your new password to continue."
        )
        return

    # Keep Profile and My Orders unlocked for one hour after a successful PIN entry.
    try:
        unlocked_until = float(session.get("orders_pin_unlocked_until", 0))
    except (TypeError, ValueError):
        unlocked_until = 0
    if time.time() < unlocked_until:
        if target == "profile":
            await send_profile(bot, chat_id, message_id, user_id)
        else:
            await _render_orders_after_pin(bot, chat_id, message_id, user_id)
        return
    if not user.get("orders_pin_hash") or not user.get("orders_pin_salt"):
        _orders_pin_state(user_id, orders_pin_target=target)
        msg = (
            "🔐 <b>Profile & My Orders are Locked</b>\n\n"
            "Set a numeric password first. After setup, the same password will protect both Profile and My Orders."
        )
        await edit_msg(bot, chat_id, message_id, msg, btn([
            [("🔐 Set Password", "orders_pin_set", "success")],
            [("Back To Menu", "back", "danger")],
        ]))
        return
    _orders_pin_state(user_id, orders_pin_target=target)
    await _show_orders_pin(bot, chat_id, message_id, user_id, "login", user_data)


async def send_orders(bot, chat_id, message_id, user_id, user_data=None):
    await _send_protected_area(bot, chat_id, message_id, user_id, "orders", user_data)


async def send_profile_protected(bot, chat_id, message_id, user_id, user_data=None):
    await _send_protected_area(bot, chat_id, message_id, user_id, "profile", user_data)


async def _render_orders_after_pin(bot, chat_id, message_id, user_id):
    orders = load_json("orders.json")
    mine = [(oid, o) for oid, o in orders.items() if str(o.get("user")) == str(user_id)]
    if not mine:
        msg = "📄 <b>MY ORDERS</b>\n\nYou haven't made any purchases yet."
    else:
        msg = "📦 <b>MY ORDERS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        for i, (oid, o) in enumerate(reversed(mine), 1):
            msg += (
                f"{i}. <b>{html.escape(str(o.get('product_name','')))}</b>\n"
                f" 📅 Plan: {html.escape(str(o.get('duration') or o.get('days') or ''))}\n"
                f" 💰 Price: ₹{o.get('price')}\n"
                f" 📅 Date: {html.escape(str(o.get('date') or ''))}\n"
                f" 🆔 Order: <code>{html.escape(str(oid))}</code>\n"
                f" 🔑 Key: <code>{html.escape(str(o.get('key','')))}</code>\n"
                f" Status: ✅ {html.escape(str(o.get('status') or ''))}\n\n"
            )
    await edit_msg(bot, chat_id, message_id, msg, btn([[ ("Back To Menu", "back", "danger") ]]))


async def send_profile(bot, chat_id, message_id, user_id):
    balances = load_json("balances.json")
    users = load_json("users.json")
    orders = load_json("orders.json")
    u = users.get(str(user_id), {})

    # Calculate profile statistics from delivered orders.
    delivered_orders = [
        o for o in orders.values()
        if str(o.get("user")) == str(user_id) and o.get("status") == "Delivered"
    ]
    keys_count = len(delivered_orders)
    spent = 0.0
    for o in delivered_orders:
        try:
            spent += float(o.get("price", 0) or 0)
        except (TypeError, ValueError):
            pass

    name = str(u.get("name") or "User")
    username = str(u.get("username") or "").strip()

    # Prefer the current Telegram account details when available.
    try:
        telegram_user = await bot.get_chat(user_id)
        if getattr(telegram_user, "first_name", None):
            name = str(telegram_user.first_name)
        if getattr(telegram_user, "username", None):
            username = str(telegram_user.username)
    except Exception:
        pass

    if username and not username.startswith("@"):
        username = "@" + username
    if not username:
        username = "Not Set"

    # Requested profile layout — every line is bold.
    msg = (
        "<b>👤 USER PROFILE 👤</b>\n\n"
        f"<b>🆔 ID: {html.escape(str(user_id))}</b>\n"
        f"<b>Name: {html.escape(name)}</b>\n"
        f"<b>Username: {html.escape(username)}</b>\n"
        "<b>🙋 Account Type: 👤 Regular</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>💰 Balance: ₹{float(balances.get(str(user_id), 0) or 0):.2f}</b>\n"
        f"<b>📊 Spent: ₹{spent:.2f}</b>\n"
        f"<b>🔑 Keys: {keys_count}</b>"
    )

    keyboard = btn([
        [("🛒 Shop/Buy Products", "shop"), ("📦 My Orders", "orders")],
        [("Back To Menu", "back")]
    ])

    # Fetch the user's current Telegram profile photo directly from Telegram.
    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
        if photos.total_count > 0 and photos.photos and photos.photos[0]:
            photo_file_id = photos.photos[0][-1].file_id

            # Remove the old menu message and replace it with the profile photo + caption.
            if message_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception:
                    pass

            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_file_id,
                caption=msg,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return
    except Exception:
        # If Telegram photo fetching fails, fall back to the text profile.
        pass

    await edit_msg(bot, chat_id, message_id, msg, keyboard)


async def send_proof(bot, chat_id, message_id):
    s = load_json("settings.json")
    link = str(s.get("proof_link", "")).strip()
    if not link:
        await edit_msg(bot, chat_id, message_id, "📄 <b>Payment Proof</b>\n\nPayment proof link is not configured yet.", btn([[('Back To Menu','back')]]))
        return
    # Directly open the configured proof link.
    await edit_msg(bot, chat_id, message_id, f"<a href='{html.escape(link, quote=True)}'>Payment Proof</a>", None)

async def send_howto(bot, chat_id, message_id):
    s = load_json("settings.json")
    link = s.get("howto_link", "")
    msg = f"📖 <b>How to Use</b>\n\n1. Add Balance\n2. Shop Now\n3. Key Instant Milega\nVideo Tutorial:\n🔗 <a href='{html.escape(link, quote=True)}'>Watch Now</a>"
    await edit_msg(bot, chat_id, message_id, msg, btn([[("Back To Menu","back")]]))

async def send_support(bot, chat_id, message_id):
    # Support opens directly to the two requested ticket actions only.
    msg = "💬 <b>SUPPORT CENTER</b>\n\nChoose an option below."
    await edit_msg(bot, chat_id, message_id, msg, btn([
        [("🆕 Open New Ticket", "ticket_new", "success")],
        [("📋 My Tickets", "ticket_mine", "primary")],
        [("Back", "back", "danger")],
    ]))

async def show_tickets_menu(bot, chat_id, message_id):
    # Keep older callback references working, but use the same two-button menu.
    await send_support(bot, chat_id, message_id)

def tickets_created_today(user_id):
    """Count this user's tickets for the current India calendar day (midnight reset)."""
    today = now_ist().date()
    tickets = load_json("tickets.json")
    count = 0
    for ticket in tickets.values():
        if str(ticket.get("user_id")) != str(user_id):
            continue
        created = ticket.get("created", 0)
        try:
            created_day = datetime.fromtimestamp(float(created), IST).date()
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        if created_day == today:
            count += 1
    return count

async def open_new_ticket(bot, chat_id, user_id):
    settings = load_json("settings.json")
    limit = max(0, int(settings.get("ticket_daily_limit", 5)))
    used = tickets_created_today(user_id)
    if used >= limit:
        await send_message(bot, chat_id,
            f"⛔ <b>Daily Ticket Limit Reached</b>\n\nYou have used <b>{used}/{limit}</b> tickets for today. You can open a new ticket tomorrow after 12:00 AM (India time).",
            btn([[ ("📋 My Tickets", "ticket_mine", "primary")], [("Back", "tickets_menu", "danger")]]))
        return
    save_temp(user_id, "waiting", "ticket_issue")
    await send_message(bot, chat_id,
        "📝 <b>OPEN NEW TICKET</b>\n\nPlease send your issue in one message. It will be sent to the admin team.",
        btn([[ ("❌Cancel", "ticket_cancel", "danger") ]]))

async def show_my_tickets(bot, chat_id, user_id):
    tickets = load_json("tickets.json")
    mine = [(tid, t) for tid, t in tickets.items() if str(t.get("user_id")) == str(user_id)]
    mine.sort(key=lambda pair: pair[1].get("created", 0), reverse=True)
    if not mine:
        await send_message(bot, chat_id, "📋 <b>MY TICKETS</b>\n\nYou have not opened any tickets yet.",
            btn([[ ("🆕 Open New Ticket", "ticket_new", "success")], [("Back", "tickets_menu", "danger")]]))
        return
    lines = ["📋 <b>MY TICKETS</b>"]
    rows = []
    for tid, ticket in mine[:15]:
        status = "🟢 Open" if ticket.get("status", "open") == "open" else "⚪ Closed"
        lines.append(f"\n<b>#{html.escape(tid)}</b> — {status}\n{html.escape(str(ticket.get('issue',''))[:180])}")
        rows.append([(f"🎫 #{tid}", f"ticket_view_{tid}", "primary")])
    rows.append([("🆕 Open New Ticket", "ticket_new", "success")])
    rows.append([("Back", "tickets_menu", "danger")])
    await send_message(bot, chat_id, "\n".join(lines), btn(rows))

async def send_add_balance(bot, chat_id, message_id, user_id):
    # CAPTCHA removed as requested. Open redeem-code instructions directly.
    await show_redeem_code_instructions(bot, chat_id, user_id)

async def show_redeem_code_instructions(bot, chat_id, user_id):
    save_temp(user_id, "waiting", "redeem_code")
    save_temp(user_id, "redeem_code", "")
    msg = (
        "💰 <b>ADD BALANCE — REDEEM CODE</b>\n\n"
        "<b>What is a Redeem Code?</b>\n"
        "A Redeem Code is a code used to add balance to your account. Official Google Play redeem codes and UPI payments are not the same thing. When watching the videos below, use only the official methods available in your app. Avoid suspicious links that ask you to send money or share private information.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📹 <b>How To Generate Redeem Code From Google Pay</b>\n"
        "https://youtu.be/aHVQW2xiw2Y?si=9cIvNcx92fFDPqCO\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📹 <b>How To Generate Redeem Code From PhonePe</b>\n"
        "https://youtu.be/Y4qbaSHluCc?si=2-RvSA_dwsrnq5zX\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📹 <b>How To Generate Redeem Code From Paytm</b>\n"
        "https://youtu.be/UnAkxFRP55w?si=_bhGjeDTx39zpyVq\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote><b>📩 SEND YOUR REDEEM CODE</b></blockquote>"
    )
    await send_message(bot, chat_id, msg, btn([[ ("Back To Menu", "back") ]]))

def reseller_is_active(user_id):
    users = load_json("users.json")
    info = users.get(str(user_id), {}).get("reseller", {})
    if not info or not info.get("active"):
        return False
    until = info.get("active_until")
    if until == "permanent":
        return True
    try:
        if float(until) > time.time():
            return True
    except (TypeError, ValueError):
        pass
    # Expired reseller access is disabled automatically.
    info["active"] = False
    info["panel_logged_in"] = False
    users[str(user_id)]["reseller"] = info
    save_json("users.json", users)
    return False


def reseller_price(user_id, original_price):
    """Active resellers receive the configured percentage discount on every product."""
    if not reseller_is_active(user_id):
        return round(float(original_price), 2)
    s = load_json("settings.json")
    try:
        discount = max(0, min(90, float(s.get("reseller_discount_percent", 50))))
    except (TypeError, ValueError):
        discount = 50
    return round(float(original_price) * (100 - discount) / 100, 2)


def _duration_seconds(value):
    """Convert simple reseller durations like '1 month', '30 days', '12 hours'."""
    text = str(value or "").strip().lower()
    match = re.fullmatch(r"(\d+)\s*(minute|minutes|min|hour|hours|day|days|week|weeks|month|months|year|years)", text)
    if not match:
        raise ValueError("Use a duration such as 1 month, 30 days, or 12 hours.")
    amount = int(match.group(1))
    unit = match.group(2)
    factors = {"minute":60, "minutes":60, "min":60, "hour":3600, "hours":3600, "day":86400, "days":86400, "week":604800, "weeks":604800, "month":2592000, "months":2592000, "year":31536000, "years":31536000}
    if amount < 1 or amount > 3650:
        raise ValueError("Duration must be between 1 and 3650 units.")
    return amount * factors[unit]


def reseller_dialpad_keyboard():
    # Keep dial-pad button labels clean: no color emojis beside the buttons.
    # Telegram clients may ignore native button styles depending on API/client support.
    return btn([
        [("1", "reseller_pad_1", "primary"), ("2", "reseller_pad_2", "primary"), ("3", "reseller_pad_3", "primary")],
        [("4", "reseller_pad_4", "primary"), ("5", "reseller_pad_5", "primary"), ("6", "reseller_pad_6", "primary")],
        [("7", "reseller_pad_7", "primary"), ("8", "reseller_pad_8", "primary"), ("9", "reseller_pad_9", "primary")],
        [("⌫ Delete", "reseller_pad_del", "danger"), ("0", "reseller_pad_0", "primary"), ("🧹 Clear", "reseller_pad_clear", "danger")],
        [("✅ Confirm", "reseller_pad_ok", "success")],
        [("❌Cancel", "reseller_pad_cancel", "danger")]
    ])


async def show_reseller_login(bot, chat_id, message_id, context):
    context.user_data["reseller_login_state"] = {"step": "id", "digits": ""}
    await edit_msg(bot, chat_id, message_id,
        "🔐 <b>Reseller Login</b>\n\nEnter your numeric <b>Reseller ID</b> using the dial pad below.\n\n🔢 <b>Input:</b> <code>—</code>",
        reseller_dialpad_keyboard())


async def show_reseller_settings(bot, chat_id, message_id):
    s = load_json("settings.json")
    plans = s.get("reseller_plans", [])
    active = sum(1 for uid in load_json("users.json") if reseller_is_active(uid))
    discount = s.get("reseller_discount_percent", 50)
    msg = ("💎 <b>Reseller Settings</b>\n\n"
           f"📋 Plans: <b>{len(plans)}</b>\n"
           f"👥 Active Resellers: <b>{active}</b>\n"
           f"🎯 Product Discount: <b>{discount}%</b>\n\n"
           "All reseller controls are managed here.")
    await edit_msg(bot, chat_id, message_id, msg, btn([
        [("➕ Add Reseller Plan", "reseller_add_plan", "success")],
        [("✏️ Edit Plan", "reseller_edit_plan", "primary"), ("🗑️ Delete Plan", "reseller_delete_plan", "danger")],
        [("➕ Add Reseller", "reseller_add_user", "success"), ("➖ Remove Reseller", "reseller_remove_user", "danger")],
        [("📋 Reseller List", "reseller_list", "primary")],
        [("🎯 Set Discount %", "reseller_discount_set", "primary")],
        [("🔄 Reseller System ON/OFF", "reseller_toggle", "danger" if s.get("reseller_enabled", True) else "success")],
        [("Back to Admin", "backadmin", "danger")]
    ]))


async def show_reseller_upgrade(bot, chat_id, message_id, user_id):
    s = load_json("settings.json")
    if not s.get("reseller_enabled", True):
        await edit_msg(bot, chat_id, message_id, "🛠️ <b>Reseller upgrade is currently disabled.</b>", btn([[ ("Back", "back", "danger") ]]))
        return
    plans = s.get("reseller_plans", [])
    if not plans:
        await edit_msg(bot, chat_id, message_id, "💎 <b>Upgrade to Reseller</b>\n\nNo reseller plans are available right now. Please contact the admin.", btn([[ ("Back", "back", "danger") ]]))
        return
    bal = float(load_json("balances.json").get(str(user_id), 0) or 0)
    msg = f"💎 <b>Upgrade to Reseller</b>\n\n💰 Your Balance: <b>₹{bal:.2f}</b>\n🎯 Active resellers get <b>{int(s.get('reseller_discount_percent',50))}% off inside the Reseller Panel only</b>. Regular Shop Bot prices remain unchanged.\n\nChoose a plan:"
    rows = []
    for i, plan in enumerate(plans):
        days = int(plan.get("days", 0) or 0)
        if days <= 0:
            try: days = max(1, int(_duration_seconds(plan.get("name", "30 days")) / 86400))
            except Exception: days = 30
        rows.append([(f"📅 {plan.get('name','Reseller Plan')} ({days} Days) — ₹{float(plan.get('price',0)):.2f}", f"reseller_buy_{i}", "success")])
    rows.append([("Back", "back", "danger")])
    await edit_msg(bot, chat_id, message_id, msg, btn(rows))


async def show_reseller_list(bot, chat_id, message_id):
    users = load_json("users.json")
    rows = []
    lines = ["📋 <b>Reseller List</b>\n"]
    count = 0
    for uid, user in users.items():
        info = user.get("reseller", {}) if isinstance(user, dict) else {}
        if info.get("active") and reseller_is_active(uid):
            count += 1
            name = html.escape(str(user.get("name", "User")))
            username = "@" + str(user.get("username")) if user.get("username") else "No username"
            until = "Permanent" if info.get("active_until") == "permanent" else datetime.fromtimestamp(float(info.get("active_until", 0)), IST).strftime("%d %b %Y %H:%M")
            lines.append(f"{count}. <b>{name}</b>\n🆔 <code>{uid}</code> | {html.escape(username)}\n📅 Expires: {html.escape(until)}\n")
    if count == 0:
        lines.append("No active resellers.")
    await edit_msg(bot, chat_id, message_id, "\n".join(lines), btn([[ ("Back to Reseller Settings", "reseller_settings", "danger") ]]))


async def send_product_plans(bot, chat_id, message_id, pid, user_id=None):
    products = load_json("products.json")
    if pid not in products:
        await edit_msg(bot, chat_id, message_id, "❌ Product nahi mila", btn([[ ("Back", "backcat") ]]))
        return
    p = products[pid]
    plans = p.get("plans", [])
    if not plans:
        await edit_msg(bot, chat_id, message_id, f"❌ <b>{html.escape(str(p.get('name','')))}</b>\n\nIs product ke liye koi plan nahi hai.\nAdmin se contact karo.", btn([[ ("Back to Shop", "backcat") ]]))
        return
    product_name = html.escape(str(p.get("name", "")))
    msg = (
        f"<blockquote><b>👑 PRODUCT: {product_name}</b></blockquote>\n\n"
        "<b>✏️ CHOOSE YOUR PLAN ✏️</b>\n\n"
        "<blockquote><i><b>👀 Select your validity plan below to proceed with the secure order 🛍️</b></i></blockquote>"
    )
    rows=[]
    for original_index, plan in enumerate(plans):
        d=duration_text(plan); keys_count=len(plan.get("keys",[]))
        price = plan.get('price', 0)
        # Shop Bot always displays the standard price. Reseller discounts are
        # only applied when buying from the separate Reseller Panel bot.
        display_price = float(price)
        rows.append([(f"{d} - ₹{display_price:.2f}", f"plan_{pid}_{original_index}", "primary")])
    rows.append([ ("Back to Shop","backcat") ])
    markup=btn(rows)
    video_id=str(p.get("video_file_id") or "").strip()
    if video_id:
        try:
            if message_id: await delete_msg(bot,chat_id,message_id)
            return await bot.send_video(chat_id=chat_id,video=video_id,caption=msg,parse_mode="HTML",reply_markup=markup)
        except Exception:
            pass
    await edit_msg(bot,chat_id,message_id,msg,markup)

async def send_order_to_channel(bot, order_id, product_name, plan, price, channel_id=None):
    """Send the privacy-safe sold-order notification to the configured channel."""
    settings = load_json("settings.json")
    channel_id = str(channel_id or settings.get("order_channel_id", "")).strip()
    if not channel_id:
        raise RuntimeError("Order Channel ID is empty. Set it from Admin Panel.")

    channel_text = (
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "🛒 <b>NEW ORDER PROCESSED</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "👤 <b>Customer:</b> ********\n"
        "🔗 <b>Username:</b> ********\n"
        "🆔 <b>User ID:</b> ********\n"
        f"📦 <b>Product:</b> {html.escape(str(product_name))}\n"
        f"⏱️ <b>Plan:</b> {html.escape(str(duration_text(plan)))}\n"
        f"💰 <b>Price:</b> ₹{price}\n"
        f"🔖 <b>Order ID:</b> <code>{html.escape(str(order_id))}</code>\n"
        "🔑 <b>Delivered Key:</b> ********"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        text="🛒 Start Bot & Buy Products",
        url=str(settings.get("shop_bot_link") or "https://t.me/TurboPaidPanelStoreBot"),
        api_kwargs={"style": "primary"}
    )]])

    # Convert the saved value to an integer so Telegram receives the real channel ID.
    await bot.send_message(
        chat_id=int(channel_id),
        text=channel_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb,
    )


async def notify_admin_new_order(bot, order_id, user_id, product_name, plan, price, key, now):
    # Admin notification stays unchanged and still contains the real customer/key/date.
    try:
        user = await bot.get_chat(user_id)
        username = getattr(user, "username", None)
        display_name = getattr(user, "first_name", None) or "User"
    except Exception:
        username = None
        display_name = "User"
    username_text = f"@{html.escape(username)}" if username else "No username"
    text = (
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "🛒 <b>NEW ORDER PROCESSED</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"👤 <b>Customer:</b> {html.escape(str(display_name))}\n"
        f"🔗 <b>Username:</b> {username_text}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📦 <b>Product:</b> {html.escape(str(product_name))}\n"
        f"⏱️ <b>Plan:</b> {html.escape(str(duration_text(plan)))}\n"
        f"💰 <b>Price:</b> ₹{price}\n"
        f"🔖 <b>Order ID:</b> <code>{html.escape(str(order_id))}</code>\n"
        f"🔑 <b>Delivered Key:</b> <code>{html.escape(str(key))}</code>\n"
        f"🕐 <b>Date:</b> {html.escape(str(now))}"
    )
    await send_message(bot, int(ADMIN_ID), text)

    # Channel notification is deliberately separate: a channel error must NEVER
    # cancel/undo a successful purchase or delivery.
    try:
        await send_order_to_channel(bot, order_id, product_name, plan, price)
    except Exception as e:
        print(f"[ORDER CHANNEL ERROR] {type(e).__name__}: {e}")


async def buy_plan(bot, chat_id, message_id, user_id, pid, plan_index):
    products = load_json("products.json")
    balances = load_json("balances.json")
    orders = load_json("orders.json")
    if pid not in products:
        await edit_msg(bot, chat_id, message_id, "❌ Product nahi mila", btn([[("Back","backcat")]]))
        return
    plans = products[pid].get("plans", [])
    if plan_index < 0 or plan_index >= len(plans):
        await edit_msg(bot, chat_id, message_id, "❌ Plan nahi mila", btn([[("Back","backcat")]]))
        return
    p = products[pid]
    plan = plans[plan_index]
    bal = float(balances.get(str(user_id), 0) or 0)
    original_price = float(plan.get("price", 0))
    # Do not discount purchases made in the regular Shop Bot.
    price = round(original_price, 2)
    if bal < price:
        await edit_msg(
            bot, chat_id, message_id,
            f"❌ <b>Insufficient Balance</b>\n\nPlan: {html.escape(duration_text(plan))}\nPrice: ₹{price:.2f}\nYour Balance: ₹{float(bal):.2f}",
            btn([[("💰 Add Balance","addbal")],[("Back","backcat")]])
        )
        return
    if not plan.get("keys"):
        await edit_msg(
            bot, chat_id, message_id,
            "❌ <b>Out of Stock!</b>\n\nIs plan ke liye koi key nahi hai.\nAdmin se contact karo.",
            btn([[("Back","backcat")]])
        )
        return

    balances[str(user_id)] = bal - price
    save_json("balances.json", balances)

    key = plan["keys"].pop(0)
    save_json("products.json", products)

    order_id = f"ORD{int(time.time())}{random.randint(100,999)}"
    now = datetime.now().strftime("%d %b %Y %H:%M")
    try:
        user_obj = await bot.get_chat(user_id)
        username = getattr(user_obj, "username", "") or ""
        first_name = getattr(user_obj, "first_name", "") or "User"
    except Exception:
        username = ""
        first_name = "User"
    orders[order_id] = {
        "user": user_id, "username": username, "name": first_name, "product_id": pid,
        "product_name": p["name"], "plan": plan,
        "price": price, "duration": duration_text(plan), "days": plan.get("days"),
        "status": "Delivered", "date": now, "key": key
    }
    save_json("orders.json", orders)
    await reward_referrer(bot, user_id, "purchase")
    try:
        await notify_admin_new_order(bot, order_id, user_id, p["name"], plan, price, key, now)
    except Exception:
        pass

    # Purchase-success receipt. Keep the key inside a Telegram quote block
    # and provide Telegram's native Copy Text button for the exact key.
    current_balance = balances.get(str(user_id), 0)
    msg = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>✅ Purchased Successfully</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🛍️ Product : {html.escape(str(p['name']))}</b>\n"
        f"<b>✈️ Plan : {html.escape(str(duration_text(plan)))}</b>\n"
        f"<b>🕣 Date &amp; Time : {html.escape(str(now))}</b>\n"
        f"<b>🆔 Order ID : {html.escape(str(order_id))}</b>\n"
        f"<blockquote><b>🔑 License Key : {html.escape(str(key))}</b></blockquote>\n"
        f"<b>Now Your Balance : ₹{float(current_balance):.2f}</b>"
    )
    # Telegram's native Copy Text button copies only the license key.
    copy_key_button = InlineKeyboardButton(
        text="📋 Copy Key",
        copy_text=CopyTextButton(text=str(key))
    )
    await edit_msg(
        bot, chat_id, message_id, msg,
        InlineKeyboardMarkup([
            [copy_key_button],
            [InlineKeyboardButton(text="📦 My Orders", callback_data="orders", style="success")],
            [InlineKeyboardButton(text="Back To Menu", callback_data="back", style="danger")]
        ])
    )

# ============================================================
# ADMIN MENUS
# ============================================================
async def send_admin_panel(bot, chat_id, message_id=0):
    s = load_json("settings.json")
    users = load_json("users.json")
    msg = (
        "👑 <b>Admin Panel</b>\n\n"
        f"👥 Total Users: {len(users)}\n"
        f"📄 Proof: {html.escape(str(s.get('proof_link','')))}\n"
        f"📖 HowTo: {html.escape(str(s.get('howto_link','')))}\n"
        f"💬 Support: {html.escape(str(s.get('support_user','')))}\n"
        f"📥 Download Files: {html.escape(str(s.get('download_link','')))}\n"
    )
    bot_enabled = bool(s.get("bot_enabled", True))
    status_text = "🟢 <b>Bot Status : ON</b>" if bot_enabled else "🔴 <b>Bot Status : OFF</b>"
    toggle_text = "🔴 Turn Bot OFF" if bot_enabled else "🟢 Turn Bot ON"
    kb = btn([
        [(status_text, "bot_status_info")],
        [(toggle_text, "bot_toggle")],
        [("✏️ Edit Maintenance Message", "edit_maintenance_message")],
        [("🛍️ Product ON / OFF", "products_toggle")],
        [("📁 Category Management", "category_manage")],
        [("📦 Add Product", "addprod"), ("✏️ Edit Product", "editprod"), ("🗑️ Delete Product", "delprod")],
        [("🔗 Product Links", "product_links")],
        [("➕ Add Plan", "addplan"), ("✏️ Edit Plan", "editplan"), ("🗑️ Delete Plan", "delplan")],
        [("🔑 Add Plan Keys", "addplankeys")],
        [("💰 Add User Balance", "adduserbal")],
        [("👥 User List", "userlist")],
        [("🔐 User Password Status", "password_users")],
        [("💎 Reseller Settings", "reseller_settings", "primary")],
        [("📢 Broadcast", "broadcast")],
        [("🔁 Automatic Channel Broadcast", "auto_bc_home")],
        [("🎟️ Create Coupon Code", "create_coupon")],
        [("🎡 Lucky Spin Settings", "lucky_spin_settings")],
        [("🎮 Play & Earn Settings", "playearn_settings")],
        [("🎯 Daily Task Settings", "daily_task_settings")],
        [("🕹️ Admin Game Controls", "game_controls")],
        [("🔄 Restart Game Cooldowns", "restartgame_confirm")],
        [("📄 Proof Link", "setproof")],
        [("✏️ Edit Start Menu", "edit_start_menu")],
        [("🎨 Start Menu Button Settings", "start_menu_buttons_admin")],
        [("📖 HowTo Link", "sethowto")],
        [("💬 Support User Name", "setsupport")],
        [("🎫 Daily Ticket Limit", "set_ticket_daily_limit", "primary")],
        [("📢 Order Channel ID", "set_order_channel")],
        [("📥 Download Files Link", "setdownload")],
        [("🔎 Search Order", "search_order")],
    ])
    if message_id:
        await edit_msg(bot, chat_id, message_id, msg, kb)
    else:
        await send_message(bot, chat_id, msg, kb)

async def product_picker(bot, chat_id, message_id, title, callback_prefix):
    products = load_json("products.json")
    if not products:
        await edit_msg(bot, chat_id, message_id, "❌ <b>Koi Product nahi hai!</b>", btn([[("Back","backadmin")]]))
        return
    rows = []
    for pid, p in products.items():
        rows.append([(f"{p.get('name','')} ({len(p.get('plans',[]))} plans)", f"{callback_prefix}{pid}")])
    rows.append([("Back","backadmin")])
    await edit_msg(bot, chat_id, message_id, title, btn(rows))

async def product_links_picker(bot, chat_id, message_id):
    products = load_json("products.json")
    if not products:
        await edit_msg(bot, chat_id, message_id, "❌ <b>No Products Found!</b>", btn([[ ("Back", "backadmin") ]]))
        return
    rows = []
    for pid, p in products.items():
        rows.append([(f"🔗 {p.get('name','')} ({pid})", f"productlink_{pid}")])
    rows.append([("Back", "backadmin")])
    await edit_msg(
        bot, chat_id, message_id,
        "🔗 <b>Product Links</b>\n\nSelect a product to get its Telegram deep link.",
        btn(rows)
    )

async def show_product_link(bot, chat_id, message_id, pid):
    products = load_json("products.json")
    product = products.get(pid)
    if not product:
        await edit_msg(bot, chat_id, message_id, "❌ <b>Product not found!</b>", btn([[ ("Back", "product_links") ]]))
        return

    username = await get_bot_username(bot)
    link = product_deep_link(username, pid)
    if not link:
        await edit_msg(bot, chat_id, message_id, "❌ <b>Could not detect the bot username.</b>\n\nSet the correct <code>shop_bot_link</code> in settings.json and try again.", btn([[ ("Back", "product_links") ]]))
        return

    # Telegram's native Copy Text button copies only the link.
    copy_button = InlineKeyboardButton(text="📋 Copy Product Link", copy_text=CopyTextButton(text=link))
    open_button = InlineKeyboardButton(text="🚀 Open Product", url=link)
    await edit_msg(
        bot, chat_id, message_id,
        f"🔗 <b>PRODUCT LINK</b>\n\n"
        f"📦 <b>Product:</b> {html.escape(str(product.get('name','')))}\n"
        f"🆔 <b>Product ID:</b> <code>{html.escape(str(pid))}</code>\n\n"
        f"🔗 <code>{html.escape(link)}</code>\n\n"
        f"<b>ഈ link click ചെയ്താൽ Bot തുറന്ന് നേരിട്ട് ഈ Product-ലേക്ക് പോകും.</b>",
        InlineKeyboardMarkup([[copy_button], [open_button], [InlineKeyboardButton(text="Back", callback_data="product_links", style="danger")]])
    )

async def product_status_picker(bot, chat_id, message_id):
    products = load_json("products.json")
    if not products:
        await edit_msg(
            bot, chat_id, message_id,
            "❌ <b>No Products Found!</b>",
            btn([[("Back", "backadmin")]])
        )
        return

    rows = []
    for pid, p in products.items():
        enabled = p.get("enabled", True)
        status = "🟢 ON" if enabled else "🔴 OFF"
        rows.append([(
            f"{status}  {p.get('name','')}",
            f"toggleprod_{pid}",
            "primary" if enabled else "danger"
        )])
    rows.append([("Back", "backadmin")])

    await edit_msg(
        bot, chat_id, message_id,
        "🛍️ <b>Products ON / OFF</b>\n\n"
        "Tap a product to change its status.\n"
        "🟢 ON = available for purchase\n"
        "🔴 OFF = Under Maintenance",
        btn(rows)
    )

async def category_picker(bot, chat_id, message_id):
    categories = load_json("categories.json")
    if not categories:
        await edit_msg(bot, chat_id, message_id, "❌ <b>Koi Category nahi hai!</b>\n\nPehle '📁 Add Category' se category add karo.", btn([[("Back","backadmin")]]))
        return
    rows = [[(c["name"], f"addtoprod_{cid}")] for cid,c in categories.items()]
    rows.append([("❌Cancel","backadmin")])
    await edit_msg(bot, chat_id, message_id, "📁 <b>Kis Category me Product Add karna hai?</b>", btn(rows))


async def category_management_menu(bot, chat_id, message_id):
    categories = load_json("categories.json")
    await edit_msg(bot, chat_id, message_id,
        f"📁 <b>Category Management</b>\n\nTotal Categories: <b>{len(categories)}</b>\n\nChoose an action:",
        btn([[("➕ Add Category", "addcat")],
             [("✏️ Rename / Style Category", "category_edit_pick")],
             [("🗑️ Delete Category", "category_delete_pick")],
             [("Back to Admin", "backadmin")]]))


async def category_action_picker(bot, chat_id, message_id, action):
    categories = load_json("categories.json")
    if not categories:
        await edit_msg(bot, chat_id, message_id, "❌ <b>No categories found.</b>", btn([[("Back", "category_manage")]]))
        return
    rows = [[(c.get("name", "Unnamed"), f"category_{action}_{cid}", c.get("style"))]
            for cid, c in categories.items()]
    rows.append([("Back", "category_manage")])
    title = "Select a category to edit:" if action == "edit" else "Select a category to delete:"
    await edit_msg(bot, chat_id, message_id, f"📁 <b>{title}</b>", btn(rows))


async def category_style_picker(bot, chat_id, message_id, mode, cid=""):
    await edit_msg(bot, chat_id, message_id, "🎨 <b>Choose Category Button Style</b>\n\nSelect a colour:",
        btn([[("🔴 Red", f"catstyle_{mode}_{cid}_danger", "danger")],
             [("🟢 Green", f"catstyle_{mode}_{cid}_success", "success")],
             [("🔵 Blue", f"catstyle_{mode}_{cid}_primary", "primary")],
             [("⚪ Default / Transparent", f"catstyle_{mode}_{cid}_none")],
             [("❌Cancel", "category_manage")]]))


async def category_edit_menu(bot, chat_id, message_id, cid):
    categories = load_json("categories.json")
    category = categories.get(cid)
    if not category:
        await edit_msg(bot, chat_id, message_id, "❌ Category not found.", btn([[("Back", "category_manage")]]))
        return
    current = category.get("style") or "default"
    await edit_msg(bot, chat_id, message_id,
        f"✏️ <b>Edit Category</b>\n\nName: <b>{html.escape(str(category.get('name', '')))}</b>\nButton Style: <b>{html.escape(str(current).title())}</b>",
        btn([[("✏️ Rename", f"category_rename_{cid}")],
             [("🎨 Change Button Style", f"category_restyle_{cid}")],
             [("Back", "category_edit_pick")]]))


async def add_plan_product_picker(bot, chat_id, message_id):
    await product_picker(bot, chat_id, message_id, "➕ <b>Kis Product me Plan Add karna hai?</b>", "addplanprod_")

async def add_keys_product_picker(bot, chat_id, message_id):
    await product_picker(bot, chat_id, message_id, "🔑 <b>Kis Product ke Plan me Keys Add karna hai?</b>", "addkeysprod_")

async def edit_plan_product_picker(bot, chat_id, message_id):
    await product_picker(bot, chat_id, message_id, "✏️ <b>Kis Product ka Plan Edit karna hai?</b>", "editplanprod_")

async def delete_plan_product_picker(bot, chat_id, message_id):
    await product_picker(bot, chat_id, message_id, "🗑️ <b>Kis Product ka Plan Delete karna hai?</b>", "delplanprod_")

async def edit_product_picker(bot, chat_id, message_id):
    await product_picker(bot, chat_id, message_id, "✏️ <b>Kis Product ko Edit karna hai?</b>", "editprod_")

async def delete_product_picker(bot, chat_id, message_id):
    await product_picker(
        bot, chat_id, message_id,
        "🗑️ <b>Kis Product ko Delete karna hai?</b>\n\n⚠️ <b>Warning:</b> Product delete karne se uske saare plans aur keys bhi delete ho jayenge!",
        "delprod_"
    )

async def plans_picker(bot, chat_id, message_id, pid, mode):
    products = load_json("products.json")
    p = products.get(pid)
    if not p:
        await edit_msg(bot, chat_id, message_id, "❌ Product nahi mila", btn([[("Back","backadmin")]]))
        return
    plans = p.get("plans", [])
    if not plans:
        await edit_msg(bot, chat_id, message_id, "❌ <b>Is product me koi plan nahi hai!</b>", btn([[("Back","backadmin")]]))
        return
    rows = []
    for i, plan in enumerate(plans):
        count = len(plan.get("keys", []))
        if mode == "addkeys":
            data = f"addkeysplan_{pid}_{i}"
            label = f"{duration_text(plan)} - ₹{plan['price']} ({count} keys)"
        elif mode == "edit":
            data = f"editplan_{pid}_{i}"
            label = f"{duration_text(plan)} - ₹{plan['price']} ({count} keys)"
        else:
            data = f"delplan_{pid}_{i}"
            label = f"❌ {duration_text(plan)} - ₹{plan['price']}"
        rows.append([(label, data)])
    rows.append([("Back","backadmin")])
    title = {
        "addkeys": f"🔑 <b>Add Keys - {html.escape(str(p['name']))}</b>\n\nKis plan me keys add karna hai?",
        "edit": f"✏️ <b>Edit Plan - {html.escape(str(p['name']))}</b>\n\nKis plan ko edit karna hai?",
        "delete": f"🗑️ <b>Delete Plan - {html.escape(str(p['name']))}</b>\n\nKis plan ko delete karna hai?"
    }[mode]
    await edit_msg(bot, chat_id, message_id, title, btn(rows))

# ============================================================
# PAYMENT
# ============================================================
async def broadcast_to_users(bot, users, source_chat_id, source_message_id):
    """Reliably copy a broadcast to registered users, retrying rate/network errors."""
    sent = failed = unreachable = 0
    for raw_uid in list(users):
        try:
            uid = int(raw_uid)
        except (TypeError, ValueError):
            failed += 1
            continue

        delivered = False
        failure_counted = False
        for attempt in range(4):
            try:
                # copy_message preserves formatting, captions, media and links.
                await bot.copy_message(
                    chat_id=uid,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                )
                sent += 1
                delivered = True
                break
            except RetryAfter as exc:
                # Telegram explicitly tells us how long to wait before retrying.
                wait_seconds = float(getattr(exc, "retry_after", 1)) + 1
                await asyncio.sleep(min(max(wait_seconds, 1), 120))
            except (TimedOut, NetworkError):
                if attempt < 3:
                    await asyncio.sleep(1.5 * (attempt + 1))
                else:
                    failed += 1
                    failure_counted = True
            except (Forbidden, BadRequest):
                # Usually blocked bot, deleted account, or user never started it.
                failed += 1
                failure_counted = True
                unreachable += 1
                break
            except Exception:
                failed += 1
                failure_counted = True
                break

        if not delivered and not failure_counted:
            failed += 1

        # Keep well below Telegram's broadcast rate limit.
        await asyncio.sleep(0.1)

    return sent, failed, unreachable


def broadcast_report(total, sent, failed, unreachable):
    return (
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"👥 Total Users: {total}\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}\n"
        f"🚫 Blocked / Unreachable: {unreachable}\n\n"
        "<i>Telegram cannot deliver messages to users who blocked the bot, "
        "deleted their account, or have not started the bot.</i>"
    )

# ============================================================
# COUPONS + LUCKY SPIN
# ============================================================
def parse_expiry(value):
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=IST)
            if fmt in ("%Y-%m-%d", "%d-%m-%Y"):
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            pass
    return None

def lucky_reward():
    s = load_json("settings.json")
    try:
        minimum = float(s.get("lucky_spin_min_reward", 1.0))
        maximum = float(s.get("lucky_spin_max_reward", 5.0))
    except (TypeError, ValueError):
        minimum, maximum = 1.0, 5.0
    minimum = max(0.0, minimum)
    maximum = max(minimum, maximum)
    return round(random.uniform(minimum, maximum), 2)

async def show_claim_coupon(bot, chat_id, message_id):
    await edit_msg(bot, chat_id, message_id, "🎟️ <b>Claim Coupon Code</b>\n\nSend your coupon code to claim the balance.", btn([[('Back', 'back')]]))

async def do_lucky_spin(bot, chat_id, user_id, message_id):
    users = load_json("users.json"); balances = load_json("balances.json"); uid = str(user_id)
    user = users.get(uid, {}); last = float(user.get("last_lucky_spin", 0) or 0); remaining = 86400 - (time.time() - last)
    if remaining > 0:
        h = int(remaining // 3600); m = int((remaining % 3600) // 60)
        await edit_msg(bot, chat_id, message_id, f"⏳ <b>Lucky Spin Already Used</b>\n\nTry again after <b>{h}h {m}m</b>.", btn([[('Back','back')]])); return
    reward = lucky_reward(); balances[uid] = round(float(balances.get(uid, 0) or 0) + reward, 2); user["last_lucky_spin"] = time.time(); users[uid] = user
    save_json("balances.json", balances); save_json("users.json", users)
    await edit_msg(bot, chat_id, message_id, f"🎉 <b>Lucky Spin Result!</b>\n\n🎁 You won <b>₹{reward:.2f}</b>\n💰 Balance: <b>₹{balances[uid]:.2f}</b>\n\n⏰ You can spin again after 24 hours.", btn([[('Back','back')]]))
    try:
        uname = f"@{html.escape(str(user.get('username')))}" if user.get('username') else "No username"
        await send_message(bot, int(ADMIN_ID), f"🎡 <b>Lucky Spin Claimed</b>\n\n👤 {html.escape(str(user.get('name','User')))}\n🆔 <code>{user_id}</code>\n🔗 {uname}\n🎁 Reward: <b>₹{reward:.2f}</b>")
    except Exception: pass



# ============================================================
# PLAY AND EARN — TIC-TAC-TOE (one game per 24 hours)
# ============================================================
TT_FILE = "tictactoe.json"
TT_COOLDOWN = 24 * 60 * 60
GAME_STATS_FILE = "game_stats.json"

def game_cooldown_seconds(game):
    s = load_json("settings.json")
    prefix = "tt" if game == "tt" else "rps"
    try:
        hours = float(s.get(f"{prefix}_cooldown_hours", 24))
    except (TypeError, ValueError):
        hours = 24
    return max(0, min(hours, 8760)) * 3600

def game_enabled(game):
    s = load_json("settings.json")
    return bool(s.get("tt_enabled" if game == "tt" else "rps_enabled", True))

def record_game_win(uid, game, reward):
    stats = load_json(GAME_STATS_FILE)
    key = str(uid)
    row = stats.get(key, {})
    row["wins"] = int(row.get("wins", 0) or 0) + 1
    row["reward_total"] = round(float(row.get("reward_total", 0) or 0) + float(reward), 2)
    stat_key = "tt_wins" if game == "tt" else "rps_wins"
    row[stat_key] = int(row.get(stat_key, 0) or 0) + 1
    row["last_win"] = int(time.time())
    stats[key] = row
    save_json(GAME_STATS_FILE, stats)

def daily_task_day_key():
    return now_ist().strftime("%Y-%m-%d")

def daily_task_day_data(data=None, create=True):
    """Return today's multi-task container, migrating the previous single-task format safely."""
    if data is None:
        data = load_json("daily_tasks.json")
    day = daily_task_day_key()
    current = data.get(day)
    if not isinstance(current, dict):
        current = {"tasks": []}
        if create:
            data[day] = current
            save_json("daily_tasks.json", data)
        return data, current
    if not isinstance(current.get("tasks"), list):
        # Migrate the old single Daily Task without losing today's accepted users/progress.
        settings_now = load_json("settings.json")
        legacy = {
            "id": "1", "name": "Daily Task", "required": max(1, int(settings_now.get("daily_task_games", 2) or 2)),
            "max_users": max(1, int(settings_now.get("daily_task_max_users", 100) or 100)),
            "reward": float(settings_now.get("daily_task_reward", 1.0) or 0),
            "enabled": bool(settings_now.get("daily_task_enabled", True)),
            "users": current.get("users", {}) if isinstance(current.get("users", {}), dict) else {},
            "participants": current.get("participants", []) if isinstance(current.get("participants", []), list) else [],
            "rewarded_users": current.get("rewarded_users", []) if isinstance(current.get("rewarded_users", []), list) else [],
        }
        current = {"tasks": [legacy]}
        data[day] = current
        save_json("daily_tasks.json", data)
    return data, current

def daily_task_status(uid, task_id=None):
    data, day_data = daily_task_day_data()
    key = str(uid)
    tasks = [t for t in day_data.get("tasks", []) if isinstance(t, dict) and t.get("enabled", True)]
    statuses = []
    for task in tasks:
        users = task.setdefault("users", {})
        row = users.get(key, {}) if isinstance(users.get(key, {}), dict) else {}
        participants = task.setdefault("participants", [])
        rewarded = task.setdefault("rewarded_users", [])
        statuses.append({
            "id": str(task.get("id", "1")), "name": str(task.get("name") or f"Task {task.get('id', '1')}"),
            "games": int(row.get("games", 0) or 0), "required": max(1, int(task.get("required", 2) or 2)),
            "max_users": max(1, int(task.get("max_users", 100) or 100)), "participant_count": len(participants),
            "participant": key in participants, "rewarded_count": len(rewarded),
            "rewarded": bool(row.get("rewarded", False)) or key in rewarded,
            "limit_reached": bool(row.get("limit_reached", False)), "reward": max(0.0, float(task.get("reward", 0) or 0)),
            "enabled": bool(task.get("enabled", True)),
        })
    if task_id is not None:
        return next((x for x in statuses if x["id"] == str(task_id)), None)
    return {"enabled": bool(statuses), "tasks": statuses}

def daily_task_is_participant(uid):
    status = daily_task_status(uid)
    return any(t["participant"] and not t["rewarded"] for t in status.get("tasks", []))

def daily_task_can_play(uid):
    status = daily_task_status(uid)
    return any(t["participant"] and not t["rewarded"] and t["games"] < t["required"] for t in status.get("tasks", []))

async def record_daily_task_game(bot, uid, game_name):
    """Count one completed game toward every accepted, unfinished task for today."""
    data, day_data = daily_task_day_data()
    key = str(uid)
    notes = []
    changed = False
    for task in day_data.get("tasks", []):
        if not isinstance(task, dict) or not task.get("enabled", True):
            continue
        participants = task.setdefault("participants", [])
        if key not in participants:
            continue
        users = task.setdefault("users", {})
        row = users.setdefault(key, {"games": 0, "rewarded": False})
        required = max(1, int(task.get("required", 2) or 2))
        reward = max(0.0, float(task.get("reward", 0) or 0))
        max_users = max(1, int(task.get("max_users", 100) or 100))
        rewarded_users = task.setdefault("rewarded_users", [])
        if row.get("rewarded") or key in rewarded_users:
            continue
        row["games"] = min(required, int(row.get("games", 0) or 0) + 1)
        changed = True
        if row["games"] >= required:
            if len(rewarded_users) < max_users:
                balances = load_json("balances.json")
                balances[key] = round(float(balances.get(key, 0) or 0) + reward, 2)
                save_json("balances.json", balances)
                row["rewarded"] = True
                row["reward"] = reward
                rewarded_users.append(key)
                notes.append(f"✅ <b>{html.escape(str(task.get('name') or 'Daily Task'))} completed!</b> 🎁 ₹{reward:.2f} added. Balance: ₹{balances[key]:.2f}")
                try:
                    user_record = load_json("users.json").get(key, {})
                    name = html.escape(str(user_record.get("name") or user_record.get("first_name") or "User"))
                    await bot.send_message(chat_id=int(ADMIN_ID), text=(
                        "🎯 <b>DAILY TASK REWARD</b>\n\n" f"📌 Task: <b>{html.escape(str(task.get('name') or 'Daily Task'))}</b>\n"
                        f"👤 {name}\n🆔 <code>{uid}</code>\n🎮 Games completed: {required}\n🎁 Reward: <b>₹{reward:.2f}</b>\n"
                        f"📊 Rewarded users for this task: <b>{len(rewarded_users)}/{max_users}</b>"
                    ), parse_mode="HTML")
                except Exception as exc:
                    print(f"Could not notify admin about Daily Task reward: {exc}")
            else:
                row["limit_reached"] = True
                notes.append(f"⚠️ {html.escape(str(task.get('name') or 'Daily Task'))}: games completed, but its reward-user limit has been reached.")
        else:
            notes.append(f"🎯 <b>{html.escape(str(task.get('name') or 'Daily Task'))} progress:</b> {row['games']}/{required} games.")
    if changed:
        save_json("daily_tasks.json", data)
    return "\n".join(notes)

async def show_daily_task(bot, chat_id, message_id, uid):
    status = daily_task_status(uid)
    tasks = status.get("tasks", [])
    if not tasks:
        await edit_msg(bot, chat_id, message_id,
            "🎯 <b>DAILY TASKS</b>\n\n❌ <b>No Task Available</b>\n\nPlease check back later.",
            btn([[('🔄 Refresh','daily_task','primary')], [('Back To Menu','back','danger')]]))
        return
    lines = ["🎯 <b>DAILY TASKS</b>", f"📅 Date: <b>{daily_task_day_key()}</b>", ""]
    rows = []
    for task in tasks:
        lines.append(f"<b>📌 {html.escape(task['name'])}</b>")
        lines.append(f"🎮 Games: <b>{task['games']}/{task['required']}</b>  •  🎁 Reward: <b>₹{task['reward']:.2f}</b>")
        lines.append(f"👥 Accepted: <b>{task['participant_count']}/{task['max_users']}</b>")
        if task["rewarded"]:
            lines.append("✅ <b>Completed — reward already received.</b>")
        elif task["limit_reached"]:
            lines.append("⚠️ This task's reward limit has been reached.")
        elif task["participant"]:
            lines.append("🟢 <b>Accepted — keep playing to finish this task.</b>")
            rows.append([(f"🎮 Continue: {task['name']}"[:60], f"daily_task_play_{task['id']}", "success")])
        elif task["participant_count"] >= task["max_users"]:
            lines.append("⚠️ <b>This task is full.</b>")
        else:
            lines.append("Tap Accept to start this task. Earlier games do not count.")
            rows.append([(f"✅ Accept: {task['name']}"[:60], f"daily_task_accept_{task['id']}", "success")])
        lines.append("")
    rows.extend([[('🔄 Refresh','daily_task','primary')], [('Back To Menu','back','danger')]])
    lines.append("Each task can be rewarded only once per user. New tasks can be completed even after finishing another task. A game played after accepting counts toward all your accepted unfinished tasks. Daily Tasks have no 24-hour cooldown; normal Play And Earn rules remain unchanged for users without an accepted task.")
    await edit_msg(bot, chat_id, message_id, "\n".join(lines), btn(rows))

async def accept_daily_task(bot, chat_id, message_id, uid, task_id):
    data, day_data = daily_task_day_data()
    task = next((t for t in day_data.get("tasks", []) if isinstance(t, dict) and str(t.get("id")) == str(task_id) and t.get("enabled", True)), None)
    if not task:
        await show_daily_task(bot, chat_id, message_id, uid)
        return
    key = str(uid)
    participants = task.setdefault("participants", [])
    users = task.setdefault("users", {})
    row = users.get(key, {}) if isinstance(users.get(key, {}), dict) else {}
    if row.get("rewarded") or key in task.setdefault("rewarded_users", []):
        await show_daily_task(bot, chat_id, message_id, uid)
        return
    max_users = max(1, int(task.get("max_users", 100) or 100))
    if key not in participants:
        if len(participants) >= max_users:
            await edit_msg(bot, chat_id, message_id, f"⚠️ <b>{html.escape(str(task.get('name') or 'This task'))} is full.</b>", btn([[('🔄 Refresh','daily_task','primary')],[('Back To Menu','back','danger')]]))
            return
        participants.append(key)
        users[key] = {"games": 0, "rewarded": False}
    save_json("daily_tasks.json", data)
    await show_daily_task(bot, chat_id, message_id, uid)

def leaderboard_text():
    stats = load_json(GAME_STATS_FILE)
    users = load_json("users.json")
    if not stats:
        return "🏆 <b>TOP WINNERS</b>\n\nNo wins recorded yet. Be the first to win!"
    ordered = sorted(stats.items(), key=lambda item: (int(item[1].get("wins", 0) or 0), float(item[1].get("reward_total", 0) or 0)), reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>TOP WINNERS</b>", "", "Ranked by total wins • Top 10"]
    for index, (uid, row) in enumerate(ordered, 1):
        user = users.get(str(uid), {})
        name = str(user.get("name") or user.get("first_name") or f"User {uid}")
        name = html.escape(name[:40])
        icon = medals[index-1] if index <= 3 else f"{index}."
        lines.append(f"{icon} <b>{name}</b> — {int(row.get('wins', 0) or 0)} wins\n   💰 Reward earned: ₹{float(row.get('reward_total', 0) or 0):.2f}")
    return "\n".join(lines)

def game_reward_range(game):
    s = load_json("settings.json")
    prefix = "tt" if game == "tt" else "rps"
    minimum = float(s.get(f"{prefix}_min_reward", 0.01))
    maximum = float(s.get(f"{prefix}_max_reward", 0.75))
    return minimum, maximum

async def notify_admin_game_win(bot, uid, game_name, reward, new_balance, details):
    """Send full winner and reward details to the configured admin chat."""
    try:
        user_id = int(uid)
        user_record = load_json("users.json").get(str(uid), {})
        name = str(user_record.get("name") or user_record.get("first_name") or "Unknown")
        username = str(user_record.get("username") or "")
        if username and not username.startswith("@"):
            username = "@" + username
        try:
            chat_user = await bot.get_chat(user_id)
            name = chat_user.first_name or name
            if chat_user.last_name:
                name += " " + chat_user.last_name
            if chat_user.username:
                username = "@" + chat_user.username
        except Exception:
            pass
        if not username:
            username = "Not set"
        previous_balance = round(float(new_balance) - float(reward), 2)
        report = (
            "🏆 <b>PLAY AND EARN — USER WON</b>\n\n"
            f"🎮 <b>Game:</b> {html.escape(game_name)}\n"
            f"👤 <b>Name:</b> {html.escape(name)}\n"
            f"🔗 <b>Username:</b> {html.escape(username)}\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"🕒 <b>Time:</b> {now_ist().strftime('%d-%m-%Y %I:%M:%S %p IST')}\n"
            f"📋 <b>Game Details:</b> {html.escape(details)}\n"
            f"🎁 <b>Reward:</b> ₹{float(reward):.2f}\n"
            f"💰 <b>Previous Balance:</b> ₹{previous_balance:.2f}\n"
            f"💳 <b>New Balance:</b> ₹{float(new_balance):.2f}"
        )
        await bot.send_message(chat_id=int(ADMIN_ID), text=report, parse_mode="HTML")
    except Exception as exc:
        # A notification failure must not undo the user's valid game reward.
        print(f"Could not send Play & Earn win notification to admin: {exc}")

def tt_winner(board):
    lines = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))
    for a,b,c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return None

def tt_minimax(board, turn, bot_symbol, depth=0):
    result = tt_winner(board)
    if result:
        if result == bot_symbol:
            return 10 - depth, None
        if result == "draw":
            return 0, None
        return depth - 10, None
    best_score = -100 if turn == bot_symbol else 100
    best_moves = []
    for i, cell in enumerate(board):
        if cell is not None:
            continue
        board[i] = turn
        next_turn = "O" if turn == "X" else "X"
        score, _ = tt_minimax(board, next_turn, bot_symbol, depth + 1)
        board[i] = None
        if turn == bot_symbol:
            if score > best_score:
                best_score, best_moves = score, [i]
            elif score == best_score:
                best_moves.append(i)
        else:
            if score < best_score:
                best_score, best_moves = score, [i]
            elif score == best_score:
                best_moves.append(i)
    return best_score, (random.choice(best_moves) if best_moves else None)

def tt_keyboard(game, uid):
    board = game["board"]
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            symbol = board[i]
            label = symbol if symbol else "ㅤ"
            if symbol == game["user_symbol"]:
                color = "success"  # user clicked
            elif symbol == game["bot_symbol"]:
                color = "primary"  # bot clicked
            else:
                color = "danger"  # empty
            row.append(InlineKeyboardButton(label, callback_data=f"tt_move_{uid}_{i}", style=color))
        rows.append(row)
    rows.append([InlineKeyboardButton("Back To Menu", callback_data="back", style="danger")])
    return InlineKeyboardMarkup(rows)

async def tt_render(bot, chat_id, message_id, uid, text=None):
    games = load_json(TT_FILE)
    game = games.get(str(uid))
    if not game:
        return
    board = game["board"]
    if text is None:
        text = (f"🎮 <b>TIC-TAC-TOE — PLAY & EARN</b>\n\n"
                f"Your symbol: <b>{game['user_symbol']}</b>\n"
                f"Bot symbol: <b>{game['bot_symbol']}</b>\n\n"
                "Tap a red empty button to make your move.")
    await edit_msg(bot, chat_id, message_id, text, tt_keyboard(game, uid))

async def tt_start(bot, chat_id, message_id, uid):
    games = load_json(TT_FILE)
    key = str(uid)
    now = int(time.time())
    old = games.get(key, {})
    last_play = int(old.get("last_play", 0) or 0)
    cooldown = game_cooldown_seconds("tt")
    if not game_enabled("tt"):
        await edit_msg(bot, chat_id, message_id, "🛠️ <b>TicTacToe is temporarily disabled by Admin.</b>", btn([[ ("Back to Games", "play_earn_menu") ]]))
        return
    if now - last_play < cooldown and not daily_task_can_play(uid):
        remaining = cooldown - (now - last_play)
        hours, rem = divmod(remaining, 3600)
        minutes = rem // 60
        await edit_msg(bot, chat_id, message_id,
                       f"⏳ <b>You have already played.</b>\nTry again in <b>{hours}h {minutes}m</b>.",
                       btn([[("Back To Menu", "back")]]))
        return
    # The user always makes the first move, regardless of which symbol is assigned.
    user_symbol = random.choice(["X", "O"])
    game = {"board": [None] * 9, "user_symbol": user_symbol,
            "bot_symbol": "O" if user_symbol == "X" else "X",
            "last_play": now, "active": True}
    games[key] = game
    save_json(TT_FILE, games)
    # Do not let the bot place a symbol before the user.
    await tt_render(bot, chat_id, message_id, uid)

async def tt_move(bot, chat_id, message_id, uid, index):
    games = load_json(TT_FILE)
    key = str(uid)
    game = games.get(key)
    if not game or not game.get("active"):
        await edit_msg(bot, chat_id, message_id, "🎮 <b>Start a new game from Play And Earn.</b>",
                       btn([[("Back To Menu", "back")]]))
        return
    board = game["board"]
    if index < 0 or index > 8 or board[index] is not None:
        await tt_render(bot, chat_id, message_id, uid, "❌ <b>That square is not empty. Choose a red button.</b>")
        return
    board[index] = game["user_symbol"]
    result = tt_winner(board)
    if not result:
        # Balanced bot mode: on each bot turn, use the optimal move 50% of the
        # time and a random legal move 50% of the time. This makes the bot less
        # predictable and gives the user a fairer chance, but actual win rates
        # can vary with user decisions and draws.
        empty_moves = [i for i, cell in enumerate(board) if cell is None]
        if empty_moves and random.random() < 0.5:
            move = random.choice(empty_moves)
        else:
            _, move = tt_minimax(board, game["bot_symbol"], game["bot_symbol"])
        if move is not None:
            board[move] = game["bot_symbol"]
        result = tt_winner(board)
    games[key] = game
    if result:
        game["active"] = False
        games[key] = game
        if result == game["user_symbol"]:
            reward = round(random.uniform(*game_reward_range("tt")), 2)
            balances = load_json("balances.json")
            balances[key] = round(float(balances.get(key, 0) or 0) + reward, 2)
            save_json("balances.json", balances)
            record_game_win(uid, "tt", reward)
            await notify_admin_game_win(
                bot, uid, "TicTacToe", reward, balances[key],
                f"User symbol: {game['user_symbol']}; Bot symbol: {game['bot_symbol']}; Final board: {' | '.join(str(cell or 'Empty') for cell in board)}"
            )
            final_text = (f"🎉 <b>You won!</b>\n\n🏆 Reward: <b>₹{reward:.2f}</b>\n"
                          f"💰 Balance: <b>₹{balances[key]:.2f}</b>\n\n" +
                          ("🎯 Daily Task mode: continue playing without the 24-hour cooldown." if daily_task_is_participant(uid) else "⏳ You can play again after 24 hours."))
        elif result == "draw":
            final_text = "🤝 <b>It's a draw!</b>\n\nNo reward this time." + ("\n🎯 Daily Task mode: continue playing to complete your task." if daily_task_is_participant(uid) else "\n⏳ You can play again after 24 hours.")
        else:
            final_text = "🤖 <b>The bot won!</b>\n\nNo reward this time." + ("\n🎯 Daily Task mode: continue playing to complete your task." if daily_task_is_participant(uid) else "\n⏳ You can play again after 24 hours.")
        task_note = await record_daily_task_game(bot, uid, "TicTacToe")
        final_text += "\n\n" + task_note
        save_json(TT_FILE, games)
        await edit_msg(bot, chat_id, message_id, final_text, tt_keyboard(game, uid))
        return
    save_json(TT_FILE, games)
    await tt_render(bot, chat_id, message_id, uid)


# ============================================================
# PLAY AND EARN — ROCK PAPER SCISSORS (separate 24-hour limit)
# ============================================================
RPS_FILE = "rock_paper_scissors.json"
RPS_CHOICES = {"rock": "✊ Rock", "paper": "📄 Paper", "scissors": "✂️ Scissors"}

def play_earn_keyboard():
    s = load_json("settings.json")
    tt_label = "❌⭕ TicTacToe" if s.get("tt_enabled", True) else "⛔ TicTacToe (OFF)"
    rps_label = "✊ Rock Paper Scissors" if s.get("rps_enabled", True) else "⛔ Rock Paper Scissors (OFF)"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tt_label, callback_data="tt_start", style="primary")],
        [InlineKeyboardButton(rps_label, callback_data="rps_start", style="primary")],
        [InlineKeyboardButton("Back To Menu", callback_data="back", style="danger")],
    ])

def rps_keyboard(uid, user_choice=None, bot_choice=None):
    rows = []
    for key, label in RPS_CHOICES.items():
        if key == user_choice:
            style = "success"  # user clicked
        elif key == bot_choice:
            style = "primary"  # bot clicked
        else:
            style = "danger"  # empty
        rows.append([InlineKeyboardButton(label, callback_data=f"rps_pick_{uid}_{key}", style=style)])
    rows.append([InlineKeyboardButton("Back to Games", callback_data="play_earn_menu", style="danger")])
    return InlineKeyboardMarkup(rows)

async def rps_start(bot, chat_id, message_id, uid):
    games = load_json(RPS_FILE)
    old = games.get(str(uid), {})
    now = int(time.time())
    last_play = int(old.get("last_play", 0) or 0)
    cooldown = game_cooldown_seconds("rps")
    if not game_enabled("rps"):
        await edit_msg(bot, chat_id, message_id, "🛠️ <b>Rock Paper Scissors is temporarily disabled by Admin.</b>", btn([[ ("Back to Games", "play_earn_menu") ]]))
        return
    if now - last_play < cooldown and not daily_task_can_play(uid):
        remaining = cooldown - (now - last_play)
        hours, rem = divmod(remaining, 3600)
        minutes = rem // 60
        await edit_msg(bot, chat_id, message_id,
            f"⏳ <b>Rock Paper Scissors already played.</b>\nTry again in <b>{hours}h {minutes}m</b>.",
            btn([[('Back to Games', 'play_earn_menu')]]))
        return
    await edit_msg(bot, chat_id, message_id,
        "✊ <b>ROCK PAPER SCISSORS — PLAY & EARN</b>\n\n"
        "Choose one button. 🟢 Your choice will be green, 🔵 the bot's choice blue, and 🔴 the empty choices red.",
        rps_keyboard(uid))

async def rps_play(bot, chat_id, message_id, uid, user_choice):
    if user_choice not in RPS_CHOICES:
        return
    if not game_enabled("rps"):
        await edit_msg(bot, chat_id, message_id, "🛠️ <b>Rock Paper Scissors is temporarily disabled by Admin.</b>", btn([[ ("Back to Games", "play_earn_menu") ]]))
        return
    games = load_json(RPS_FILE)
    key = str(uid)
    old = games.get(key, {})
    now = int(time.time())
    last_play = int(old.get("last_play", 0) or 0)
    cooldown = game_cooldown_seconds("rps")
    if now - last_play < cooldown and not daily_task_can_play(uid):
        remaining = cooldown - (now - last_play)
        hours, rem = divmod(remaining, 3600)
        await edit_msg(bot, chat_id, message_id,
            f"⏳ <b>Already played this game.</b>\nTry again in <b>{hours}h {rem // 60}m</b>.",
            btn([[('Back to Games', 'play_earn_menu')]]))
        return

    # Configured outcome odds: 75% bot win, 25% user win; ties are avoided.
    # The displayed bot choice always follows standard Rock/Paper/Scissors rules.
    user_wins = random.random() < 0.25
    beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    loses_to = {"rock": "paper", "paper": "scissors", "scissors": "rock"}
    if user_wins:
        bot_choice = beats[user_choice]
        result_text = "🎉 <b>You won!</b>"
        reward = round(random.uniform(*game_reward_range("rps")), 2)
        balances = load_json("balances.json")
        balances[key] = round(float(balances.get(key, 0) or 0) + reward, 2)
        save_json("balances.json", balances)
        record_game_win(uid, "rps", reward)
        await notify_admin_game_win(
            bot, uid, "Rock Paper Scissors", reward, balances[key],
            f"User clicked: {RPS_CHOICES[user_choice]}; Bot clicked: {RPS_CHOICES[bot_choice]}; Result: User won"
        )
        reward_text = f"\n\n🏆 Reward: <b>₹{reward:.2f}</b>\n💰 Balance: <b>₹{balances[key]:.2f}</b>"
    else:
        bot_choice = loses_to[user_choice]
        result_text = "🤖 <b>The bot won!</b>"
        reward_text = "\n\nNo reward this time."

    games[key] = {"last_play": now, "user_choice": user_choice, "bot_choice": bot_choice}
    save_json(RPS_FILE, games)
    task_note = await record_daily_task_game(bot, uid, "Rock Paper Scissors")
    user_label = RPS_CHOICES[user_choice]
    bot_label = RPS_CHOICES[bot_choice]
    await edit_msg(bot, chat_id, message_id,
        f"✊ <b>ROCK PAPER SCISSORS RESULT</b>\n\n"
        f"🟢 <b>You clicked:</b> {user_label}\n"
        f"🔵 <b>Bot clicked:</b> {bot_label}\n\n"
        f"{result_text}{reward_text}\n\n" + ("🎯 Daily Task mode: no 24-hour cooldown for accepted task users.\n\n" if daily_task_is_participant(uid) else "⏳ You can play this game again after 24 hours.\n\n") + f"{task_note}",
        rps_keyboard(uid, user_choice, bot_choice))


# ============================================================
# CALLBACK HANDLER
# ============================================================

# ============================================================
# AUTOMATIC CHANNEL BROADCAST
# Stores source message IDs and uses copy_message to preserve full
# Telegram formatting, media, captions, entities and file types.
# ============================================================
def parse_broadcast_interval(value):
    match = re.fullmatch(r"\s*(\d+)\s*([SMHD])\s*", str(value).upper())
    if not match:
        raise ValueError("Use formats such as 10S, 10M, 1H, 24H, 1D or 2D.")
    amount = int(match.group(1))
    unit = match.group(2)
    if amount < 1:
        raise ValueError("Interval must be at least 1.")
    return amount * {"S": 1, "M": 60, "H": 3600, "D": 86400}[unit]

def auto_bc_channels(s):
    channels = s.setdefault("auto_broadcast_channels", {})
    # Migrate the earlier single-channel setup without losing its messages.
    old_id = str(s.get("auto_broadcast_channel_id", "") or "").strip()
    if old_id and old_id not in channels:
        channels[old_id] = {
            "title": old_id,
            "interval": s.get("auto_broadcast_interval", "10M"),
            "enabled": bool(s.get("auto_broadcast_enabled", False)),
            "items": list(s.get("auto_broadcast_items", [])),
            "index": int(s.get("auto_broadcast_index", 0) or 0),
            "next_at": float(s.get("auto_broadcast_next_at", 0) or 0),
        }
        s["auto_broadcast_enabled"] = False
        s["auto_broadcast_items"] = []
    return channels

def auto_bc_keyboard():
    return btn([
        [("➕ Add Channel", "auto_bc_channel"), ("📡 Manage Channels", "auto_bc_channels")],
        [("🤖 Bot Auto Broadcast", "auto_bc_bot_home")],
        [("🔙 Back", "backadmin")],
    ])

async def auto_bc_home(bot, chat_id, message_id=0):
    s = load_json("settings.json")
    channels = auto_bc_channels(s)
    save_json("settings.json", s)
    active = sum(1 for c in channels.values() if c.get("enabled"))
    msg = (
        "<b>🔁 AUTOMATIC CHANNEL BROADCAST</b>\n\n"
        f"Total channels: <b>{len(channels)}</b>\n"
        f"Running channels: <b>{active}</b>\n\n"
        "Each channel has its own messages, interval, start/pause and remove controls. "
        "Bot Auto Broadcast separately sends scheduled posts to users who have started this bot."
    )
    await edit_msg(bot, chat_id, message_id, msg, auto_bc_keyboard())

async def auto_bc_channel_home(bot, chat_id, message_id, channel_id):
    s = load_json("settings.json")
    channels = auto_bc_channels(s)
    c = channels.get(str(channel_id))
    if not c:
        await auto_bc_home(bot, chat_id, message_id)
        return
    s["auto_broadcast_selected_channel"] = str(channel_id)
    save_json("settings.json", s)
    items = c.get("items", [])
    status = "RUNNING" if c.get("enabled") else "PAUSED"
    idx = int(c.get("index", 0) or 0)
    title = html.escape(str(c.get("title") or channel_id))
    last_error = str(c.get("last_error", "") or "").strip()
    error_line = f"\nLast error: <code>{html.escape(last_error[:250])}</code>" if last_error else ""
    last_sent = c.get("last_sent_at")
    sent_line = f"\nLast sent: <b>{datetime.fromtimestamp(float(last_sent), IST).strftime('%d-%m-%Y %H:%M:%S')}</b>" if last_sent else ""
    msg = (
        f"<b>📡 {title}</b>\n\n"
        f"Channel ID: <code>{html.escape(str(channel_id))}</code>\n"
        f"Status: <b>{status}</b>\n"
        f"Interval: <b>{html.escape(str(c.get('interval', '10M')))}</b>\n"
        f"Saved messages: <b>{len(items)}</b>\n"
        f"Next message: <b>{(idx % len(items)) + 1 if items else 0}</b>"
        f"{error_line}"
        f"{sent_line}"
    )
    keyboard = btn([
        [("➕ Add Message", f"auto_bc_add_{channel_id}"), ("📋 Message List", f"auto_bc_list_{channel_id}")],
        [("⏱ Set Interval", f"auto_bc_interval_{channel_id}"), ("▶️ Start" if not c.get("enabled") else "⏸ Pause", f"auto_bc_toggle_{channel_id}")],
        [("🗑 Remove Channel", f"auto_bc_remove_{channel_id}"), ("🔙 Channels", "auto_bc_channels")],
    ])
    await edit_msg(bot, chat_id, message_id, msg, keyboard)

async def auto_bc_bot_home(bot, chat_id, message_id=0):
    s = load_json("settings.json")
    cfg = s.setdefault("auto_broadcast_bot", {"enabled": False, "interval": "10M", "items": [], "index": 0, "next_at": 0, "last_error": ""})
    s["auto_broadcast_bot"] = cfg
    save_json("settings.json", s)
    status = "RUNNING" if cfg.get("enabled") else "PAUSED"
    items = cfg.get("items", [])
    err = f"\nLast error: <code>{html.escape(str(cfg.get('last_error',''))[:220])}</code>" if cfg.get("last_error") else ""
    msg = ("<b>🤖 BOT AUTO BROADCAST</b>\n\n"
           "This sends your saved posts to users who have started the bot.\n\n"
           f"Status: <b>{status}</b>\nInterval: <b>{html.escape(str(cfg.get('interval','10M')))}</b>\n"
           f"Saved messages: <b>{len(items)}</b>{err}")
    kb = btn([[ ("➕ Add Message", "auto_bc_bot_add") ],
              [("📋 Message List", "auto_bc_bot_list")],
              [("⏱ Set Interval", "auto_bc_bot_interval"), ("▶️ Start" if not cfg.get("enabled") else "⏸ Pause", "auto_bc_bot_toggle")],
              [("🔙 Back", "auto_bc_home")]])
    await edit_msg(bot, chat_id, message_id, msg, kb)

async def auto_bc_bot_list(bot, chat_id, message_id=0):
    s = load_json("settings.json")
    cfg = s.setdefault("auto_broadcast_bot", {})
    items = cfg.get("items", [])
    rows = [[(f"🗑 Delete Message #{i+1}", f"auto_bc_bot_delete_{i}")] for i in range(len(items))]
    rows.append([("🔙 Back", "auto_bc_bot_home")])
    desc = "\n".join(f"{i+1}. {html.escape(str(x.get('type','message')))}" for i,x in enumerate(items)) or "No messages saved."
    await edit_msg(bot, chat_id, message_id, "<b>BOT BROADCAST MESSAGES</b>\n\n" + desc, btn(rows))

async def auto_bc_worker(application):
    """Persistent per-channel broadcast scheduler.

    The schedule is stored after every attempt, so a process restart does not
    lose the channel list, message cursor, or next-send time.
    """
    print("[AUTO BROADCAST] Worker loop entered.")
    while True:
        try:
            s = load_json("settings.json")
            channels = auto_bc_channels(s)
            changed = False
            now = time.time()

            for channel_id in list(channels.keys()):
                # Reload before every channel: admin callbacks may have changed
                # settings while a previous Telegram API request was awaiting.
                s = load_json("settings.json")
                channels = auto_bc_channels(s)
                c = channels.get(channel_id)
                if c is None:
                    continue
                if not isinstance(c, dict):
                    c = {}
                    channels[channel_id] = c
                    changed = True

                items = c.get("items", [])
                if not c.get("enabled") or not items:
                    continue

                try:
                    interval = parse_broadcast_interval(c.get("interval", "10M"))
                    next_at = float(c.get("next_at", 0) or 0)
                except (TypeError, ValueError) as exc:
                    c["last_error"] = f"Invalid schedule: {exc}"
                    c["enabled"] = False
                    changed = True
                    print(f"[AUTO BROADCAST] Disabled invalid schedule for {channel_id}: {exc}")
                    continue

                if now < next_at:
                    continue

                idx = int(c.get("index", 0) or 0) % len(items)
                item = items[idx]
                c["last_attempt_at"] = time.time()
                sent_ok = False

                try:
                    source_chat_id = int(item["chat_id"])
                    source_message_id = int(item["message_id"])
                    target_chat_id = int(channel_id)

                    await asyncio.wait_for(
                        application.bot.copy_message(
                            chat_id=target_chat_id,
                            from_chat_id=source_chat_id,
                            message_id=source_message_id,
                        ),
                        timeout=35,
                    )

                    c["index"] = (idx + 1) % len(items)
                    c["next_at"] = time.time() + interval
                    c["last_error"] = ""
                    c["last_sent_at"] = time.time()
                    c["last_success_message"] = idx + 1
                    sent_ok = True
                    print(f"[AUTO BROADCAST] SUCCESS channel={channel_id} item={idx + 1}/{len(items)} next_in={interval}s")

                except RetryAfter as exc:
                    retry_seconds = float(getattr(exc, "retry_after", 60))
                    c["next_at"] = time.time() + max(60, retry_seconds + 2)
                    c["last_error"] = f"Telegram rate limit; retry in {int(retry_seconds)}s"
                    print(f"[AUTO BROADCAST] RATE_LIMIT channel={channel_id}: {exc}")

                except (TimedOut, NetworkError, asyncio.TimeoutError) as exc:
                    # Keep the same item and retry later; transient network
                    # problems must not permanently skip a scheduled message.
                    c["next_at"] = time.time() + 60
                    c["last_error"] = f"Temporary Telegram/network error: {type(exc).__name__}"
                    print(f"[AUTO BROADCAST] RETRY channel={channel_id}: {type(exc).__name__}: {exc}")

                except (Forbidden, BadRequest) as exc:
                    c["next_at"] = time.time() + 300
                    c["last_error"] = f"{type(exc).__name__}: {str(exc)[:220]}"
                    print(f"[AUTO BROADCAST] TELEGRAM_REJECTED channel={channel_id}: {exc}")

                except Exception as exc:
                    c["next_at"] = time.time() + 60
                    c["last_error"] = f"{type(exc).__name__}: {str(exc)[:220]}"
                    print(f"[AUTO BROADCAST] FAILED channel={channel_id}: {type(exc).__name__}: {exc}")

                # Merge scheduler fields into the latest file instead of
                # writing the stale snapshot loaded before copy_message().
                # This prevents the worker from erasing a newly-added channel,
                # message, interval change, or admin pause action.
                latest = load_json("settings.json")
                latest_channels = auto_bc_channels(latest)
                latest_c = latest_channels.get(channel_id)
                if latest_c is not None:
                    latest_items = latest_c.get("items", [])
                    if latest_items and sent_ok:
                        latest_c["index"] = (idx + 1) % len(latest_items)
                    elif latest_items:
                        latest_c["index"] = int(latest_c.get("index", 0) or 0) % len(latest_items)
                    for field in ("next_at", "last_error", "last_attempt_at",
                                  "last_sent_at", "last_success_message"):
                        if field in c:
                            latest_c[field] = c[field]
                    latest_channels[channel_id] = latest_c
                    latest["auto_broadcast_channels"] = latest_channels
                    save_json("settings.json", latest)
                changed = False

            if changed:
                s["auto_broadcast_channels"] = channels
                save_json("settings.json", s)

        except Exception as exc:
            print(f"[AUTO BROADCAST] WORKER LOOP ERROR: {type(exc).__name__}: {exc}")

        # Separate scheduled broadcast to users of this bot. Progress is
        # checkpointed so a restart resumes instead of restarting the batch.
        try:
            latest = load_json("settings.json")
            cfg = latest.setdefault("auto_broadcast_bot", {"enabled": False, "interval": "10M", "items": [], "index": 0, "next_at": 0, "user_cursor": 0})
            bot_items = cfg.get("items", [])
            if cfg.get("enabled") and bot_items and time.time() >= float(cfg.get("next_at", 0) or 0):
                users_map = load_json("users.json")
                user_ids = [x for x in users_map.keys() if str(x).lstrip("-").isdigit()]
                if user_ids:
                    bidx = int(cfg.get("index", 0) or 0) % len(bot_items)
                    item = bot_items[bidx]
                    cursor = max(0, int(cfg.get("user_cursor", 0) or 0))
                    sent_count = int(cfg.get("cycle_sent", 0) or 0)
                    failed_count = int(cfg.get("cycle_failed", 0) or 0)
                    while cursor < len(user_ids):
                        # Respect pause/delete/edit actions while a large user
                        # broadcast is in progress.
                        current_settings = load_json("settings.json")
                        current_cfg = current_settings.get("auto_broadcast_bot", {})
                        if not current_cfg.get("enabled"):
                            break
                        current_items = current_cfg.get("items", [])
                        if not current_items:
                            break
                        # If admin changed the message list during a cycle,
                        # restart that cycle cleanly with its current selection.
                        if bidx >= len(current_items):
                            bidx = 0
                            item = current_items[0]
                        uid = user_ids[cursor]
                        try:
                            await asyncio.wait_for(application.bot.copy_message(
                                chat_id=int(uid), from_chat_id=int(item["chat_id"]),
                                message_id=int(item["message_id"])), timeout=20)
                            sent_count += 1
                        except RetryAfter as exc:
                            await asyncio.sleep(max(1, float(getattr(exc, "retry_after", 5))))
                            try:
                                await application.bot.copy_message(chat_id=int(uid), from_chat_id=int(item["chat_id"]), message_id=int(item["message_id"]))
                                sent_count += 1
                            except Exception:
                                failed_count += 1
                        except (Forbidden, BadRequest):
                            failed_count += 1
                        except Exception:
                            failed_count += 1
                        cursor += 1
                        # Save only scheduler progress into the latest config;
                        # never overwrite concurrent admin changes.
                        current_settings = load_json("settings.json")
                        current_cfg = current_settings.setdefault("auto_broadcast_bot", {})
                        current_cfg["user_cursor"] = cursor
                        current_cfg["cycle_sent"] = sent_count
                        current_cfg["cycle_failed"] = failed_count
                        current_settings["auto_broadcast_bot"] = current_cfg
                        save_json("settings.json", current_settings)
                        await asyncio.sleep(0.05)
                    current_settings = load_json("settings.json")
                    current_cfg = current_settings.setdefault("auto_broadcast_bot", {})
                    if cursor >= len(user_ids):
                        current_items = current_cfg.get("items", [])
                        if current_items:
                            current_cfg["index"] = (bidx + 1) % len(current_items)
                        try:
                            next_interval = parse_broadcast_interval(current_cfg.get("interval", "10M"))
                        except ValueError:
                            next_interval = 600
                            current_cfg["last_error"] = "Invalid interval; using 10M."
                        current_cfg["next_at"] = time.time() + next_interval
                        current_cfg["last_sent_at"] = time.time()
                        current_cfg["last_report"] = {"sent": sent_count, "failed": failed_count, "total": len(user_ids)}
                        current_cfg["user_cursor"] = 0
                        current_cfg["cycle_sent"] = 0
                        current_cfg["cycle_failed"] = 0
                    current_settings["auto_broadcast_bot"] = current_cfg
                    save_json("settings.json", current_settings)
                else:
                    cfg["next_at"] = time.time() + 300
                    cfg["last_error"] = "No registered users found."
                    latest["auto_broadcast_bot"] = cfg
                    save_json("settings.json", latest)
        except Exception as exc:
            print(f"[BOT AUTO BROADCAST] ERROR: {type(exc).__name__}: {exc}")

        await asyncio.sleep(2)



async def callback_handler_refresh_list(bot, chat_id, message_id, channel_id):
    s = load_json("settings.json"); c = auto_bc_channels(s).get(str(channel_id), {})
    items = c.get("items", []); rows = []
    for i, item in enumerate(items):
        rows.append([(f"🗑 Delete #{i+1} ({item.get('type','message')})"[:60], f"auto_bc_delete_{channel_id}_{i}")])
    rows.append([("🔙 Back", f"auto_bc_open_{channel_id}")])
    desc = "\n".join(f"{i+1}. {html.escape(str(x.get('type','message')))}" for i, x in enumerate(items)) or "No messages added yet."
    await edit_msg(bot, chat_id, message_id, "<b>SAVED MESSAGES</b>\n\n" + desc, btn(rows))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    bot = context.bot
    chat_id = q.message.chat_id
    message_id = q.message.message_id
    user_id = q.from_user.id
    first_name = q.from_user.first_name or "User"
    data = q.data or ""
    if data == "start_menu_buttons_admin" or data.startswith("smb_"):
        if not is_admin(user_id):
            await q.answer("Admin only.", show_alert=True); return
        await q.answer()
        if data == "start_menu_buttons_admin":
            await start_menu_buttons_admin(bot, chat_id, message_id); return
        if data.startswith("smb_edit:"):
            await start_menu_button_editor(bot, chat_id, message_id, data.split(":", 1)[1]); return
        if data.startswith("smb_style:"):
            _, key, style = data.split(":", 2)
            if key in START_MENU_BUTTON_DEFAULTS and style in ("primary", "success", "danger"):
                st = load_json("settings.json")
                st.setdefault("start_menu_buttons", {}).setdefault(key, {})["style"] = style
                save_json("settings.json", st)
            await start_menu_button_editor(bot, chat_id, message_id, key); return
        if data.startswith("smb_name:"):
            key = data.split(":", 1)[1]
            if key in START_MENU_BUTTON_DEFAULTS:
                save_temp(user_id, "waiting", "start_menu_button_name")
                save_temp(user_id, "start_menu_button_key", key)
                await edit_msg(bot, chat_id, message_id, "<b>Send the new button name (max 64 characters).</b>", btn([[("❌ Cancel", "start_menu_buttons_admin")]]))
            return
    if data.startswith("auto_bc_") and not is_admin(user_id):
        await q.answer("Admin only.", show_alert=True)
        return
    if data.startswith("auto_bc_"):
        try:
            await q.answer()
        except Exception:
            pass
    if data == "auto_bc_home":
        await auto_bc_home(bot, chat_id, message_id)
        return
    if data == "auto_bc_bot_home":
        context.user_data.pop("auto_bc_waiting", None)
        save_temp(user_id, "waiting", "")
        await auto_bc_bot_home(bot, chat_id, message_id)
        return
    if data == "auto_bc_bot_add":
        save_temp(user_id, "waiting", "auto_bc_bot_add_message")
        context.user_data["auto_bc_waiting"] = "auto_bc_bot_add_message"
        await edit_msg(bot, chat_id, message_id, "<b>SEND BOT BROADCAST MESSAGE</b>\n\nSend text, photo, video, document, audio, voice or GIF. Telegram formatting and captions are copied as-is.", btn([[ ("Cancel", "auto_bc_bot_home") ]]))
        return
    if data == "auto_bc_bot_list":
        await auto_bc_bot_list(bot, chat_id, message_id)
        return
    if data == "auto_bc_bot_interval":
        save_temp(user_id, "waiting", "auto_bc_bot_interval")
        await edit_msg(bot, chat_id, message_id, "<b>SET BOT BROADCAST INTERVAL</b>\n\nExamples: 10M, 1H, 24H, 1D.", btn([[ ("Cancel", "auto_bc_bot_home") ]]))
        return
    if data == "auto_bc_bot_toggle":
        s = load_json("settings.json"); cfg = s.setdefault("auto_broadcast_bot", {"enabled": False, "interval": "10M", "items": [], "index": 0, "next_at": 0})
        if not cfg.get("enabled") and not cfg.get("items"):
            await send_message(bot, chat_id, "Add at least one bot broadcast message first."); return
        cfg["enabled"] = not bool(cfg.get("enabled"))
        if cfg["enabled"]: cfg["next_at"] = time.time()
        s["auto_broadcast_bot"] = cfg; save_json("settings.json", s)
        await auto_bc_bot_home(bot, chat_id, message_id); return
    if data.startswith("auto_bc_bot_delete_"):
        try:
            idx = int(data.rsplit("_", 1)[1])
            s = load_json("settings.json"); cfg = s.setdefault("auto_broadcast_bot", {}); items = cfg.get("items", [])
            if 0 <= idx < len(items): items.pop(idx)
            cfg["items"] = items; cfg["index"] = min(int(cfg.get("index", 0) or 0), max(0, len(items)-1))
            if not items: cfg["enabled"] = False; cfg["next_at"] = 0
            s["auto_broadcast_bot"] = cfg; save_json("settings.json", s)
        except Exception as exc:
            print(f"[BOT AUTO BROADCAST] Delete failed: {exc}")
        await auto_bc_bot_list(bot, chat_id, message_id); return
    if data == "auto_bc_channels":
        context.user_data.pop("auto_bc_waiting", None)
        save_temp(user_id, "waiting", "")
        s = load_json("settings.json")
        channels = auto_bc_channels(s)
        save_json("settings.json", s)
        rows = [[(f"{'🟢' if c.get('enabled') else '⚪'} {str(c.get('title') or cid)[:24]}", f"auto_bc_open_{cid}")] for cid, c in channels.items()]
        rows.append([("➕ Add Channel", "auto_bc_channel")])
        rows.append([("🔙 Back", "auto_bc_home")])
        await edit_msg(bot, chat_id, message_id, "<b>📡 MANAGE CHANNELS</b>\n\nSelect a channel to manage its messages and schedule.", btn(rows))
        return
    if data == "auto_bc_channel":
        # Keep the input state in both persistent temp.json and PTB user_data.
        # This prevents the channel-ID message from being ignored if another
        # handler or a stale temp record changes the persistent waiting value.
        save_temp(user_id, "waiting", "auto_bc_channel")
        context.user_data["auto_bc_waiting"] = "auto_bc_channel"
        await edit_msg(bot, chat_id, message_id,
            "<b>ADD CHANNEL — FORWARD METHOD</b>\n\n"
            "1. Open the target Telegram channel.\n"
            "2. Select any normal message posted in that channel.\n"
            "3. Tap <b>Forward</b> and send that message directly to this bot chat.\n\n"
            "<b>Important:</b> Forward it as a Telegram forward; do not copy/paste it. The channel must allow forwarding, and this bot must already be an administrator with <b>Post Messages</b> permission.\n\n"
            "I will identify the channel from the forwarded message and verify the bot permissions automatically. No Channel ID is needed.",
            btn([[ ("Cancel", "auto_bc_channels") ]]))
        return
    if data.startswith("auto_bc_open_"):
        context.user_data.pop("auto_bc_waiting", None)
        save_temp(user_id, "waiting", "")
        await auto_bc_channel_home(bot, chat_id, message_id, data[len("auto_bc_open_"):])
        return
    if data.startswith("auto_bc_add_"):
        channel_id = data[len("auto_bc_add_"):]
        save_temp(user_id, "waiting", "auto_bc_add_message")
        save_temp(user_id, "auto_bc_target", channel_id)
        await edit_msg(bot, chat_id, message_id,
            "<b>SEND MESSAGE TO ADD</b>\n\nSend text, photo, video, document, audio or another Telegram message. Formatting and captions are preserved.",
            btn([[ ("Cancel", f"auto_bc_open_{channel_id}") ]]))
        return
    if data.startswith("auto_bc_interval_"):
        channel_id = data[len("auto_bc_interval_"):]
        save_temp(user_id, "waiting", "auto_bc_interval")
        save_temp(user_id, "auto_bc_target", channel_id)
        await edit_msg(bot, chat_id, message_id,
            "<b>SET CHANNEL INTERVAL</b>\n\nExamples: <code>10S</code>, <code>10M</code>, <code>1H</code>, <code>24H</code>, <code>1D</code>, <code>2D</code>.",
            btn([[ ("Cancel", f"auto_bc_open_{channel_id}") ]]))
        return
    if data.startswith("auto_bc_toggle_"):
        channel_id = data[len("auto_bc_toggle_"):]
        s = load_json("settings.json"); channels = auto_bc_channels(s); c = channels.get(channel_id)
        if not c:
            await auto_bc_home(bot, chat_id, message_id); return
        if not c.get("enabled"):
            if not c.get("items"):
                await send_message(bot, chat_id, "Add at least one message to this channel first."); return
            c["next_at"] = time.time(); c["enabled"] = True
        else:
            c["enabled"] = False
        channels[channel_id] = c; s["auto_broadcast_channels"] = channels; save_json("settings.json", s)
        await auto_bc_channel_home(bot, chat_id, message_id, channel_id); return
    if data.startswith("auto_bc_list_"):
        channel_id = data[len("auto_bc_list_"):]
        s = load_json("settings.json"); c = auto_bc_channels(s).get(channel_id, {})
        items = c.get("items", [])
        rows = []
        for i, item in enumerate(items):
            label = f"🗑 Delete #{i+1} ({item.get('type','message')})"
            rows.append([(label[:60], f"auto_bc_delete_{channel_id}_{i}")])
        rows.append([("🔙 Back", f"auto_bc_open_{channel_id}")])
        desc = "\n".join(f"{i+1}. {html.escape(str(x.get('type','message')))}" for i, x in enumerate(items)) or "No messages added yet."
        await edit_msg(bot, chat_id, message_id, "<b>SAVED MESSAGES</b>\n\n" + desc + "\n\nTap a delete button to remove an individual message.", btn(rows)); return
    if data.startswith("auto_bc_delete_"):
        parts = data[len("auto_bc_delete_"):].rsplit("_", 1)
        if len(parts) == 2:
            channel_id, raw_index = parts
            s = load_json("settings.json"); channels = auto_bc_channels(s); c = channels.get(channel_id)
            try: index = int(raw_index)
            except ValueError: index = -1
            if c and 0 <= index < len(c.get("items", [])):
                c["items"].pop(index)
                c["index"] = min(int(c.get("index", 0) or 0), max(0, len(c["items"])-1))
                if not c["items"]: c["enabled"] = False; c["next_at"] = 0
                channels[channel_id] = c; s["auto_broadcast_channels"] = channels; save_json("settings.json", s)
        await callback_handler_refresh_list(bot, chat_id, message_id, channel_id)
        return
    if data.startswith("auto_bc_remove_"):
        channel_id = data[len("auto_bc_remove_"):]
        s = load_json("settings.json"); channels = auto_bc_channels(s)
        channels.pop(channel_id, None); s["auto_broadcast_channels"] = channels
        if s.get("auto_broadcast_selected_channel") == channel_id: s["auto_broadcast_selected_channel"] = ""
        save_json("settings.json", s)
        await auto_bc_home(bot, chat_id, message_id); return
    # Answer maintenance product callbacks BEFORE the normal callback acknowledgement.
    # Telegram callback queries can only be answered once; answering first without
    # show_alert would prevent the maintenance alert from being displayed.
    if data.startswith("buy_"):
        _pid = data[4:]
        _products = load_json("products.json")
        _product = _products.get(_pid)
        if _product and not _product.get("enabled", True):
            await q.answer("🛠️This Product Is Under Maintaince", show_alert=True)
            return
    elif data.startswith("plan_"):
        _parts = data.split("_")
        if len(_parts) == 3:
            _products = load_json("products.json")
            _product = _products.get(_parts[1])
            if _product and not _product.get("enabled", True):
                await q.answer("🛠️This Product Is Under Maintaince", show_alert=True)
                return

    try:
        await q.answer()
    except Exception:
        pass

    # Reseller system: plans, wallet purchase, manual admin controls and discount.
    if data == "upgrade_reseller":
        await show_reseller_upgrade(bot, chat_id, message_id, user_id)
        return
    if data == "reseller_login":
        await show_reseller_login(bot, chat_id, message_id, context)
        return
    if data.startswith("reseller_pad_"):
        state = context.user_data.get("reseller_login_state")
        if not isinstance(state, dict):
            await show_reseller_login(bot, chat_id, message_id, context)
            return
        action = data[len("reseller_pad_"):]
        if action == "cancel":
            context.user_data.pop("reseller_login_state", None)
            await edit_msg(bot, chat_id, message_id, "❌ <b>Reseller login cancelled.</b>", btn([[ ("Back To Menu", "back", "danger") ]]))
            return
        digits = str(state.get("digits", ""))
        if action == "del":
            digits = digits[:-1]
        elif action == "clear":
            digits = ""
        elif action == "ok":
            if not digits:
                await q.answer("Enter the numbers first.", show_alert=True)
                return
            if state.get("step") == "id":
                # Bind the reseller ID to the Telegram account currently interacting
                # with the bot. Never search other users' reseller IDs here.
                users = load_json("users.json")
                own_uid = str(user_id)
                own_row = users.get(own_uid, {})
                own_reseller = own_row.get("reseller", {}) if isinstance(own_row, dict) else {}
                if (not isinstance(own_reseller, dict)
                    or str(own_reseller.get("login_id", "")) != digits
                    or not own_reseller.get("active")
                    or not reseller_is_active(own_uid)):
                    state["digits"] = ""
                    context.user_data["reseller_login_state"] = state
                    await edit_msg(bot, chat_id, message_id, "❌ <b>Reseller ID not found or access expired for this Telegram account.</b>\n\nEnter your own numeric <b>Reseller ID</b> again.\n\n🔢 <b>Input:</b> <code>—</code>", reseller_dialpad_keyboard())
                    return
                match_uid = own_uid
                state["target_uid"] = own_uid
                state["step"] = "password"
                state["digits"] = ""
                context.user_data["reseller_login_state"] = state
                await edit_msg(bot, chat_id, message_id, "🔐 <b>Reseller Login</b>\n\nEnter your numeric <b>Password</b>. Input is masked.\n\n🔢 <b>Password:</b> <code>—</code>", reseller_dialpad_keyboard())
                return
            target_uid = str(state.get("target_uid", ""))
            users = load_json("users.json")
            row = users.get(target_uid, {})
            reseller = row.get("reseller", {}) if isinstance(row, dict) else {}
            try:
                salt = bytes.fromhex(str(reseller.get("password_salt", "")))
                supplied_hash = hashlib.pbkdf2_hmac("sha256", digits.encode(), salt, 160000).hex()
                valid = bool(salt) and hmac.compare_digest(supplied_hash, str(reseller.get("password_hash", "")))
            except Exception:
                valid = False
            if not valid or not reseller.get("active") or not reseller_is_active(target_uid):
                state["digits"] = ""
                context.user_data["reseller_login_state"] = state
                await edit_msg(bot, chat_id, message_id, "❌ <b>Incorrect password or expired reseller access.</b>\n\nTry again using the dial pad.\n\n🔢 <b>Password:</b> <code>—</code>", reseller_dialpad_keyboard())
                return
            # Credentials are account-bound: only the owner of this Telegram account can log in.
            if str(user_id) != target_uid:
                context.user_data.pop("reseller_login_state", None)
                await edit_msg(bot, chat_id, message_id, "❌ <b>This reseller login belongs to a different Telegram account.</b>", btn([[ ("Back To Menu", "back", "danger") ]]))
                return
            reseller["login_session_until"] = time.time() + 3600
            row["reseller"] = reseller
            users[target_uid] = row
            save_json("users.json", users)
            context.user_data.pop("reseller_login_state", None)
            await edit_msg(bot, chat_id, message_id, "✅ <b>Reseller Login Successful!</b>\n\n🔐 Your reseller session is active for <b>1 hour</b>.\n🎯 Current discount: <b>" + str(int(load_json("settings.json").get("reseller_discount_percent", 50))) + "%</b>.\n\nYou can shop using your discounted reseller prices while your reseller plan remains active.", btn([[ ("🛍️ Shop Products", "shop", "success") ], [("🔄 Login Again", "reseller_login", "primary")], [("Back To Menu", "back", "danger")]]))
            return
        elif action.isdigit() and len(action) == 1:
            if len(digits) >= 12:
                await q.answer("Maximum 12 digits.", show_alert=True)
                return
            digits += action
        else:
            return
        state["digits"] = digits
        context.user_data["reseller_login_state"] = state
        label = "•" * len(digits) if state.get("step") == "password" else (digits if digits else "—")
        field = "Password" if state.get("step") == "password" else "Reseller ID"
        await edit_msg(bot, chat_id, message_id, f"🔐 <b>Reseller Login</b>\n\nEnter your numeric <b>{field}</b> using the dial pad below.\n\n🔢 <b>{field}:</b> <code>{label}</code>", reseller_dialpad_keyboard())
        return
    if data == "reseller_settings" and is_admin(user_id):
        await show_reseller_settings(bot, chat_id, message_id)
        return
    if data == "reseller_list" and is_admin(user_id):
        await show_reseller_list(bot, chat_id, message_id)
        return
    if data == "reseller_toggle" and is_admin(user_id):
        s = load_json("settings.json")
        s["reseller_enabled"] = not s.get("reseller_enabled", True)
        save_json("settings.json", s)
        await show_reseller_settings(bot, chat_id, message_id)
        return
    if data == "reseller_add_plan" and is_admin(user_id):
        save_temp(user_id, "waiting", "reseller_plan_name")
        await edit_msg(bot, chat_id, message_id, "➕ <b>Add Reseller Plan</b>\n\nSend plan name. Example: 1 Month", btn([[ ("❌Cancel", "reseller_settings", "danger") ]]))
        return
    if data == "reseller_edit_plan" and is_admin(user_id):
        plans = load_json("settings.json").get("reseller_plans", [])
        rows = [[(f"✏️ {p.get('name')} — ₹{p.get('price')}", f"reseller_edit_{i}", "primary")] for i,p in enumerate(plans)]
        rows.append([("Back", "reseller_settings", "danger")])
        await edit_msg(bot, chat_id, message_id, "Choose a reseller plan to edit its price:", btn(rows))
        return
    if data.startswith("reseller_edit_") and is_admin(user_id):
        try: idx = int(data.rsplit("_",1)[1])
        except ValueError: return
        plans = load_json("settings.json").get("reseller_plans", [])
        if not 0 <= idx < len(plans): return
        save_temp(user_id, "waiting", "reseller_edit_price")
        save_temp(user_id, "reseller_plan_index", idx)
        await edit_msg(bot, chat_id, message_id, f"Send the new price for <b>{html.escape(str(plans[idx].get('name')))}</b> (₹):", btn([[ ("❌Cancel", "reseller_settings", "danger") ]]))
        return
    if data == "reseller_delete_plan" and is_admin(user_id):
        plans = load_json("settings.json").get("reseller_plans", [])
        rows = [[(f"🗑️ {p.get('name')} — ₹{p.get('price')}", f"reseller_del_{i}", "danger")] for i,p in enumerate(plans)]
        rows.append([("Back", "reseller_settings", "danger")])
        await edit_msg(bot, chat_id, message_id, "Choose a reseller plan to delete:", btn(rows))
        return
    if data.startswith("reseller_del_") and is_admin(user_id):
        try: idx = int(data.rsplit("_",1)[1])
        except ValueError: return
        s = load_json("settings.json"); plans = s.get("reseller_plans", [])
        if 0 <= idx < len(plans):
            removed = plans.pop(idx); s["reseller_plans"] = plans; save_json("settings.json", s)
            await edit_msg(bot, chat_id, message_id, f"✅ Deleted reseller plan: {html.escape(str(removed.get('name','Plan')))}", btn([[ ("⬅️ Reseller Settings", "reseller_settings", "primary") ]]))
        return
    if data == "reseller_add_user" and is_admin(user_id):
        save_temp(user_id, "waiting", "reseller_manual_add")
        await edit_msg(bot, chat_id, message_id, "Send the Telegram User ID to grant permanent reseller access:", btn([[ ("❌Cancel", "reseller_settings", "danger") ]]))
        return
    if data == "reseller_remove_user" and is_admin(user_id):
        save_temp(user_id, "waiting", "reseller_manual_remove")
        await edit_msg(bot, chat_id, message_id, "Send the Telegram User ID to remove reseller access:", btn([[ ("❌Cancel", "reseller_settings", "danger") ]]))
        return
    if data == "reseller_discount_set" and is_admin(user_id):
        save_temp(user_id, "waiting", "reseller_discount")
        await edit_msg(bot, chat_id, message_id, "Send reseller discount percentage (1–90). Example: 50", btn([[ ("❌Cancel", "reseller_settings", "danger") ]]))
        return
    if data.startswith("reseller_buy_"):
        try: idx = int(data.rsplit("_",1)[1])
        except ValueError: return
        s = load_json("settings.json"); plans = s.get("reseller_plans", [])
        if not s.get("reseller_enabled", True):
            await q.answer("Reseller upgrades are disabled.", show_alert=True); return
        if not 0 <= idx < len(plans):
            await q.answer("This plan is no longer available.", show_alert=True); return
        plan = plans[idx]
        try:
            price = round(float(plan.get("price", 0)), 2)
            days = int(plan.get("days", 0) or 0)
            seconds = days * 86400 if days > 0 else _duration_seconds(plan.get("name", ""))
            if seconds <= 0: raise ValueError("invalid duration")
        except (ValueError, TypeError):
            await q.answer("Admin has configured an invalid plan duration.", show_alert=True); return
        balances = load_json("balances.json"); bal = round(float(balances.get(str(user_id), 0) or 0), 2)
        if price <= 0:
            await q.answer("This plan has an invalid price.", show_alert=True); return
        if bal < price:
            await edit_msg(bot, chat_id, message_id, f"❌ <b>Insufficient Balance</b>\n\nPlan: {html.escape(str(plan.get('name')))}\nPrice: ₹{price:.2f}\nYour Balance: ₹{bal:.2f}", btn([[ ("💰 Add Balance", "addbal", "success") ], [ ("Back", "upgrade_reseller", "danger") ]]))
            return
        balances[str(user_id)] = round(bal-price, 2); save_json("balances.json", balances)
        users = load_json("users.json"); u = users.setdefault(str(user_id), {})
        old = u.get("reseller", {})
        start_from = max(time.time(), float(old.get("active_until", 0) or 0)) if old.get("active") and old.get("active_until") != "permanent" else time.time()
        if old.get("active_until") == "permanent" and old.get("active"):
            active_until = "permanent"
        else:
            active_until = start_from + seconds
        # Generate numeric credentials once per user; keep the password hashed at rest.
        reseller_id = str(old.get("login_id") or random.randint(10000000, 99999999))
        password = str(random.randint(100000, 999999999))
        salt = os.urandom(16).hex()
        password_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 160000).hex()
        u["reseller"] = {"active": True, "active_until": active_until, "plan": str(plan.get("name")), "login_id": reseller_id, "password_salt": salt, "password_hash": password_hash}
        users[str(user_id)] = u; save_json("users.json", users)
        expiry_text = "Permanent" if active_until == "permanent" else datetime.fromtimestamp(active_until, IST).strftime("%d %b %Y %H:%M")
        success_markup = InlineKeyboardMarkup([
            [start_menu_button("reseller", url=RESELLER_BOT_LINK)],
            [InlineKeyboardButton("Shop Products", callback_data="shop", style="primary")],
            [InlineKeyboardButton("Back To Menu", callback_data="back", style="danger")],
        ])
        await edit_msg(bot, chat_id, message_id, f"✅ <b>Reseller Upgrade Successful!</b>\n\n📅 Plan: <b>{html.escape(str(plan.get('name')))}</b>\n💰 Paid: <b>₹{price:.2f}</b>\n💳 Remaining Balance: <b>₹{balances[str(user_id)]:.2f}</b>\n🎯 Product Discount: <b>{int(s.get('reseller_discount_percent',50))}%</b>\n🆔 Reseller ID: <code>{reseller_id}</code>\n🔑 Numeric Password: <code>{password}</code>\n📅 Expires: <b>{html.escape(expiry_text)}</b>\n\nKeep your login details private.", success_markup)
        try:
            await send_message(bot, int(ADMIN_ID), f"💎 <b>Reseller Plan Purchased</b>\nUser ID: <code>{user_id}</code>\nName: {html.escape(str(u.get('name','User')))}\nPlan: {html.escape(str(plan.get('name')))}\nPaid: ₹{price:.2f}")
        except Exception: pass
        return

    # When the bot is OFF, normal users only see maintenance mode.
    # Admin can still use the Admin Panel.
    if not is_admin(user_id) and not load_json("settings.json").get("bot_enabled", True):
        settings = load_json("settings.json")
        maintenance_text = settings.get("maintenance_message") or DEFAULT_SETTINGS["maintenance_message"]
        await edit_msg(bot, chat_id, message_id, maintenance_text, None)
        return

    # Forgot password: first ask the user to start the separate OTP bot.
    # OTP is only generated/sent after the user presses NEXT.
    if data == "orders_pin_forgot":
        if not OTP_BOT_TOKEN or OTP_BOT_TOKEN == "PASTE_OTP_BOT_TOKEN_HERE":
            await edit_msg(bot, chat_id, message_id,
                "⚠️ <b>Password reset is temporarily unavailable.</b> Please try again later.",
                btn([[ ("Back", "back", "danger") ]]))
            return
        temp_all = load_json("temp.json")
        session = temp_all.setdefault(str(user_id), {})
        for key in ("orders_pin_otp_hash", "orders_pin_otp_expires", "orders_pin_otp_attempts", "orders_pin_reset_ready_expires"):
            session.pop(key, None)
        session["waiting"] = "orders_pin_otp_pending"
        session["orders_pin_target"] = session.get("orders_pin_target", "orders")
        temp_all[str(user_id)] = session
        save_json("temp.json", temp_all)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 START OTP BOT", url="https://t.me/TbOTPCaptchaBot", style="primary")],
            [InlineKeyboardButton("➡️ NEXT", callback_data="orders_pin_otp_next", style="success")],
            [InlineKeyboardButton("❌Cancel", callback_data="orders_pin_otp_cancel", style="danger")],
        ])
        await edit_msg(bot, chat_id, message_id,
            "🔐 <b>FORGOT PASSWORD</b>\n\n"
            "To reset your password, you must first start our OTP Bot.\n\n"
            "<b>1.</b> Click <b>START OTP BOT</b> below.\n"
            "<b>2.</b> Press <b>START</b> in the OTP Bot.\n"
            "<b>3.</b> Return here and click <b>NEXT</b>.\n\n"
            "⚠️ <b>You must start the OTP Bot before continuing.</b>", keyboard)
        return

    if data == "orders_pin_otp_next":
        temp_all = load_json("temp.json")
        session = temp_all.get(str(user_id), {})
        if session.get("waiting") != "orders_pin_otp_pending":
            await q.answer("Please tap Forgot Password first.", show_alert=True)
            return
        if not OTP_BOT_TOKEN or OTP_BOT_TOKEN == "PASTE_OTP_BOT_TOKEN_HERE":
            await q.answer("OTP service is not configured yet.", show_alert=True)
            return
        otp = f"{random.randint(0, 999999):06d}"
        try:
            async with Bot(token=OTP_BOT_TOKEN) as otp_bot:
                await otp_bot.send_message(
                    chat_id=int(user_id),
                    text=("🔐 PASSWORD RESET OTP\n\n"
                          f"Your OTP is: {otp}\n"
                          "This code expires in 5 minutes and can be used only once.\n"
                          "If you did not request this, ignore this message.")
                )
        except (Forbidden, BadRequest):
            await q.answer("OTP BOT NOT STARTED! Open @TbOTPCaptchaBot and press START, then tap NEXT again.", show_alert=True)
            return
        except Exception:
            await q.answer("Could not contact the OTP Bot. Please start @TbOTPCaptchaBot and try again.", show_alert=True)
            return

        session["waiting"] = "orders_pin_otp"
        session["orders_pin_otp_hash"] = hashlib.sha256((str(user_id) + ":" + otp).encode()).hexdigest()
        session["orders_pin_otp_expires"] = time.time() + 300
        session["orders_pin_otp_attempts"] = 0
        temp_all[str(user_id)] = session
        save_json("temp.json", temp_all)
        context.user_data["orders_pin_otp_digits"] = ""
        await edit_msg(bot, chat_id, message_id,
            "🔐 <b>PLEASE ENTER YOUR OTP</b>\n\n"
            "The 6-digit OTP was sent by our OTP Bot.\n"
            "⏳ <b>Validity:</b> 5 minutes\n\n"
            "🔢 <b>OTP:</b> <code>—</code>",
            _otp_keyboard(""))
        return

    if data.startswith("orders_pin_otp_digit_"):
        session = load_json("temp.json").get(str(user_id), {})
        if session.get("waiting") != "orders_pin_otp":
            await q.answer("Request an OTP first.", show_alert=True)
            return
        digit = data.rsplit("_", 1)[-1]
        if digit not in "0123456789" or len(digit) != 1:
            return
        digits = str(context.user_data.get("orders_pin_otp_digits", ""))
        if len(digits) < 6:
            digits += digit
        context.user_data["orders_pin_otp_digits"] = digits
        await edit_msg(bot, chat_id, message_id,
            "🔐 <b>Please enter your OTP.</b>\\n\\n"
            "🔢 <b>OTP:</b> <code>" + ("•" * len(digits) if digits else "—") + "</code>",
            _otp_keyboard(digits))
        return

    if data in ("orders_pin_otp_del", "orders_pin_otp_clear"):
        session = load_json("temp.json").get(str(user_id), {})
        if session.get("waiting") != "orders_pin_otp":
            await q.answer("Request an OTP first.", show_alert=True)
            return
        digits = str(context.user_data.get("orders_pin_otp_digits", ""))
        digits = digits[:-1] if data == "orders_pin_otp_del" else ""
        context.user_data["orders_pin_otp_digits"] = digits
        await edit_msg(bot, chat_id, message_id,
            "🔐 <b>Please enter your OTP.</b>\\n\\n"
            "🔢 <b>OTP:</b> <code>" + ("•" * len(digits) if digits else "—") + "</code>",
            _otp_keyboard(digits))
        return

    if data == "orders_pin_otp_verify":
        temp_all = load_json("temp.json")
        session = temp_all.get(str(user_id), {})
        if session.get("waiting") != "orders_pin_otp":
            await q.answer("Request a new OTP first.", show_alert=True)
            return
        digits = str(context.user_data.get("orders_pin_otp_digits", ""))
        if time.time() > float(session.get("orders_pin_otp_expires", 0)):
            for key in ("orders_pin_otp_hash", "orders_pin_otp_expires", "orders_pin_otp_attempts"):
                session.pop(key, None)
            session["waiting"] = ""
            temp_all[str(user_id)] = session
            save_json("temp.json", temp_all)
            context.user_data.pop("orders_pin_otp_digits", None)
            await edit_msg(bot, chat_id, message_id,
                "⌛ <b>OTP expired.</b> Please tap Forgot Password and request a new code.",
                btn([[("Back", "back", "danger")]]))
            return
        expected = hashlib.sha256((str(user_id) + ":" + digits).encode()).hexdigest()
        if len(digits) != 6 or not hmac.compare_digest(expected, str(session.get("orders_pin_otp_hash", ""))):
            attempts = int(session.get("orders_pin_otp_attempts", 0)) + 1
            session["orders_pin_otp_attempts"] = attempts
            if attempts >= 5:
                for key in ("orders_pin_otp_hash", "orders_pin_otp_expires", "orders_pin_otp_attempts"):
                    session.pop(key, None)
                session["waiting"] = ""
                notice = "❌ <b>Too many incorrect attempts.</b> Please request a new OTP."
                keyboard = btn([[("Back", "back", "danger")]])
            else:
                notice = f"❌ <b>Incorrect OTP.</b> Attempts remaining: <b>{5-attempts}</b>."
                keyboard = _otp_keyboard("")
            temp_all[str(user_id)] = session
            save_json("temp.json", temp_all)
            context.user_data["orders_pin_otp_digits"] = ""
            await edit_msg(bot, chat_id, message_id, notice + ("\\n\\n🔐 <b>Please enter your OTP.</b>" if attempts < 5 else ""), keyboard)
            return

        # OTP is valid. Do not reset/open the password form automatically.
        # Keep the existing password unchanged until the user explicitly taps RESET PASSWORD.
        for key in ("orders_pin_otp_hash", "orders_pin_otp_expires", "orders_pin_otp_attempts"):
            session.pop(key, None)
        session["waiting"] = "orders_pin_reset_ready"
        session.pop("orders_pin_reset_ready_expires", None)  # no expiry; pending until password is set
        temp_all[str(user_id)] = session
        save_json("temp.json", temp_all)
        context.user_data.pop("orders_pin_otp_digits", None)
        success_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔐 RESET PASSWORD", callback_data="orders_pin_reset_after_otp", style="success")],
            [InlineKeyboardButton("Back To Menu", callback_data="back", style="danger")],
        ])
        await edit_msg(
            bot, chat_id, message_id,
            "✅ <b>OTP VERIFICATION SUCCESSFUL!</b>\n\n"
            "Your identity has been verified successfully.\n"
            "Your current password has not been changed yet.\n\n"
            "To choose a new password, tap <b>RESET PASSWORD</b> below.",
            success_keyboard,
        )
        return

    if data == "orders_pin_reset_after_otp":
        # OTP was already verified in the immediately preceding step. Do not
        # ask for OTP again when the user presses RESET PASSWORD.
        temp_all = load_json("temp.json")
        session = temp_all.get(str(user_id), {})
        if session.get("waiting") != "orders_pin_reset_ready":
            await q.answer("Please complete OTP verification first.", show_alert=True)
            return
        # OTP is already verified. The RESET PASSWORD button now opens the
        # exact same numeric PIN setup flow used by first-time users.
        target = session.get("orders_pin_target", "orders")
        session.pop("orders_pin_reset_ready_expires", None)  # remove legacy expiry field
        session["waiting"] = ""
        temp_all[str(user_id)] = session
        save_json("temp.json", temp_all)

        users = load_json("users.json")
        account = users.setdefault(str(user_id), {})
        account.pop("orders_pin_hash", None)
        account.pop("orders_pin_salt", None)
        users[str(user_id)] = account
        save_json("users.json", users)

        _clear_orders_pin_state(user_id)
        context.user_data.pop("orders_pin_digits", None)
        _orders_pin_state(user_id, mode="setup", orders_pin_target=target)
        await _show_orders_pin(bot, chat_id, message_id, user_id, "setup", context.user_data,
            "✅ <b>OTP VERIFICATION SUCCESSFUL!</b> Your identity is verified. Set your new password below.")
        return

    if data == "orders_pin_otp_cancel":
        temp_all = load_json("temp.json")
        session = temp_all.setdefault(str(user_id), {})
        for key in ("orders_pin_otp_hash", "orders_pin_otp_expires", "orders_pin_otp_attempts"):
            session.pop(key, None)
        session["waiting"] = ""
        temp_all[str(user_id)] = session
        save_json("temp.json", temp_all)
        context.user_data.pop("orders_pin_otp_digits", None)
        await edit_msg(bot, chat_id, message_id, "❌ <b>Password reset cancelled.</b>",
                       btn([[("Back To Menu", "back", "danger")]]))
        return

    if data == "password_users" and is_admin(user_id):
        users = load_json("users.json")
        rows = []
        for uid, u in list(users.items())[:100]:
            name = html.escape(str(u.get("name", "User")))
            uname = str(u.get("username", "") or "").strip().lstrip("@")
            uname_text = f"@{html.escape(uname)}" if uname else "No username"
            status = "✅ Password set" if u.get("orders_pin_hash") and u.get("orders_pin_salt") else "⚠️ Not set"
            rows.append(f"• <b>{name}</b> — {uname_text} — ID: <code>{html.escape(str(uid))}</code> — {status}")
        body = "🔐 <b>USER PASSWORD STATUS</b>\n\n" + ("\n".join(rows) if rows else "No users found.")
        body += "\n\n🔒 Passwords are stored as secure hashes, so the original PIN cannot be displayed. Accepting a Forgot Password request removes the old PIN; the user then sets a new one. Reject leaves it unchanged."
        # Send all user records in Telegram-safe chunks instead of silently truncating the list.
        chunks = []
        while len(body) > 3500:
            cut = body.rfind("\n", 0, 3500)
            if cut < 1:
                cut = 3500
            chunks.append(body[:cut])
            body = body[cut:].lstrip("\n")
        chunks.append(body)
        await edit_msg(bot, chat_id, message_id, chunks[0], btn([[ ("⬅️ Admin Panel", "backadmin", "danger") ]]))
        for part in chunks[1:]:
            await send_message(bot, chat_id, part)
        return

    # My Orders numeric password / keypad flow. The PIN is hashed, never stored in plain text.
    if data == "orders_pin_set":
        temp = get_temp(user_id)
        target = temp.get("orders_pin_target", "orders")
        _orders_pin_state(user_id, orders_pin_target=target)
        await _show_orders_pin(bot, chat_id, message_id, user_id, "setup", context.user_data)
        return
    if data == "orders_pin_enter":
        users = load_json("users.json")
        user = users.get(str(user_id), {})
        if user.get("orders_pin_hash") and user.get("orders_pin_salt"):
            temp = get_temp(user_id)
            target = temp.get("orders_pin_target", "orders")
            _orders_pin_state(user_id, orders_pin_target=target)
            await _show_orders_pin(bot, chat_id, message_id, user_id, "login", context.user_data)
        else:
            await edit_msg(bot, chat_id, message_id, "🔐 <b>You haven't set a Profile & My Orders password yet.</b>", btn([[ ("🔐 Set Password", "orders_pin_set", "success") ], [ ("Back To Menu", "back", "danger") ]]))
        return
    if data.startswith("orders_pin_digit_"):
        temp = get_temp(user_id)
        if temp.get("waiting") != "orders_pin":
            await q.answer("Open My Orders first.", show_alert=True)
            return
        digit = data.rsplit("_", 1)[1]
        if digit not in "0123456789" or len(digit) != 1:
            return
        digits = str(context.user_data.get("orders_pin_digits", ""))
        if len(digits) < 12:
            digits += digit
        context.user_data["orders_pin_digits"] = digits
        _orders_pin_state(user_id)
        mode = temp.get("orders_pin_mode", "login")
        _, keyboard = _orders_pin_keyboard(user_id, digits, mode)
        labels = {"setup": "🔐 <b>Set Profile & Orders Password</b>\n\nCreate a numeric PIN with 4–12 digits.", "confirm": "🔐 <b>Confirm Your Password</b>\n\nEnter the same 4–12 digit PIN again.", "login": "🔒 <b>Profile & Orders — Password Required</b>\n\nEnter your numeric PIN to continue."}
        shown = "•" * len(digits) if digits else "—"
        await edit_msg(bot, chat_id, message_id, labels.get(mode, labels["login"]) + f"\n\n🔢 <b>PIN:</b> <code>{shown}</code>", keyboard)
        return
    if data in ("orders_pin_del", "orders_pin_clear"):
        temp = get_temp(user_id)
        if temp.get("waiting") != "orders_pin":
            await q.answer("Open My Orders first.", show_alert=True)
            return
        digits = str(context.user_data.get("orders_pin_digits", ""))
        digits = digits[:-1] if data == "orders_pin_del" else ""
        context.user_data["orders_pin_digits"] = digits
        _orders_pin_state(user_id)
        mode = temp.get("orders_pin_mode", "login")
        labels = {"setup": "🔐 <b>Set Profile & Orders Password</b>\n\nCreate a numeric PIN with 4–12 digits.", "confirm": "🔐 <b>Confirm Your Password</b>\n\nEnter the same 4–12 digit PIN again.", "login": "🔒 <b>Profile & Orders — Password Required</b>\n\nEnter your numeric PIN to continue."}
        _, keyboard = _orders_pin_keyboard(user_id, digits, mode)
        shown = "•" * len(digits) if digits else "—"
        await edit_msg(bot, chat_id, message_id, labels.get(mode, labels["login"]) + f"\n\n🔢 <b>PIN:</b> <code>{shown}</code>", keyboard)
        return
    if data == "orders_pin_submit":
        temp = get_temp(user_id)
        if temp.get("waiting") != "orders_pin":
            await q.answer("Open My Orders first.", show_alert=True)
            return
        mode = temp.get("orders_pin_mode", "login")
        digits = str(context.user_data.get("orders_pin_digits", ""))
        if mode in ("setup", "confirm") and not (4 <= len(digits) <= 12):
            await _show_orders_pin(bot, chat_id, message_id, user_id, mode, context.user_data, "❌ PIN must contain 4–12 digits.")
            return
        if mode == "setup":
            salt, digest = _orders_pin_hash(digits)
            _orders_pin_state(user_id, mode="confirm", digits="", orders_pin_pending_salt=salt, orders_pin_pending_hash=digest)
            context.user_data["orders_pin_digits"] = ""
            _, keyboard = _orders_pin_keyboard(user_id, "", "confirm")
            await edit_msg(bot, chat_id, message_id, "🔐 <b>Confirm Your Password</b>\n\nEnter the same 4–12 digit PIN again.\n\n🔢 <b>PIN:</b> <code>—</code>", keyboard)
            return
        if mode == "confirm":
            salt = temp.get("orders_pin_pending_salt", "")
            digest = temp.get("orders_pin_pending_hash", "")
            if not salt or not _orders_pin_matches(digits, salt, digest):
                _orders_pin_state(user_id, mode="confirm", digits="")
                context.user_data["orders_pin_digits"] = ""
                _, keyboard = _orders_pin_keyboard(user_id, "", "confirm")
                await edit_msg(bot, chat_id, message_id, "❌ <b>PINs do not match.</b>\n\nPlease enter your new PIN again.\n\n🔢 <b>PIN:</b> <code>—</code>", keyboard)
                return
            users = load_json("users.json")
            user = users.setdefault(str(user_id), {})
            user["orders_pin_salt"] = salt
            user["orders_pin_hash"] = digest
            users[str(user_id)] = user
            save_json("users.json", users)
            target = temp.get("orders_pin_target", "orders")
            _clear_orders_pin_state(user_id)
            _orders_pin_state(user_id, orders_pin_target=target)
            context.user_data.pop("orders_pin_digits", None)
            await edit_msg(bot, chat_id, message_id, "✅ <b>Profile & My Orders password set successfully!</b>\n\nTap <b>Enter Password</b> and enter your PIN to open the selected section.", btn([
                [("🔒 Enter Password", "orders_pin_enter", "success")],
                [("Back To Menu", "back", "danger")],
            ]))
            return
        if mode == "login":
            users = load_json("users.json")
            user = users.get(str(user_id), {})
            if _orders_pin_matches(digits, user.get("orders_pin_salt", ""), user.get("orders_pin_hash", "")):
                target = temp.get("orders_pin_target", "orders")
                temp_all = load_json("temp.json")
                session = temp_all.setdefault(str(user_id), {})
                session["orders_pin_unlocked_until"] = time.time() + 3600
                temp_all[str(user_id)] = session
                save_json("temp.json", temp_all)
                _clear_orders_pin_state(user_id)
                context.user_data.pop("orders_pin_digits", None)
                if target == "profile":
                    await send_profile(bot, chat_id, message_id, user_id)
                else:
                    await _render_orders_after_pin(bot, chat_id, message_id, user_id)
            else:
                _orders_pin_state(user_id, mode="login", digits="")
                context.user_data["orders_pin_digits"] = ""
                _, keyboard = _orders_pin_keyboard(user_id, "", "login")
                await edit_msg(bot, chat_id, message_id, "❌ <b>Incorrect password.</b>\n\nTry again using the keypad below.\n\n🔢 <b>PIN:</b> <code>—</code>", keyboard)
            return
    if data == "orders_pin_cancel":
        _clear_orders_pin_state(user_id)
        context.user_data.pop("orders_pin_digits", None)
        await edit_msg(bot, chat_id, message_id, "❌ <b>My Orders password action cancelled.</b>", btn([[ ("Back To Menu", "back", "danger") ]]))
        return

    # Coupon: Skip Expiry (creates a coupon with no expiry date)
    if data == "coupon_skip_expiry" and is_admin(user_id):
        temp_all = load_json("temp.json")
        temp = temp_all.get(str(user_id), {})
        if temp.get("waiting") != "coupon_expiry":
            return
        coupons = load_json("coupons.json")
        code = str(temp.get("coupon_code", "")).strip().upper()
        if not code:
            await send_message(context.bot, chat_id, "❌ Coupon code is missing. Please start again.")
            return
        existing = coupons.get(code)
        if existing:
            claims = existing.get("claims", []) or []
            try:
                max_claims = int(existing.get("max_claims", 0))
            except Exception:
                max_claims = 0
            if len(claims) < max_claims:
                await send_message(context.bot, chat_id, "❌ This coupon code is already active and has not reached its claim limit.")
                return
        coupons[code] = {
            "amount": temp["coupon_amount"],
            "max_claims": temp["coupon_max_claims"],
            "expires": "",
            "claims": [],
            "created": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        save_json("coupons.json", coupons)
        for k in ("waiting", "coupon_code", "coupon_amount", "coupon_max_claims"):
            temp[k] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(
            context.bot, chat_id,
            f"✅ <b>Coupon Created!</b>\n\n🎟️ Code: <code>{html.escape(code)}</code>\n💰 ₹{float(coupons[code]['amount']):.2f}\n👥 Max Claims: {coupons[code]['max_claims']}\n📅 Expires: <b>No Expiry</b>"
        )
        await send_admin_panel(context.bot, chat_id)
        return

    # Play And Earn game callbacks
    if data == "play_earn_menu":
        await edit_msg(bot, chat_id, message_id, "🚀 <b>PLAY AND EARN</b>\n\nChoose a game:", play_earn_keyboard())
        return
    if data == "daily_task":
        await show_daily_task(bot, chat_id, message_id, user_id)
        return
    if data.startswith("daily_task_accept_"):
        await accept_daily_task(bot, chat_id, message_id, user_id, data.rsplit("_", 1)[1])
        return
    if data.startswith("daily_task_play_"):
        await edit_msg(bot, chat_id, message_id, "🚀 <b>PLAY AND EARN</b>\n\nChoose a game to progress your accepted Daily Task(s):", play_earn_keyboard())
        return
    if data == "game_leaderboard":
        if not is_admin(user_id):
            await q.answer("⛔ Admin only.", show_alert=True)
            return
        await edit_msg(bot, chat_id, message_id, leaderboard_text(), btn([[ ("🔄 Refresh", "game_leaderboard") ], [ ("Back to Game Controls", "game_controls") ]]))
        return
    if data == "rps_start":
        await rps_start(bot, chat_id, message_id, user_id)
        return
    if data.startswith(f"rps_pick_{user_id}_"):
        choice = data.rsplit("_", 1)[1]
        await rps_play(bot, chat_id, message_id, user_id, choice)
        return
    if data.startswith("rps_pick_"):
        await q.answer("This game belongs to another user.", show_alert=True)
        return
    if data == "tt_start":
        await tt_start(bot, chat_id, message_id, user_id)
        return
    if data.startswith(f"tt_move_{user_id}_"):
        try:
            index = int(data.rsplit("_", 1)[1])
        except (ValueError, IndexError):
            return
        await tt_move(bot, chat_id, message_id, user_id, index)
        return
    if data.startswith("tt_move_"):
        await q.answer("This game belongs to another user.", show_alert=True)
        return

    # User buttons
    if data == "claim_coupon":
        temp_all = load_json("temp.json"); temp = temp_all.get(str(user_id), {}); temp["waiting"] = "claim_coupon"; temp_all[str(user_id)] = temp; save_json("temp.json", temp_all)
        await show_claim_coupon(bot, chat_id, message_id)
    elif data == "lucky_spin":
        await do_lucky_spin(bot, chat_id, user_id, message_id)
    elif data == "addbal":
        await send_add_balance(bot, chat_id, message_id, user_id)
    elif data == "referral":
        await send_referral(bot, chat_id, message_id, user_id)
    elif data == "mykeys":
        await send_my_keys(bot, chat_id, message_id, user_id)
    elif data == "profile":
        await send_profile_protected(bot, chat_id, message_id, user_id, context.user_data)
    elif data == "orders":
        await send_orders(bot, chat_id, message_id, user_id, context.user_data)
    elif data == "shop":
        await send_categories(bot, chat_id, message_id, first_name)
    elif data == "proof":
        await send_proof(bot, chat_id, message_id)
    elif data == "howto":
        await send_howto(bot, chat_id, message_id)
    elif data == "support":
        await send_support(bot, chat_id, message_id)
    elif data == "whatsapp_support":
        cfg = load_json("settings.json")
        wa = str(cfg.get("whatsapp_support_link", "")).strip()
        if wa.startswith(("https://wa.me/", "https://api.whatsapp.com/")) and " " not in wa:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 Open WhatsApp", url=wa, style="success")],
                [InlineKeyboardButton("🎫 Tickets", callback_data="tickets_menu", style="primary")],
                [InlineKeyboardButton("Back", callback_data="support", style="danger")],
            ])
            await edit_msg(bot, chat_id, message_id, "🟢 <b>WhatsApp Support</b>\n\nTap below to contact support.", markup)
        else:
            await edit_msg(bot, chat_id, message_id, "🟢 <b>WhatsApp Support</b>\n\nWhatsApp support link is not configured yet. Please use Tickets for help.", btn([[ ("🎫 Tickets", "tickets_menu", "primary")], [("Back", "support", "danger")]]))
    elif data == "tickets_menu":
        await show_tickets_menu(bot, chat_id, message_id)
    elif data == "ticket_new":
        await open_new_ticket(bot, chat_id, user_id)
    elif data == "ticket_cancel":
        save_temp(user_id, "waiting", "")
        await edit_msg(bot, chat_id, message_id, "Ticket creation cancelled.", btn([[ ("Back To Menu", "back", "danger")]]))
    elif data == "ticket_mine":
        await show_my_tickets(bot, chat_id, user_id)
    elif data.startswith("ticket_view_"):
        tid = data[len("ticket_view_"):]
        ticket = load_json("tickets.json").get(tid)
        if not ticket or str(ticket.get("user_id")) != str(user_id):
            await q.answer("Ticket not found.", show_alert=True)
        else:
            await edit_msg(bot, chat_id, message_id, f"🎫 <b>Ticket #{html.escape(tid)}</b>\nStatus: <b>{html.escape(ticket.get('status','open'))}</b>\n\n<b>Your issue:</b>\n{html.escape(str(ticket.get('issue','')))}\n\n<b>Admin reply:</b>\n{html.escape(str(ticket.get('reply','No reply yet')))}", btn([[ ("📋 My Tickets", "ticket_mine", "primary")], [("Back", "tickets_menu", "danger")]]))
    elif data.startswith("ticket_reply_") and is_admin(user_id):
        tid = data[len("ticket_reply_"):]
        ticket = load_json("tickets.json").get(tid)
        if not ticket:
            await q.answer("Ticket not found.", show_alert=True)
        else:
            context.user_data["ticket_reply_id"] = tid
            await send_message(bot, chat_id, f"✍️ <b>Reply to Ticket #{html.escape(tid)}</b>\nSend the reply text now. It will go only to this ticket's user.", btn([[ ("❌Cancel", "ticket_reply_cancel", "danger")]]))
    elif data == "ticket_reply_cancel" and is_admin(user_id):
        context.user_data.pop("ticket_reply_id", None)
        await send_message(bot, chat_id, "Ticket reply cancelled.")
    elif data == "ticket_admin_list" and is_admin(user_id):
        tickets = load_json("tickets.json")
        rows = []
        lines = ["📋 <b>SUPPORT TICKETS</b>"]
        for tid, ticket in sorted(tickets.items(), key=lambda pair: pair[1].get("created", 0), reverse=True)[:20]:
            lines.append(f"\n<b>#{html.escape(tid)}</b> — {html.escape(str(ticket.get('name','User')))} — {html.escape(str(ticket.get('status','open')))}")
            rows.append([(f"Reply #{tid}", f"ticket_reply_{tid}", "success")])
        rows.append([("Back", "backadmin", "danger")])
        await edit_msg(bot, chat_id, message_id, "\n".join(lines), btn(rows))
    elif data == "noop":
        pass

    elif data.startswith("cat_"):
        await send_products(bot, chat_id, message_id, data[4:], first_name)
    elif data == "products_toggle" and is_admin(user_id):
        await product_status_picker(bot, chat_id, message_id)
    elif data == "product_links" and is_admin(user_id):
        await product_links_picker(bot, chat_id, message_id)
    elif data.startswith("productlink_") and is_admin(user_id):
        await show_product_link(bot, chat_id, message_id, data[len("productlink_"):])
    elif data.startswith("toggleprod_") and is_admin(user_id):
        pid = data[len("toggleprod_"):]
        products = load_json("products.json")
        if pid not in products:
            await edit_msg(
                bot, chat_id, message_id,
                "❌ <b>Product not found!</b>",
                btn([[("Back", "backadmin")]])
            )
            return
        products[pid]["enabled"] = not products[pid].get("enabled", True)
        save_json("products.json", products)
        await product_status_picker(bot, chat_id, message_id)

    # Product maintenance: show the product in the shop, but block purchase.
    elif data.startswith("buy_"):
        pid = data[4:]
        products = load_json("products.json")
        product = products.get(pid)
        if not product:
            await q.answer("Product not found.", show_alert=True)
            return
        if not product.get("enabled", True):
            await q.answer("🛠️This Product Is Under Maintaince", show_alert=True)
            return
        await send_product_plans(bot, chat_id, message_id, pid, user_id)

    elif data.startswith("plan_"):
        parts = data.split("_")
        if len(parts) == 3:
            products = load_json("products.json")
            product = products.get(parts[1])
            if not product:
                await q.answer("Product not found.", show_alert=True)
                return
            if not product.get("enabled", True):
                await q.answer("🛠️This Product Is Under Maintaince", show_alert=True)
                return
            if getattr(q.message, "video", None):
                await delete_msg(bot, chat_id, message_id)
                message_id = None
            await buy_plan(bot, chat_id, message_id, user_id, parts[1], int(parts[2]))

    # Redeem-code approval for Add Balance
    elif data.startswith("redeem_accept_") and is_admin(user_id):
        target_id = data[len("redeem_accept_"):].strip()
        users = load_json("users.json")
        if target_id not in users:
            await edit_msg(bot, chat_id, message_id, "❌ User not found.", btn([[ ("Back", "backadmin") ]]))
            return
        save_temp(user_id, "waiting", "redeem_amount")
        save_temp(user_id, "redeem_target", target_id)
        await edit_msg(
            bot, chat_id, message_id,
            f"✅ <b>Redeem Code Accepted</b>\n\nUser ID: <code>{html.escape(target_id)}</code>\n\n<b>Enter amount</b>\nExample: 1000",
            btn([[ ("❌Cancel", "backadmin") ]])
        )
    elif data.startswith("redeem_reject_") and is_admin(user_id):
        target_id = data[len("redeem_reject_"):].strip()
        users = load_json("users.json")
        if target_id in users:
            try:
                await send_message(bot, int(target_id), "❌ <b>Your redeem code is rejected.</b>")
            except Exception:
                pass
        await edit_msg(bot, chat_id, message_id, "❌ <b>Redeem code rejected.</b>", btn([[ ("Back", "backadmin") ]]))

    # Bot ON/OFF control
    elif data == "bot_status_info" and is_admin(user_id):
        s = load_json("settings.json")
        state = "ON" if s.get("bot_enabled", True) else "OFF"
        await q.answer(f"Bot is currently {state}", show_alert=True)
    elif data == "bot_toggle" and is_admin(user_id):
        s = load_json("settings.json")
        s["bot_enabled"] = not bool(s.get("bot_enabled", True))
        save_json("settings.json", s)
        await send_admin_panel(bot, chat_id, message_id)
    elif data == "edit_maintenance_message" and is_admin(user_id):
        save_temp(user_id, "waiting", "maintenance_message")
        current = load_json("settings.json").get("maintenance_message", DEFAULT_SETTINGS["maintenance_message"])
        await edit_msg(
            bot, chat_id, message_id,
            "🛠️ <b>EDIT MAINTENANCE MESSAGE</b>\n\n"
            "ഇപ്പോൾ കാണിക്കുന്ന മെസേജ് താഴെ കൊടുത്തിരിക്കുന്നു. മാറ്റാൻ പുതിയ ടെക്സ്റ്റ് അയക്കൂ.\n\n"
            f"{current}\n\n"
            "Bold, Italic, Underline, Quote, Spoiler തുടങ്ങിയ Telegram formatting ചെയ്തുതന്നെ അയക്കാം.",
            btn([[ ("Cancel", "backadmin", "danger") ]])
        )

    # Admin
    elif data == "search_order" and is_admin(user_id):
        save_temp(user_id, "waiting", "search_order")
        await edit_msg(bot, chat_id, message_id, "🔎 <b>Search Order</b>\n\nOrder ID അയക്കൂ.\nExample: <code>ORD123456789</code>", btn([[('❌Cancel','backadmin')]]))
    elif data == "category_manage" and is_admin(user_id):
        await category_management_menu(bot, chat_id, message_id)
    elif data == "category_edit_pick" and is_admin(user_id):
        await category_action_picker(bot, chat_id, message_id, "edit")
    elif data == "category_delete_pick" and is_admin(user_id):
        await category_action_picker(bot, chat_id, message_id, "delete")
    elif data.startswith("category_edit_") and is_admin(user_id):
        await category_edit_menu(bot, chat_id, message_id, data[len("category_edit_"):])
    elif data.startswith("category_rename_") and is_admin(user_id):
        cid = data[len("category_rename_"):]
        if cid not in load_json("categories.json"):
            await edit_msg(bot, chat_id, message_id, "❌ Category not found.", btn([[("Back", "category_manage")]]))
        else:
            save_temp(user_id, "category_edit_id", cid)
            save_temp(user_id, "waiting", "edit_category_name")
            await edit_msg(bot, chat_id, message_id, "✏️ <b>Send the new category name</b>", btn([[("❌Cancel", f"category_edit_{cid}")]]))
    elif data.startswith("category_restyle_") and is_admin(user_id):
        await category_style_picker(bot, chat_id, message_id, "edit", data[len("category_restyle_"):])
    elif data.startswith("category_delete_") and not data.startswith("category_delete_confirm_") and is_admin(user_id):
        cid = data[len("category_delete_"):]
        categories_now = load_json("categories.json")
        category = categories_now.get(cid)
        if not category:
            await edit_msg(bot, chat_id, message_id, "❌ Category not found.", btn([[("Back", "category_manage")]]))
        else:
            linked = [p.get("name", "Unnamed") for p in load_json("products.json").values() if p.get("cat") == cid]
            if linked:
                preview = "\n".join(f"• {html.escape(str(name))}" for name in linked[:8])
                await edit_msg(bot, chat_id, message_id,
                    f"⚠️ <b>Cannot delete this category yet.</b>\n\nIt contains <b>{len(linked)}</b> product(s):\n{preview}\n\nMove or delete those products first.",
                    btn([[("Back", "category_delete_pick")]]))
            else:
                await edit_msg(bot, chat_id, message_id,
                    f"🗑️ <b>Delete category?</b>\n\n{html.escape(str(category.get('name', '')))}",
                    btn([[("✅ Yes, Delete", f"category_delete_confirm_{cid}", "danger")],
                         [("❌Cancel", "category_delete_pick")]]))
    elif data.startswith("category_delete_confirm_") and is_admin(user_id):
        cid = data[len("category_delete_confirm_"):]
        categories_now = load_json("categories.json")
        if cid not in categories_now:
            await edit_msg(bot, chat_id, message_id, "❌ Category not found.", btn([[("Back", "category_manage")]]))
        elif any(p.get("cat") == cid for p in load_json("products.json").values()):
            await edit_msg(bot, chat_id, message_id, "⚠️ Products are linked to this category. Move or delete them first.", btn([[("Back", "category_delete_pick")]]))
        else:
            deleted_name = categories_now.pop(cid).get("name", "Category")
            save_json("categories.json", categories_now)
            await edit_msg(bot, chat_id, message_id, f"✅ Deleted category: <b>{html.escape(str(deleted_name))}</b>", btn([[("⬅️ Category Management", "category_manage")]]))
    elif data.startswith("catstyle_") and is_admin(user_id):
        parts = data.split("_")
        mode = parts[1]
        cid = "_".join(parts[2:-1])
        style_name = parts[-1]
        style_value = None if style_name == "none" else style_name
        if mode == "add":
            pending_name = get_temp(user_id).get("category_pending_name", "")
            if not pending_name:
                await edit_msg(bot, chat_id, message_id, "❌ Category name missing. Please add it again.", btn([[("Back", "category_manage")]]))
            else:
                categories_now = load_json("categories.json")
                new_cid = f"c{int(time.time())}"
                while new_cid in categories_now:
                    new_cid += "x"
                categories_now[new_cid] = {"name": pending_name, "style": style_value}
                save_json("categories.json", categories_now)
                save_temp(user_id, "category_pending_name", "")
                save_temp(user_id, "waiting", "")
                await edit_msg(bot, chat_id, message_id, f"✅ Added category: <b>{html.escape(pending_name)}</b>", btn([[("⬅️ Category Management", "category_manage")]]))
        elif mode == "edit":
            categories_now = load_json("categories.json")
            if cid not in categories_now:
                await edit_msg(bot, chat_id, message_id, "❌ Category not found.", btn([[("Back", "category_manage")]]))
            else:
                categories_now[cid]["style"] = style_value
                save_json("categories.json", categories_now)
                await category_edit_menu(bot, chat_id, message_id, cid)
    elif data == "addcat" and is_admin(user_id):
        save_temp(user_id, "waiting", "newcat")
        await edit_msg(bot, chat_id, message_id, "📁 <b>Send the new category name</b>\n\nExample: Non-Root Mobile", btn([[("❌Cancel", "category_manage")]]))
    elif data == "addprod" and is_admin(user_id):
        await category_picker(bot, chat_id, message_id)
    elif data.startswith("addtoprod_") and is_admin(user_id):
        save_temp(user_id, "addprod_cat", data[10:])
        save_temp(user_id, "waiting", "prod_name")
        await edit_msg(bot, chat_id, message_id, "📦 <b>Product Ka Naam Bhejo</b>\n\nExample: SILENT CHEATS SAFE", btn([[("❌Cancel","backadmin")]]))
    elif data == "addplan" and is_admin(user_id):
        await add_plan_product_picker(bot, chat_id, message_id)
    elif data.startswith("addplanprod_") and is_admin(user_id):
        save_temp(user_id, "addplan_pid", data[12:])
        save_temp(user_id, "waiting", "plan_duration")
        await edit_msg(bot, chat_id, message_id, "⏱️ <b>Plan Duration Bhejo</b>\n\nExample: 1 hour\nExample: 5 hours\nExample: 1 day\nExample: 30 days\n\nAap jo type karoge, wahi duration show hoga.", btn([[("❌Cancel","backadmin")]]))
    elif data == "addplankeys" and is_admin(user_id):
        await add_keys_product_picker(bot, chat_id, message_id)
    elif data.startswith("addkeysprod_") and is_admin(user_id):
        await plans_picker(bot, chat_id, message_id, data[12:], "addkeys")
    elif data.startswith("addkeysplan_") and is_admin(user_id):
        parts = data.split("_")
        save_temp(user_id, "addkeys_pid", parts[1])
        save_temp(user_id, "addkeys_plan_index", int(parts[2]))
        save_temp(user_id, "waiting", "add_plan_keys")
        await edit_msg(bot, chat_id, message_id, "🔑 <b>Is plan ke liye Keys Add Karo</b>\n\nEk line me ek key\n\nExample:\nKEY1-ABCD\nKEY2-EFGH\nKEY3-IJKL", btn([[("❌Cancel","backadmin")]]))
    elif data == "editplan" and is_admin(user_id):
        await edit_plan_product_picker(bot, chat_id, message_id)
    elif data.startswith("editplanprod_") and is_admin(user_id):
        await plans_picker(bot, chat_id, message_id, data[13:], "edit")
    elif data.startswith("editplan_") and is_admin(user_id):
        parts = data.split("_")
        pid, idx = parts[1], int(parts[2])
        save_temp(user_id, "edit_pid", pid)
        save_temp(user_id, "edit_plan_index", idx)
        products = load_json("products.json")
        plan = products[pid]["plans"][idx]
        msg = f"✏️ <b>Edit Plan</b>\n\nCurrent: {html.escape(duration_text(plan))} - ₹{plan['price']}\nKeys: {len(plan.get('keys',[]))}\n\nKya edit karna hai?"
        await edit_msg(bot, chat_id, message_id, msg, btn([
            [("⏱️ Duration",f"editplanduration_{pid}_{idx}")],
            [("💰 Price",f"editplanprice_{pid}_{idx}")],
            [("🔑 Add Keys",f"editplankeys_{pid}_{idx}")],
            [("Back","backadmin")]
        ]))
    elif data.startswith("editplanduration_") and is_admin(user_id):
        parts = data.split("_")
        save_temp(user_id, "edit_pid", parts[1])
        save_temp(user_id, "edit_plan_index", int(parts[2]))
        save_temp(user_id, "waiting", "edit_plan_duration")
        await edit_msg(bot, chat_id, message_id, "📅 <b>Naya Days Bhejo</b>", btn([[("❌Cancel","backadmin")]]))
    elif data.startswith("editplanprice_") and is_admin(user_id):
        parts = data.split("_")
        save_temp(user_id, "edit_pid", parts[1])
        save_temp(user_id, "edit_plan_index", int(parts[2]))
        save_temp(user_id, "waiting", "edit_plan_price")
        await edit_msg(bot, chat_id, message_id, "💰 <b>Naya Price Bhejo</b>\n\nExample: 199", btn([[("❌Cancel","backadmin")]]))
    elif data.startswith("editplankeys_") and is_admin(user_id):
        parts = data.split("_")
        save_temp(user_id, "edit_pid", parts[1])
        save_temp(user_id, "edit_plan_index", int(parts[2]))
        save_temp(user_id, "waiting", "edit_plan_keys")
        await edit_msg(bot, chat_id, message_id, "🔑 <b>Is plan ke liye Keys Add Karo</b>\n\nEk line me ek key\n\nExample:\nKEY1-ABCD\nKEY2-EFGH", btn([[("❌Cancel","backadmin")]]))
    elif data == "delplan" and is_admin(user_id):
        await delete_plan_product_picker(bot, chat_id, message_id)
    elif data.startswith("delplanprod_") and is_admin(user_id):
        await plans_picker(bot, chat_id, message_id, data[13:], "delete")
    elif data.startswith("delplan_") and is_admin(user_id):
        parts = data.split("_")
        pid, idx = parts[1], int(parts[2])
        products = load_json("products.json")
        plan = products[pid]["plans"][idx]
        products[pid]["plans"].pop(idx)
        save_json("products.json", products)
        await edit_msg(bot, chat_id, message_id, f"🗑️ <b>Plan Delete Ho Gaya:</b> {duration_text(plan)} - ₹{plan['price']}", btn([[("Back","backadmin")]]))
    elif data == "editprod" and is_admin(user_id):
        await edit_product_picker(bot, chat_id, message_id)
    elif data.startswith("editprod_") and is_admin(user_id):
        pid = data[9:]
        products = load_json("products.json")
        p = products[pid]
        save_temp(user_id, "edit_pid", pid)
        video_status = "✅ Added" if p.get("video_file_id") else "❌ Not Set"
        video_row = [("🎥 Add / Change Video", f"edit_video_{pid}")]
        if p.get("video_file_id"):
            video_row.append(("🗑️ Remove Video", f"remove_video_{pid}"))
        await edit_msg(
            bot, chat_id, message_id,
            f"✏️ <b>Edit Product</b>\n\nName: {html.escape(str(p['name']))}\nPlans: {len(p.get('plans',[]))}\nVideo: {video_status}",
            btn([[ ("📝 Name",f"edit_name_{pid}")], video_row, [ ("Back","backadmin")]])
        )
    elif data.startswith("edit_video_") and is_admin(user_id):
        pid = data[len("edit_video_"):]
        products = load_json("products.json")
        if pid not in products:
            await edit_msg(bot, chat_id, message_id, "❌ Product nahi mila!", btn([[ ("Back", "backadmin") ]]))
            return
        save_temp(user_id, "edit_pid", pid)
        save_temp(user_id, "waiting", "edit_product_video")
        await edit_msg(bot, chat_id, message_id, f"🎥 <b>Product Video</b>\n\nSend the video for <b>{html.escape(str(products[pid].get('name','')))}</b>.\n\nThe current product text will automatically be used as the video caption.", btn([[ ("❌Cancel", "backadmin") ]]))
    elif data.startswith("remove_video_") and is_admin(user_id):
        pid = data[len("remove_video_"):]
        products = load_json("products.json")
        if pid in products:
            products[pid].pop("video_file_id", None)
            save_json("products.json", products)
            await edit_msg(bot, chat_id, message_id, "✅ <b>Product video removed.</b>", btn([[ ("Back", "backadmin") ]]))
        else:
            await edit_msg(bot, chat_id, message_id, "❌ Product nahi mila!", btn([[ ("Back", "backadmin") ]]))
    elif data.startswith("edit_name_") and is_admin(user_id):
        save_temp(user_id, "edit_pid", data[10:])
        save_temp(user_id, "waiting", "edit_name")
        await edit_msg(bot, chat_id, message_id, "📝 <b>Naya Name Bhejo</b>", btn([[("❌Cancel","backadmin")]]))
    elif data == "delprod" and is_admin(user_id):
        await delete_product_picker(bot, chat_id, message_id)
    elif data.startswith("delprod_") and is_admin(user_id):
        pid = data[8:]
        products = load_json("products.json")
        if pid not in products:
            await edit_msg(bot, chat_id, message_id, "❌ Product nahi mila!", btn([[("Back","backadmin")]]))
            return
        p = products.pop(pid)
        save_json("products.json", products)
        await edit_msg(bot, chat_id, message_id, f"🗑️ <b>Product Delete Ho Gaya!</b>\n\nName: {html.escape(str(p['name']))}\nCategory: {html.escape(str(p['cat']))}\nPlans: {len(p.get('plans',[]))}", btn([[("Back to Admin","backadmin")]]))
    elif data == "broadcast" and is_admin(user_id):
        save_temp(user_id, "waiting", "broadcast_text")
        await edit_msg(bot, chat_id, message_id, "📢 <b>Broadcast Message</b>\n\nMessage bhejo (Text, Photo, Video, Voice, Document)\n\n<b>Note:</b> Photo/Video/Voice/Document ke saath caption bhi bhej sakte ho", btn([[("❌Cancel","backadmin")]]))
    elif data == "userlist" and is_admin(user_id):
        users = load_json("users.json")
        msg = f"👥 <b>Total Users:</b> {len(users)}\n\n"
        for i, (uid,u) in enumerate(users.items(),1):
            msg += f"{i}. {html.escape(str(u.get('name','')))}"
            if u.get("username"):
                msg += f" (@{html.escape(str(u['username']))})"
            msg += f"\n   🆔 <code>{uid}</code>\n   📅 {u.get('join','')}\n\n"
            if i >= 20:
                msg += f"\n... aur {max(0,len(users)-20)} users"
                break
        await edit_msg(bot, chat_id, message_id, msg, btn([[("Back","backadmin")]]))
    elif data == "game_controls" and is_admin(user_id):
        s = load_json("settings.json")
        tt_status = "🟢 ON" if s.get("tt_enabled", True) else "🔴 OFF"
        rps_status = "🟢 ON" if s.get("rps_enabled", True) else "🔴 OFF"
        await edit_msg(bot, chat_id, message_id,
            "🕹️ <b>ADMIN GAME CONTROLS</b>\n\n"
            f"❌⭕ <b>TicTacToe:</b> {tt_status} • Cooldown: {float(s.get('tt_cooldown_hours',24)):.1f}h\n"
            f"✊ <b>Rock Paper Scissors:</b> {rps_status} • Cooldown: {float(s.get('rps_cooldown_hours',24)):.1f}h\n\nChoose a control:",
            btn([[ ("🔄 TicTacToe ON/OFF", "toggle_tt_game") ], [ ("🔄 RPS ON/OFF", "toggle_rps_game") ], [ ("⏳ TicTacToe Cooldown", "set_tt_cooldown") ], [ ("⏳ RPS Cooldown", "set_rps_cooldown") ], [ ("💰 Reward Settings", "playearn_settings") ], [ ("🏆 View Leaderboard", "game_leaderboard") ], [ ("Back to Admin", "backadmin") ]]))
    elif data in ("toggle_tt_game", "toggle_rps_game") and is_admin(user_id):
        s = load_json("settings.json")
        key = "tt_enabled" if data == "toggle_tt_game" else "rps_enabled"
        s[key] = not bool(s.get(key, True))
        save_json("settings.json", s)
        await edit_msg(bot, chat_id, message_id, f"✅ <b>{'TicTacToe' if key == 'tt_enabled' else 'Rock Paper Scissors'} is now {'ON' if s[key] else 'OFF'}.</b>", btn([[ ("🕹️ Back to Game Controls", "game_controls") ]]))
    elif data in ("set_tt_cooldown", "set_rps_cooldown") and is_admin(user_id):
        waiting = "tt_cooldown" if data == "set_tt_cooldown" else "rps_cooldown"
        save_temp(user_id, "waiting", waiting)
        game_name = "TicTacToe" if waiting == "tt_cooldown" else "Rock Paper Scissors"
        await edit_msg(bot, chat_id, message_id, f"⏳ <b>Set {game_name} Cooldown</b>\n\nSend cooldown in hours (0–8760). Default: <code>24</code>.", btn([[ ("❌Cancel", "game_controls") ]]))
    elif data == "daily_task_settings" and is_admin(user_id):
        s = load_json("settings.json")
        data_store, day_data = daily_task_day_data()
        tasks = [t for t in day_data.get("tasks", []) if isinstance(t, dict)]
        active_count = sum(1 for t in tasks if t.get("enabled", True))
        await edit_msg(bot, chat_id, message_id,
            "🎯 <b>DAILY TASK ADMIN</b>\n\n"
            f"📌 Today's tasks: <b>{active_count}</b>\n"
            f"🧩 New task defaults — Games: <b>{int(s.get('daily_task_games', 2))}</b>, Reward: <b>₹{float(s.get('daily_task_reward', 1.0)):.2f}</b>, Max users: <b>{int(s.get('daily_task_max_users', 100))}</b>\n\n"
            "Set the defaults, then tap <b>Create New Task</b>. Each task keeps its own settings, participants and reward history.",
            btn([[('➕ Create New Task','daily_task_create','success')], [('📋 View / Delete Today’s Tasks','daily_task_manage','primary')], [('👥 Set Maximum Users','daily_task_set_users','primary')], [('🎮 Set Required Games','daily_task_set_games','primary')], [('🎁 Set Reward Amount','daily_task_set_reward','success')], [('Back to Admin','backadmin','danger')]]))
    elif data == "daily_task_create" and is_admin(user_id):
        save_temp(user_id, "waiting", "daily_task_name")
        await edit_msg(bot, chat_id, message_id,
            "📝 <b>Enter Daily Task Name</b>\n\nSend the name you want for this task.\nExample: <code>Evening Challenge</code>\n\nThe task will not be created with a default name.",
            btn([[('❌Cancel','daily_task_settings','danger')]]))
    elif data == "daily_task_manage" and is_admin(user_id):
        data_store, day_data = daily_task_day_data()
        tasks = [t for t in day_data.get("tasks", []) if isinstance(t, dict)]
        lines = ["📋 <b>TODAY’S DAILY TASKS</b>", ""]
        rows = []
        for task in tasks:
            if not task.get("enabled", True):
                continue
            lines.append(f"📌 <b>{html.escape(str(task.get('name') or 'Task'))}</b> — 🎮 {int(task.get('required', 1))} games — 🎁 ₹{float(task.get('reward', 0)):.2f} — 👥 {len(task.get('participants', []))}/{int(task.get('max_users', 100))}")
            rows.append([(f"🗑️ Delete {str(task.get('name') or 'Task')}"[:60], f"daily_task_delete_{task.get('id')}", "danger")])
        if not tasks:
            lines.append("No tasks created today.")
        rows.extend([[('➕ Create New Task','daily_task_create','success')], [('Back','daily_task_settings','primary')]])
        await edit_msg(bot, chat_id, message_id, "\n".join(lines), btn(rows))
    elif data.startswith("daily_task_delete_") and is_admin(user_id):
        task_id = data.rsplit("_", 1)[1]
        data_store, day_data = daily_task_day_data()
        found = False
        for task in day_data.get("tasks", []):
            if isinstance(task, dict) and str(task.get("id")) == task_id:
                task["enabled"] = False
                found = True
                break
        save_json("daily_tasks.json", data_store)
        await edit_msg(bot, chat_id, message_id, "🗑️ <b>Task deleted.</b> Its history and already-paid rewards are preserved.", btn([[('📋 Back to Tasks','daily_task_manage','primary')], [('Back to Admin','daily_task_settings','danger')]]))
    elif data in ("daily_task_set_users", "daily_task_set_games", "daily_task_set_reward") and is_admin(user_id):
        waiting_map = {"daily_task_set_users":"daily_task_users", "daily_task_set_games":"daily_task_games", "daily_task_set_reward":"daily_task_reward"}
        save_temp(user_id, "waiting", waiting_map[data])
        prompts = {
            "daily_task_users": "👥 <b>Default Maximum Participants Per New Task</b>\n\nSend a whole number greater than 0. Example: <code>100</code>",
            "daily_task_games": "🎮 <b>Default Games Required For New Task</b>\n\nSend a whole number greater than 0. Example: <code>3</code>",
            "daily_task_reward": "🎁 <b>Default Reward For New Task</b>\n\nSend reward in INR. Example: <code>1.00</code>",
        }
        await edit_msg(bot, chat_id, message_id, prompts[waiting_map[data]], btn([[('❌Cancel','daily_task_settings')]]))
    elif data == "playearn_settings" and is_admin(user_id):
        s = load_json("settings.json")
        await edit_msg(bot, chat_id, message_id,
            "🎮 <b>PLAY AND EARN SETTINGS</b>\n\n"
            f"❌⭕ <b>TicTacToe</b>\nMinimum: <b>₹{float(s.get('tt_min_reward', 0.01)):.2f}</b>\nMaximum: <b>₹{float(s.get('tt_max_reward', 0.75)):.2f}</b>\n\n"
            f"✊ <b>Rock Paper Scissors</b>\nMinimum: <b>₹{float(s.get('rps_min_reward', 0.01)):.2f}</b>\nMaximum: <b>₹{float(s.get('rps_max_reward', 0.75)):.2f}</b>\n\nSelect a setting to change:",
            btn([[('❌⭕ TicTacToe Min Reward','tt_reward_min')], [('❌⭕ TicTacToe Max Reward','tt_reward_max')], [('✊ RPS Min Reward','rps_reward_min')], [('✊ RPS Max Reward','rps_reward_max')], [('Back to Admin','backadmin')]]))
    elif data in ("tt_reward_min", "tt_reward_max", "rps_reward_min", "rps_reward_max") and is_admin(user_id):
        waiting_map = {"tt_reward_min":"tt_min", "tt_reward_max":"tt_max", "rps_reward_min":"rps_min", "rps_reward_max":"rps_max"}
        save_temp(user_id, "waiting", waiting_map[data])
        label_map = {"tt_reward_min":"TicTacToe Minimum Reward", "tt_reward_max":"TicTacToe Maximum Reward", "rps_reward_min":"Rock Paper Scissors Minimum Reward", "rps_reward_max":"Rock Paper Scissors Maximum Reward"}
        await edit_msg(bot, chat_id, message_id, f"💰 <b>Set {label_map[data]}</b>\n\nSend the amount in INR. Example: <code>0.25</code>", btn([[('❌Cancel','playearn_settings')]]))
    elif data == "restartgame_confirm" and is_admin(user_id):
        await edit_msg(bot, chat_id, message_id,
            "⚠️ <b>Restart Game Cooldowns?</b>\n\nThis resets the 24-hour cooldown for both games for every user. It does not change balances or rewards.",
            btn([[('✅ Yes, Reset All','restartgame_yes')], [('❌Cancel','backadmin')]]))
    elif data == "restartgame_yes" and is_admin(user_id):
        for filename in (TT_FILE, RPS_FILE):
            games = load_json(filename)
            for game in games.values():
                if isinstance(game, dict):
                    game["last_play"] = 0
            save_json(filename, games)
        await edit_msg(bot, chat_id, message_id, "✅ <b>All users' 24-hour cooldowns have been reset for TicTacToe and Rock Paper Scissors.</b>", btn([[('Back to Admin','backadmin')]]))
    elif data == "lucky_spin_settings" and is_admin(user_id):
        s = load_json("settings.json")
        await edit_msg(bot, chat_id, message_id, f"🎡 <b>Lucky Spin Settings</b>\n\n🔽 Minimum Reward: <b>₹{float(s.get('lucky_spin_min_reward',1.0)):.2f}</b>\n🔼 Maximum Reward: <b>₹{float(s.get('lucky_spin_max_reward',5.0)):.2f}</b>\n\nChoose what you want to change:", btn([[('🔽 Set Minimum Reward','lucky_set_min')],[('🔼 Set Maximum Reward','lucky_set_max')],[('Back to Admin','backadmin')]]))
    elif data == "lucky_set_min" and is_admin(user_id):
        save_temp(user_id, "waiting", "lucky_min")
        await edit_msg(bot, chat_id, message_id, "🔽 <b>Set Lucky Spin Minimum Reward</b>\n\nSend amount. Example: <code>1</code>", btn([[('❌Cancel','backadmin')]]))
    elif data == "lucky_set_max" and is_admin(user_id):
        save_temp(user_id, "waiting", "lucky_max")
        await edit_msg(bot, chat_id, message_id, "🔼 <b>Set Lucky Spin Maximum Reward</b>\n\nSend amount. Example: <code>5</code>", btn([[('❌Cancel','backadmin')]]))
    elif data == "create_coupon" and is_admin(user_id):
        temp_all = load_json("temp.json"); temp = temp_all.get(str(user_id), {}); temp["waiting"] = "coupon_code"; temp_all[str(user_id)] = temp; save_json("temp.json", temp_all)
        await edit_msg(bot, chat_id, message_id, "🎟️ <b>Create Coupon</b>\n\nSend coupon code.\nExample: <code>TURBO100</code>", btn([[('❌Cancel','backadmin')]]))
    elif data == "adduserbal" and is_admin(user_id):
        save_temp(user_id, "waiting", "adduserbal_id")
        await edit_msg(bot, chat_id, message_id, "💰 <b>Add Balance to User</b>\n\nUser ID bhejo (jo profile me dikhta hai)\n\nExample: 8154859186", btn([[("❌Cancel","backadmin")]]))
    elif data == "edit_start_menu" and is_admin(user_id):
        save_temp(user_id, "waiting", "start_menu_template")
        current = load_json("settings.json").get("start_menu_template") or "(Default start menu is currently active)"
        await edit_msg(bot, chat_id, message_id,
            "✏️ <b>Edit Start Menu</b>\n\nSend the complete Start Menu text, or send a photo/video/GIF with a caption. Telegram formatting such as Bold, Italic, Underline, Strikethrough, Spoiler, Blockquote, expandable quote and links will be preserved exactly. You can also use HTML tags.\n\n<b>Variables:</b>\n<code>[FIRST_NAME]</code> — User first name\n<code>[SECOND_NAME]</code> — User last name\n<code>[USERNAME]</code> — Username (without @)\n<code>[BALANCE]</code> — Balance amount\n<code>[USER_ID]</code> — User ID (monospace)\n\nVariables can be placed inside formatting tags, e.g. <code>&lt;b&gt;[FIRST_NAME]&lt;/b&gt;</code>.\n\n<b>Current template:</b>\n" + html.escape(str(current)),
            btn([[('❌ Cancel','backadmin')]]))
    elif data == "setproof" and is_admin(user_id):
        save_temp(user_id, "waiting", "proof")
        await edit_msg(bot, chat_id, message_id, "📄 <b>Payment Proof Link Bhejo</b>", btn([[("❌Cancel","backadmin")]]))
    elif data == "sethowto" and is_admin(user_id):
        save_temp(user_id, "waiting", "howto")
        await edit_msg(bot, chat_id, message_id, "📖 <b>How To Use Link Bhejo</b>", btn([[("❌Cancel","backadmin")]]))
    elif data == "set_ticket_daily_limit" and is_admin(user_id):
        cfg = load_json("settings.json")
        current_limit = int(cfg.get("ticket_daily_limit", 5))
        save_temp(user_id, "waiting", "ticket_daily_limit")
        await edit_msg(bot, chat_id, message_id,
            "🎫 <b>Set Daily Ticket Limit</b>\n\nSend the maximum number of tickets each user can create per India calendar day. The limit resets at <b>12:00 AM IST</b> every day (not 24 hours after the last ticket).\n\nCurrent limit: <b>" + str(current_limit) + "</b>",
            btn([[ ("❌Cancel", "backadmin", "danger")]]))
    elif data == "setsupport" and is_admin(user_id):
        save_temp(user_id, "waiting", "support")
        await edit_msg(bot, chat_id, message_id, "💬 <b>Support Username Bhejo</b>", btn([[("❌Cancel","backadmin")]]))
    elif data == "setdownload" and is_admin(user_id):
        save_temp(user_id, "waiting", "download")
        current = load_json("settings.json").get("download_link", "")
        await edit_msg(bot, chat_id, message_id, f"📥 <b>Download Files Link</b>\n\nSend the URL to open from the Download Files button.\n\nCurrent: <code>{html.escape(str(current))}</code>", btn([[ ("❌Cancel","backadmin") ]]))
    elif data == "set_order_channel" and is_admin(user_id):
        save_temp(user_id, "waiting", "order_channel")
        current = load_json("settings.json").get("order_channel_id", "")
        await edit_msg(bot, chat_id, message_id, f"📢 <b>Order Channel ID</b>\n\nSend channel Chat ID.\nExample: <code>-1004301332161</code>\n\nCurrent: <code>{html.escape(str(current))}</code>", btn([[ ("❌Cancel","backadmin") ]]))

    elif data == "test_order_channel" and is_admin(user_id):
        try:
            await send_order_to_channel(
                bot, "TEST-ORDER-001", "Test Product",
                {"duration": "Lifetime"}, 100, load_json("settings.json").get("order_channel_id", "")
            )
            await edit_msg(bot, chat_id, message_id,
                "✅ <b>Channel Test Successful!</b>\n\nCheck your order channel.",
                btn([[ ("Back", "backadmin") ]])
            )
        except Exception as e:
            err = html.escape(str(e))
            await edit_msg(bot, chat_id, message_id,
                "❌ <b>Channel Test Failed</b>\n\n"
                f"<code>{err}</code>\n\n"
                "Check that the Channel ID is correct and the bot is an admin with <b>Post Messages</b> permission.",
                btn([[ ("Back", "backadmin") ]])
            )

    elif data == "backadmin" and is_admin(user_id):
        await send_admin_panel(bot, chat_id, message_id)


    # Navigation
    elif data == "back":
        if get_temp(user_id).get("waiting") == "orders_pin":
            _clear_orders_pin_state(user_id)
            context.user_data.pop("orders_pin_digits", None)
        if getattr(q.message, "video", None):
            await delete_msg(bot, chat_id, message_id)
            message_id = None
        balances = load_json("balances.json")
        await send_main_menu(bot, chat_id, first_name, balances.get(str(user_id),0), message_id, telegram_user=q.from_user)
    elif data == "backkey":
        await send_add_balance(bot, chat_id, message_id, user_id)
    elif data in ("backcat","backshop"):
        if getattr(q.message, "video", None):
            await delete_msg(bot, chat_id, message_id)
            message_id = None
        await send_categories(bot, chat_id, message_id, first_name)

async def submit_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a ticket from any Telegram message type and copy the original to admin."""
    msg = update.message
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    tickets = load_json("tickets.json")
    tid = str(int(time.time() * 1000))
    caption_or_text = (msg.text or msg.caption or "").strip()
    content_type = getattr(msg, "effective_attachment", None)
    if not caption_or_text:
        caption_or_text = f"[{msg.effective_attachment.__class__.__name__ if msg.effective_attachment else 'Message'}]"
    ticket = {
        "user_id": user_id, "username": user.username or "",
        "name": user.full_name or user.first_name or "User",
        "issue": caption_or_text[:3000], "reply": "No reply yet", "status": "open",
        "created": time.time(), "message_type": "media" if msg.effective_attachment else "text",
        "user_message_id": msg.message_id, "user_chat_id": chat_id,
    }
    tickets[tid] = ticket
    save_json("tickets.json", tickets)
    save_temp(user_id, "waiting", "")
    admin_text = (
        f"🎫 <b>NEW SUPPORT TICKET #{html.escape(tid)}</b>\n\n"
        f"👤 <b>User:</b> {html.escape(ticket['name'])}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"🔗 <b>Username:</b> @{html.escape(ticket['username']) if ticket['username'] else 'N/A'}\n\n"
        "📎 The user's original message is attached above."
    )
    try:
        await context.bot.copy_message(chat_id=int(ADMIN_ID), from_chat_id=chat_id, message_id=msg.message_id)
        await context.bot.send_message(
            chat_id=int(ADMIN_ID), text=admin_text, parse_mode="HTML",
            reply_markup=btn([[ ("✍️ Reply to User", f"ticket_reply_{tid}", "success")],
                              [("📋 Ticket List", "ticket_admin_list", "primary")]])
        )
        await send_message(context.bot, chat_id,
            f"✅ Your ticket <b>#{html.escape(tid)}</b> has been sent to support. You can check replies in My Tickets.",
            btn([[ ("📋 My Tickets", "ticket_mine", "primary")], [("Back To Menu", "back", "danger")]]))
    except Exception:
        tickets.pop(tid, None)
        save_json("tickets.json", tickets)
        save_temp(user_id, "waiting", "ticket_issue")
        await send_message(context.bot, chat_id, "❌ Your ticket could not be delivered. Please try again later.")


async def handle_auto_bc_forwarded_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a channel from a message genuinely forwarded from that channel."""
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat or not is_admin(user.id):
        return False
    temp = get_temp(user.id)
    waiting = temp.get("waiting", "") or context.user_data.get("auto_bc_waiting", "")
    if waiting != "auto_bc_channel":
        return False

    status_msg = await send_message(context.bot, chat.id,
        "🔎 <b>Reading forwarded channel message and checking permissions...</b>")
    origin = getattr(msg, "forward_origin", None)
    source_chat = None
    # PTB 20+ represents channel forwards as MessageOriginChannel.
    if origin is not None and getattr(origin, "type", None) == "channel":
        source_chat = getattr(origin, "chat", None)
    # Compatibility with older Telegram message fields.
    if source_chat is None:
        source_chat = getattr(msg, "forward_from_chat", None)

    if source_chat is None or getattr(source_chat, "type", None) != "channel":
        await edit_msg(context.bot, chat.id, status_msg.message_id,
            "❌ <b>This is not a forwarded channel post.</b>\n\n"
            "Open the channel, tap <b>Forward</b> on one of its messages, and send that forwarded message directly here.\n\n"
            "Do not send a channel link, ID, screenshot, or copied text.",
            btn([[ ("Cancel", "auto_bc_channels") ]]))
        save_temp(user.id, "waiting", "auto_bc_channel")
        context.user_data["auto_bc_waiting"] = "auto_bc_channel"
        return True

    try:
        source_id = int(source_chat.id)
        # Resolve the channel and verify the bot can actually publish there.
        channel = await asyncio.wait_for(context.bot.get_chat(source_id), timeout=20)
        bot_info = await asyncio.wait_for(context.bot.get_me(), timeout=20)
        member = await asyncio.wait_for(
            context.bot.get_chat_member(source_id, bot_info.id), timeout=20
        )
        member_status = str(member.status)
        if member_status not in ("administrator", "creator"):
            raise ValueError("This bot is not an administrator in the forwarded channel. Add it as an admin first.")
        if member_status != "creator" and not bool(getattr(member, "can_post_messages", False)):
            raise ValueError("The bot is an admin, but the Post Messages permission is disabled.")

        settings = load_json("settings.json")
        channels = auto_bc_channels(settings)
        channel_id = str(channel.id)
        if channel_id not in channels:
            channels[channel_id] = {
                "title": getattr(channel, "title", None) or getattr(source_chat, "title", None) or channel_id,
                "interval": "10M", "enabled": False, "items": [], "index": 0, "next_at": 0
            }
        settings["auto_broadcast_channels"] = channels
        settings["auto_broadcast_selected_channel"] = channel_id
        save_json("settings.json", settings)

        # Confirm the write from disk before telling the admin it was added.
        saved = auto_bc_channels(load_json("settings.json"))
        if channel_id not in saved:
            raise RuntimeError("Could not save this channel to settings.json. Check host storage permissions.")

        save_temp(user.id, "waiting", "")
        context.user_data.pop("auto_bc_waiting", None)
        await edit_msg(context.bot, chat.id, status_msg.message_id,
            f"✅ <b>CHANNEL VERIFIED & ADDED</b>\n\n"
            f"Channel: <b>{html.escape(str(getattr(channel, 'title', 'Telegram Channel')))}</b>\n"
            f"Channel ID: <code>{channel_id}</code>\n"
            "Status: <b>Ready</b>\n\n"
            "Now open this channel and add the messages you want the bot to broadcast.")
        await auto_bc_channel_home(context.bot, chat.id, 0, channel_id)
    except Exception as exc:
        detail = str(exc).strip() or type(exc).__name__
        print(f"[AUTO BROADCAST] Forwarded-channel setup failed: {type(exc).__name__}: {detail}")
        await edit_msg(context.bot, chat.id, status_msg.message_id,
            "❌ <b>CHANNEL SETUP FAILED</b>\n\n"
            f"Reason: <code>{html.escape(detail[:350])}</code>\n\n"
            "Make sure the forwarded post is from the correct channel and this bot is an administrator with Post Messages permission. Then forward a channel post again.",
            btn([[ ("Cancel", "auto_bc_channels") ]]))
        save_temp(user.id, "waiting", "auto_bc_channel")
        context.user_data["auto_bc_waiting"] = "auto_bc_channel"
    return True


# ============================================================
# TEXT / MEDIA HANDLER
# ============================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    msg_obj = update.message
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = msg_obj.text or ""
    temp_all = load_json("temp.json")
    temp = temp_all.get(str(user_id), {})
    waiting = temp.get("waiting", "") or context.user_data.get("auto_bc_waiting", "")
    settings = load_json("settings.json")
    products = load_json("products.json")
    users = load_json("users.json")
    balances = load_json("balances.json")
    categories = load_json("categories.json")

    if is_admin(user_id) and waiting == "auto_bc_channel":
        await handle_auto_bc_forwarded_channel(update, context)
        return
    if is_admin(user_id) and waiting == "auto_bc_bot_interval":
        try: interval_seconds = parse_broadcast_interval(text)
        except ValueError as exc:
            await send_message(context.bot, chat_id, html.escape(str(exc))); return
        s = load_json("settings.json"); cfg = s.setdefault("auto_broadcast_bot", {})
        cfg["interval"] = text.strip().upper()
        cfg["next_at"] = time.time() + interval_seconds if cfg.get("enabled") else 0
        s["auto_broadcast_bot"] = cfg; save_json("settings.json", s); save_temp(user_id, "waiting", "")
        await auto_bc_bot_home(context.bot, chat_id, 0); return
    if is_admin(user_id) and waiting == "auto_bc_interval":
        try: parse_broadcast_interval(text)
        except ValueError as exc:
            await send_message(context.bot, chat_id, html.escape(str(exc))); return
        temp_target = get_temp(user_id).get("auto_bc_target", "")
        channels = auto_bc_channels(settings); c = channels.get(str(temp_target))
        if not c:
            await send_message(context.bot, chat_id, "Channel not found. Please select it again."); return
        c["interval"] = text.strip().upper(); c["next_at"] = time.time() + parse_broadcast_interval(text)
        channels[str(temp_target)] = c; settings["auto_broadcast_channels"] = channels
        save_json("settings.json", settings); save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id, f"Interval updated to <b>{html.escape(text.strip().upper())}</b>.")
        await auto_bc_channel_home(context.bot, chat_id, 0, str(temp_target)); return

    if not text:
        return

    if is_admin(user_id) and waiting == "auto_bc_bot_add_message":
        s = load_json("settings.json"); cfg = s.setdefault("auto_broadcast_bot", {"enabled": False, "interval": "10M", "items": [], "index": 0, "next_at": 0})
        cfg.setdefault("items", []).append({"chat_id": int(chat_id), "message_id": int(msg_obj.message_id), "type": "text"})
        s["auto_broadcast_bot"] = cfg; save_json("settings.json", s)
        await send_message(context.bot, chat_id, f"Bot broadcast message saved. Total: <b>{len(cfg['items'])}</b>.", btn([[ ("Done", "auto_bc_bot_home") ]]))
        return
    if is_admin(user_id) and waiting == "auto_bc_add_message":
        target = str(get_temp(user_id).get("auto_bc_target", settings.get("auto_broadcast_selected_channel", "")))
        channels = auto_bc_channels(settings); channel = channels.get(target)
        if not channel:
            await send_message(context.bot, chat_id, "Select a verified channel before adding messages."); return
        channel.setdefault("items", []).append({"chat_id": int(chat_id), "message_id": int(msg_obj.message_id), "type": "text"})
        channels[target] = channel; settings["auto_broadcast_channels"] = channels; save_json("settings.json", settings)
        await send_message(context.bot, chat_id, f"Text message added. Total: <b>{len(channel['items'])}</b>.", btn([[ ("Done", f"auto_bc_open_{target}") ]]))
        return

    # Admin replies are routed privately to the exact user who opened the ticket.
    if is_admin(user_id) and context.user_data.get("ticket_reply_id"):
        tid = str(context.user_data.pop("ticket_reply_id"))
        tickets = load_json("tickets.json")
        ticket = tickets.get(tid)
        if not ticket:
            await send_message(context.bot, chat_id, "Ticket not found.")
            return
        ticket["reply"] = text.strip()
        ticket["replied_at"] = time.time()
        tickets[tid] = ticket
        save_json("tickets.json", tickets)
        try:
            await context.bot.send_message(chat_id=int(ticket["user_id"]),
                text=f"📩 <b>SUPPORT REPLY — TICKET #{html.escape(tid)}</b>\n\n{html.escape(text.strip())}\n\nUse Support → Tickets → My Tickets to view the conversation.",
                parse_mode="HTML")
            await send_message(context.bot, chat_id, f"✅ Reply sent privately to the user for Ticket #{html.escape(tid)}.")
        except Exception as exc:
            await send_message(context.bot, chat_id, f"❌ Could not send reply: {html.escape(str(exc)[:200])}")
        return

    if waiting == "ticket_daily_limit" and is_admin(user_id):
        try:
            new_limit = int(text.strip())
            if new_limit < 0 or new_limit > 1000:
                raise ValueError
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Send a whole number from 0 to 1000. Use 0 to disable new tickets for users.")
            return
        cfg = load_json("settings.json")
        cfg["ticket_daily_limit"] = new_limit
        save_json("settings.json", cfg)
        save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id,
            f"✅ Daily ticket limit set to <b>{new_limit}</b> per user. It resets every day at <b>12:00 AM IST</b>.",
            btn([[ ("👑 Back to Admin", "backadmin", "primary")]]))
        return

    if waiting == "ticket_issue":
        if len(text.strip()) < 1 or len(text.strip()) > 3000:
            await send_message(context.bot, chat_id, "Please send your issue in a message up to 3000 characters, or attach any supported media.")
            return
        await submit_ticket_message(update, context)
        return

    if waiting == "orders_pin":
        await send_message(context.bot, chat_id, "🔐 Please use the numeric keypad buttons to enter your Profile & My Orders PIN.")
        return

    if waiting == "reseller_plan_name" and is_admin(user_id):
        name = text.strip()
        if not name or len(name) > 50:
            await send_message(context.bot, chat_id, "❌ Send a valid plan name (up to 50 characters).")
            return
        save_temp(user_id, "reseller_new_plan_name", name)
        save_temp(user_id, "waiting", "reseller_plan_price")
        await send_message(context.bot, chat_id, f"Send the price for <b>{html.escape(name)}</b> in rupees. Example: 100")
        return
    if waiting == "reseller_plan_price" and is_admin(user_id):
        try: price = round(float(text.strip()), 2)
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Enter a valid number, for example 100.")
            return
        if price <= 0:
            await send_message(context.bot, chat_id, "❌ Price must be greater than zero.")
            return
        save_temp(user_id, "reseller_new_plan_price", price)
        save_temp(user_id, "waiting", "reseller_plan_days")
        name = str(temp.get("reseller_new_plan_name", "Reseller Plan"))
        await send_message(context.bot, chat_id, f"Send how many days this plan should last for <b>{html.escape(name)}</b>. Example: 7")
        return
    if waiting == "reseller_plan_days" and is_admin(user_id):
        try: days = int(text.strip())
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Enter the number of days as a whole number. Example: 7")
            return
        if not 1 <= days <= 3650:
            await send_message(context.bot, chat_id, "❌ Days must be between 1 and 3650.")
            return
        s = load_json("settings.json"); plans = s.setdefault("reseller_plans", [])
        name = str(temp.get("reseller_new_plan_name", "Reseller Plan"))
        price = round(float(temp.get("reseller_new_plan_price", 0) or 0), 2)
        plans.append({"name": name, "price": price, "days": days})
        s["reseller_plans"] = plans; save_json("settings.json", s)
        save_temp(user_id, "waiting", ""); save_temp(user_id, "reseller_new_plan_name", ""); save_temp(user_id, "reseller_new_plan_price", "")
        await send_message(context.bot, chat_id, f"✅ <b>Reseller Plan Added</b>\n\n📅 {html.escape(name)}\n⏳ Duration: <b>{days} days</b>\n💰 ₹{price:.2f}")
        await show_reseller_settings(context.bot, chat_id, 0)
        return
    if waiting == "reseller_edit_price" and is_admin(user_id):
        try: price = round(float(text.strip()), 2)
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Enter a valid price."); return
        if price <= 0:
            await send_message(context.bot, chat_id, "❌ Price must be greater than zero."); return
        s = load_json("settings.json"); plans = s.get("reseller_plans", [])
        try: idx = int(temp.get("reseller_plan_index", -1))
        except (TypeError, ValueError): idx = -1
        if not 0 <= idx < len(plans):
            await send_message(context.bot, chat_id, "❌ Plan not found."); return
        plans[idx]["price"] = price; s["reseller_plans"] = plans; save_json("settings.json", s)
        save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id, "✅ Reseller plan price updated.")
        await show_reseller_settings(context.bot, chat_id, 0)
        return
    if waiting == "reseller_discount" and is_admin(user_id):
        try: discount = int(text.strip())
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Enter a whole number from 1 to 90."); return
        if not 1 <= discount <= 90:
            await send_message(context.bot, chat_id, "❌ Discount must be between 1 and 90."); return
        s = load_json("settings.json"); s["reseller_discount_percent"] = discount; save_json("settings.json", s)
        save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id, f"✅ Reseller product discount set to {discount}%.")
        await show_reseller_settings(context.bot, chat_id, 0)
        return
    if waiting in ("reseller_manual_add", "reseller_manual_remove") and is_admin(user_id):
        target = text.strip()
        if not target.isdigit():
            await send_message(context.bot, chat_id, "❌ Send a numeric Telegram User ID."); return
        users = load_json("users.json")
        if waiting == "reseller_manual_add":
            u = users.setdefault(target, {})
            previous = u.get("reseller", {}) if isinstance(u.get("reseller", {}), dict) else {}
            reseller_id = str(previous.get("login_id") or random.randint(10000000, 99999999))
            password = str(random.randint(100000, 999999999))
            salt = os.urandom(16).hex()
            password_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 160000).hex()
            u["reseller"] = {"active": True, "active_until": "permanent", "plan": "Admin Granted", "login_id": reseller_id, "password_salt": salt, "password_hash": password_hash}
            users[target] = u; save_json("users.json", users)
            result = f"✅ Reseller access granted permanently to User ID <code>{target}</code>."
            try: await send_message(context.bot, int(target), f"💎 <b>Reseller Access Activated by Admin!</b>\nYou now receive the configured discount on products.\n\n🆔 Reseller ID: <code>{reseller_id}</code>\n🔑 Numeric Password: <code>{password}</code>\nKeep these details private.")
            except Exception: pass
        else:
            u = users.get(target, {})
            if isinstance(u, dict) and u.get("reseller"):
                u["reseller"]["active"] = False; users[target] = u; save_json("users.json", users)
            result = f"✅ Reseller access removed for User ID <code>{target}</code>."
            try: await send_message(context.bot, int(target), "ℹ️ <b>Your reseller access has been removed by the admin.</b>")
            except Exception: pass
        save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id, result)
        await show_reseller_settings(context.bot, chat_id, 0)
        return

    if waiting == "daily_task_name" and is_admin(user_id):
        task_name = text.strip()
        if not task_name or len(task_name) > 60:
            await send_message(context.bot, chat_id, "❌ Task name must be between 1 and 60 characters. Please send a shorter name.")
            return
        data_store, day_data = daily_task_day_data()
        existing_ids = [int(t.get("id", 0)) for t in day_data.get("tasks", []) if isinstance(t, dict) and str(t.get("id", "")).isdigit()]
        task_id = str(max(existing_ids + [0]) + 1)
        s = load_json("settings.json")
        task = {"id": task_id, "name": task_name, "required": max(1, int(s.get("daily_task_games", 2) or 2)), "max_users": max(1, int(s.get("daily_task_max_users", 100) or 100)), "reward": max(0.0, float(s.get("daily_task_reward", 1.0) or 0)), "enabled": True, "users": {}, "participants": [], "rewarded_users": []}
        day_data.setdefault("tasks", []).append(task)
        data_store[daily_task_day_key()] = day_data
        save_json("daily_tasks.json", data_store)
        save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id,
            f"✅ <b>{html.escape(task_name)} created!</b>\n\n🎮 Games required: <b>{task['required']}</b>\n🎁 Reward: <b>₹{task['reward']:.2f}</b>\n👥 Maximum participants: <b>{task['max_users']}</b>\n\nUsers can accept this task separately from other tasks.")
        await send_admin_panel(context.bot, chat_id)
        return

    if waiting in ("daily_task_users", "daily_task_games") and is_admin(user_id):
        try:
            value = int(text.strip())
            if value < 1 or value > 1000000:
                raise ValueError
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Send a whole number between 1 and 1000000.")
            return
        s = load_json("settings.json")
        key = "daily_task_max_users" if waiting == "daily_task_users" else "daily_task_games"
        s[key] = value
        save_json("settings.json", s)
        save_temp(user_id, "waiting", "")
        label = "maximum rewarded users per day" if waiting == "daily_task_users" else "games required for Daily Task"
        await send_message(context.bot, chat_id, f"✅ Daily Task {label} set to <b>{value}</b>.")
        await send_admin_panel(context.bot, chat_id)
        return
    if waiting == "daily_task_reward" and is_admin(user_id):
        try:
            amount = float(text.strip())
            if amount < 0 or amount > 1000000:
                raise ValueError
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Send a valid reward amount from ₹0 to ₹1000000.")
            return
        s = load_json("settings.json")
        s["daily_task_reward"] = round(amount, 2)
        save_json("settings.json", s)
        save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id, f"✅ Daily Task reward set to <b>₹{amount:.2f}</b>.")
        await send_admin_panel(context.bot, chat_id)
        return

    if waiting in ("tt_cooldown", "rps_cooldown") and is_admin(user_id):
        try:
            hours = float(text.strip())
            if hours < 0 or hours > 8760:
                raise ValueError
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Send a number from 0 to 8760 hours, e.g. 24.")
            return
        s = load_json("settings.json")
        key = "tt_cooldown_hours" if waiting == "tt_cooldown" else "rps_cooldown_hours"
        s[key] = hours
        save_json("settings.json", s)
        save_temp(user_id, "waiting", "")
        game_name = "TicTacToe" if waiting == "tt_cooldown" else "Rock Paper Scissors"
        await send_message(context.bot, chat_id, f"✅ <b>{game_name} cooldown set to {hours:g} hour(s).</b>")
        await send_admin_panel(context.bot, chat_id)
        return
    if waiting in ("tt_min", "tt_max", "rps_min", "rps_max") and is_admin(user_id):
        try:
            amount = float(text.strip())
            if amount < 0 or amount > 1000000:
                raise ValueError
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Please send a valid non-negative amount, e.g. 0.25.")
            return
        s = load_json("settings.json")
        key_map = {"tt_min": ("tt_min_reward", "tt_max_reward", "TicTacToe minimum"),
                   "tt_max": ("tt_max_reward", "tt_min_reward", "TicTacToe maximum"),
                   "rps_min": ("rps_min_reward", "rps_max_reward", "Rock Paper Scissors minimum"),
                   "rps_max": ("rps_max_reward", "rps_min_reward", "Rock Paper Scissors maximum")}
        setting_key, other_key, label = key_map[waiting]
        other = float(s.get(other_key, 0.75 if other_key.endswith("max_reward") else 0.01))
        if waiting.endswith("_min") and amount > other:
            await send_message(context.bot, chat_id, f"❌ Minimum cannot be higher than current maximum ₹{other:.2f}.")
            return
        if waiting.endswith("_max") and amount < other:
            await send_message(context.bot, chat_id, f"❌ Maximum cannot be lower than current minimum ₹{other:.2f}.")
            return
        s[setting_key] = round(amount, 2)
        save_json("settings.json", s)
        save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id, f"✅ <b>{label} reward set to ₹{amount:.2f}.</b>")
        await send_admin_panel(context.bot, chat_id)
        return
    if waiting == "lucky_min" and is_admin(user_id):
        try: amount = float(text.strip())
        except ValueError: await send_message(context.bot, chat_id, "❌ Enter a valid amount."); return
        s=load_json("settings.json"); maximum=float(s.get("lucky_spin_max_reward",5.0))
        if amount < 0 or amount > maximum: await send_message(context.bot,chat_id,f"❌ Minimum must be between ₹0 and current maximum ₹{maximum:.2f}."); return
        s["lucky_spin_min_reward"]=round(amount,2); save_json("settings.json",s); save_temp(user_id,"waiting","")
        await send_message(context.bot,chat_id,f"✅ Lucky Spin minimum reward set to <b>₹{amount:.2f}</b>."); await send_admin_panel(context.bot,chat_id); return
    if waiting == "lucky_max" and is_admin(user_id):
        try: amount = float(text.strip())
        except ValueError: await send_message(context.bot, chat_id, "❌ Enter a valid amount."); return
        s=load_json("settings.json"); minimum=float(s.get("lucky_spin_min_reward",1.0))
        if amount < minimum: await send_message(context.bot,chat_id,f"❌ Maximum cannot be lower than current minimum ₹{minimum:.2f}."); return
        s["lucky_spin_max_reward"]=round(amount,2); save_json("settings.json",s); save_temp(user_id,"waiting","")
        await send_message(context.bot,chat_id,f"✅ Lucky Spin maximum reward set to <b>₹{amount:.2f}</b>."); await send_admin_panel(context.bot,chat_id); return
    if waiting == "claim_coupon":
        code=text.strip().upper(); coupons=load_json("coupons.json"); coupon=coupons.get(code)
        if not coupon: await send_message(context.bot, chat_id, "❌ <b>Invalid coupon code.</b>"); return
        expiry=parse_expiry(str(coupon.get("expires","")))
        if expiry and now_ist()>expiry: await send_message(context.bot, chat_id, "❌ <b>This coupon has expired.</b>"); return
        claims=coupon.setdefault("claims",[]); uid=str(user_id); max_claims=int(coupon.get("max_claims",1))
        if uid in claims: await send_message(context.bot, chat_id, "❌ <b>You have already claimed this coupon.</b>"); return
        if len(claims)>=max_claims: await send_message(context.bot, chat_id, "❌ <b>This coupon has reached its claim limit.</b>"); return
        amount=float(coupon.get("amount",0)); balances=load_json("balances.json"); balances[uid]=round(float(balances.get(uid,0) or 0)+amount,2); claims.append(uid); coupon["claims"]=claims; coupons[code]=coupon
        save_json("balances.json",balances); save_json("coupons.json",coupons)
        temp["waiting"]=""; temp_all[str(user_id)]=temp; save_json("temp.json",temp_all)
        await send_message(context.bot,chat_id,f"✅ <b>Coupon Claimed!</b>\n\n🎟️ Code: <code>{html.escape(code)}</code>\n💰 Added: <b>₹{amount:.2f}</b>\n💲 Balance: <b>₹{balances[uid]:.2f}</b>")
        u=load_json("users.json").get(uid,{})
        try: await send_message(context.bot,int(ADMIN_ID),f"🎟️ <b>Coupon Claimed</b>\n\n👤 {html.escape(str(u.get('name','User')))}\n🆔 <code>{user_id}</code>\n🔗 @{html.escape(str(u.get('username')))}\n🎟️ Code: <code>{html.escape(code)}</code>\n💰 Added: <b>₹{amount:.2f}</b>\n📊 Claims: <b>{len(claims)}/{max_claims}</b>")
        except Exception: pass
        return
    if waiting == "coupon_code" and is_admin(user_id):
        code=text.strip().upper(); coupons=load_json("coupons.json")
        if not code:
            await send_message(context.bot,chat_id,"❌ Invalid coupon code.")
            return
        if code in coupons:
            existing = coupons.get(code, {})
            claims = existing.get("claims", []) or []
            try:
                max_claims = int(existing.get("max_claims", 0))
            except Exception:
                max_claims = 0
            if len(claims) < max_claims:
                await send_message(context.bot,chat_id,"❌ This coupon code is already active and has not reached its claim limit.")
                return
        temp["coupon_code"]=code; temp["waiting"]="coupon_amount"; temp_all[str(user_id)]=temp; save_json("temp.json",temp_all); await send_message(context.bot,chat_id,"💰 <b>Coupon Amount</b>\n\nSend amount. Example: <code>100</code>"); return
    if waiting == "coupon_amount" and is_admin(user_id):
        try: amount=float(text.strip()); assert amount>0
        except: await send_message(context.bot,chat_id,"❌ Enter a valid amount greater than 0."); return
        temp["coupon_amount"]=amount; temp["waiting"]="coupon_max_claims"; temp_all[str(user_id)]=temp; save_json("temp.json",temp_all); await send_message(context.bot,chat_id,"👥 <b>Maximum Users</b>\n\nHow many users can claim it? Example: <code>10</code>"); return
    if waiting == "coupon_max_claims" and is_admin(user_id):
        try: mx=int(text.strip()); assert mx>0
        except: await send_message(context.bot,chat_id,"❌ Enter a whole number greater than 0."); return
        temp["coupon_max_claims"]=mx; temp["waiting"]="coupon_expiry"; temp_all[str(user_id)]=temp; save_json("temp.json",temp_all); await send_message(context.bot,chat_id,"📅 <b>Expiry Date & Time</b>\n\nUse <code>YYYY-MM-DD HH:MM</code>\nExample: <code>2026-10-01 23:59</code>\n\nOr tap <b>Skip</b> to create a coupon with no expiry.", btn([[('⏭️ Skip','coupon_skip_expiry')],[('❌Cancel','backadmin')]])); return
    if waiting == "coupon_expiry" and is_admin(user_id):
        expiry=parse_expiry(text.strip())
        if not expiry or expiry<=now_ist(): await send_message(context.bot,chat_id,"❌ Invalid or past expiry date."); return
        coupons=load_json("coupons.json"); code=temp["coupon_code"]; coupons[code]={"amount":temp["coupon_amount"],"max_claims":temp["coupon_max_claims"],"expires":expiry.astimezone(IST).strftime("%Y-%m-%d %H:%M"),"claims":[],"created":datetime.now().strftime("%Y-%m-%d %H:%M")}; save_json("coupons.json",coupons)
        for k in ("waiting","coupon_code","coupon_amount","coupon_max_claims"): temp[k]=""
        temp_all[str(user_id)]=temp; save_json("temp.json",temp_all); await send_message(context.bot,chat_id,f"✅ <b>Coupon Created!</b>\n\n🎟️ <code>{html.escape(code)}</code>\n💰 ₹{float(coupons[code]['amount']):.2f}\n👥 Max Claims: {coupons[code]['max_claims']}\n📅 Expires: {coupons[code]['expires']}"); await send_admin_panel(context.bot,chat_id); return

    if waiting == "search_order" and is_admin(user_id):
        order_id = text.strip()
        orders = load_json("orders.json")
        order = orders.get(order_id)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        if not order:
            await send_message(context.bot, chat_id, f"❌ <b>Order not found.</b>\n\nOrder ID: <code>{html.escape(order_id)}</code>")
            await send_admin_panel(context.bot, chat_id)
            return
        username = order.get("username", "")
        username_text = f"@{html.escape(str(username))}" if username else "No username"
        msg = (
            "📋 <b>ORDER DETAILS</b>\n\n"
            f"🔖 <b>Order ID:</b> <code>{html.escape(str(order_id))}</code>\n"
            f"👤 <b>Customer:</b> {html.escape(str(order.get('name','User')))}\n"
            f"🔗 <b>Username:</b> {username_text}\n"
            f"🆔 <b>User ID:</b> <code>{html.escape(str(order.get('user','')))}</code>\n"
            f"📦 <b>Product:</b> {html.escape(str(order.get('product_name','')))}\n"
            f"⏱️ <b>Plan:</b> {html.escape(str(order.get('duration','')))}\n"
            f"💰 <b>Price:</b> ₹{html.escape(str(order.get('price','')))}\n"
            f"📌 <b>Status:</b> {html.escape(str(order.get('status','')))}\n"
            f"🕐 <b>Date:</b> {html.escape(str(order.get('date','')))}\n"
            f"🔑 <b>Key:</b> <code>{html.escape(str(order.get('key','')))}</code>"
        )
        await send_message(context.bot, chat_id, msg)
        await send_admin_panel(context.bot, chat_id)

    elif waiting == "redeem_code" and not is_admin(user_id):
        redeem_code = text.strip()
        if not redeem_code:
            await send_message(context.bot, chat_id, "❌ Please send a valid redeem code.")
            return

        users.setdefault(str(user_id), {})
        users[str(user_id)].setdefault("name", update.effective_user.first_name or "User")
        users[str(user_id)]["username"] = update.effective_user.username or users[str(user_id)].get("username", "")
        users[str(user_id)].setdefault("join", datetime.now().strftime("%d %b %Y"))
        save_json("users.json", users)

        temp["waiting"] = ""
        temp["redeem_code"] = redeem_code
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)

        username = update.effective_user.username
        username_text = f"@{html.escape(username)}" if username else "No username"
        admin_msg = (
            "🔔 <b>New Redeem Code Request</b>\n\n"
            f"🔑 <b>Redeem Code:</b> <code>{html.escape(redeem_code)}</code>\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"👤 <b>Username:</b> {username_text}"
        )
        admin_kb = btn([
            [("✅ Accept", f"redeem_accept_{user_id}"), ("❌ Reject", f"redeem_reject_{user_id}")]
        ])
        try:
            await send_message(context.bot, int(ADMIN_ID), admin_msg, admin_kb)
        except Exception:
            await send_message(context.bot, chat_id, "❌ Could not send the redeem request to admin. Please try again.")
            return

        await send_message(context.bot, chat_id, "✅ <b>Your redeem code is sent to admin approval.</b>")

    elif waiting == "redeem_amount" and is_admin(user_id):
        target_id = str(temp.get("redeem_target", "")).strip()
        if not target_id:
            temp["waiting"] = ""
            temp_all[str(user_id)] = temp
            save_json("temp.json", temp_all)
            await send_message(context.bot, chat_id, "❌ Redeem request expired. Please try again.")
            return
        try:
            amount = float(text.strip())
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Enter a valid amount. Example: 1000")
            return
        if amount <= 0:
            await send_message(context.bot, chat_id, "❌ Amount must be greater than 0.")
            return

        balances = load_json("balances.json")
        old_balance = float(balances.get(target_id, 0) or 0)
        new_balance = old_balance + amount
        balances[target_id] = int(new_balance) if new_balance.is_integer() else round(new_balance, 2)
        save_json("balances.json", balances)
        await reward_referrer(context.bot, int(target_id), "balance")

        redeem_temp_all = load_json("temp.json")
        redeem_temp = redeem_temp_all.get(target_id, {})
        redeem_temp["redeem_code"] = ""
        redeem_temp["waiting"] = ""
        redeem_temp_all[target_id] = redeem_temp
        temp["waiting"] = ""
        temp["redeem_target"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        save_json("temp.json", redeem_temp_all)

        await send_message(
            context.bot, int(target_id),
            f"💰 <b>Balance Added!</b>\n\n₹{html.escape(str(amount))} has been added to your balance.\n💲 <b>New Balance: ₹{html.escape(str(balances[target_id]))}</b>"
        )
        await send_message(
            context.bot, chat_id,
            f"✅ <b>Balance Added Successfully</b>\n\nUser ID: <code>{html.escape(target_id)}</code>\n💰 Added: ₹{html.escape(str(amount))}\n💲 New Balance: ₹{html.escape(str(balances[target_id]))}"
        )

    elif waiting == "newcat" and is_admin(user_id):
        category_name = text.strip()
        if not category_name or len(category_name) > 50:
            await send_message(context.bot, chat_id, "❌ Send a category name between 1 and 50 characters.")
            return
        save_temp(user_id, "category_pending_name", category_name)
        save_temp(user_id, "waiting", "")
        await send_message(context.bot, chat_id,
            f"🎨 <b>Choose button style for {html.escape(category_name)}</b>",
            btn([[("🔴 Red", "catstyle_add_new_danger", "danger")],
                 [("🟢 Green", "catstyle_add_new_success", "success")],
                 [("🔵 Blue", "catstyle_add_new_primary", "primary")],
                 [("⚪ Default / Transparent", "catstyle_add_new_none")]]))
    elif waiting == "edit_category_name" and is_admin(user_id):
        category_name = text.strip()
        cid = temp.get("category_edit_id", "")
        categories_now = load_json("categories.json")
        if not category_name or len(category_name) > 50:
            await send_message(context.bot, chat_id, "❌ Send a category name between 1 and 50 characters.")
            return
        if cid not in categories_now:
            temp["waiting"] = ""
            temp_all[str(user_id)] = temp
            save_json("temp.json", temp_all)
            await send_message(context.bot, chat_id, "❌ Category not found. Open Category Management again.")
            return
        categories_now[cid]["name"] = category_name
        save_json("categories.json", categories_now)
        temp["waiting"] = ""
        temp["category_edit_id"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"✅ Category renamed to: <b>{html.escape(category_name)}</b>")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "prod_name" and is_admin(user_id):
        cid = temp.get("addprod_cat")
        pid = f"p{int(time.time())}"
        products[pid] = {"name": text, "cat": cid, "plans": [], "enabled": True, "video_file_id": ""}
        save_json("products.json", products)
        for k in ("waiting","prod_name","addprod_cat"):
            temp[k] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"✅ Product Add ho gaya!\n\nName: {html.escape(text)}\n\nAb /admin se '➕ Add Plan' karke plans add karo.")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "plan_duration" and is_admin(user_id):
        try:
            duration = normalize_duration(text)
        except ValueError:
            await send_message(context.bot, chat_id, "❌ Duration empty aayirikkaruthu. Example: 1 hour")
            return
        temp["plan_duration"] = duration
        temp["waiting"] = "plan_price"
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, "💰 <b>Is plan ka Price kya hai?</b>\n\nExample: 90")
    elif waiting == "plan_price" and is_admin(user_id):
        pid = temp["addplan_pid"]
        duration = normalize_duration(temp["plan_duration"])
        price = int(text)
        products = load_json("products.json")
        products[pid].setdefault("plans", []).append({"duration": duration, "price": price, "keys": []})
        save_json("products.json", products)
        for k in ("waiting","plan_duration","addplan_pid"):
            temp[k] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"✅ Plan Add Ho Gaya!\n\nDuration: {html.escape(duration)}\nPrice: ₹{price}\n\nAb is plan ke liye keys add karo!\n/admin se '🔑 Add Plan Keys' select karo.")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "add_plan_keys" and is_admin(user_id):
        keys = [x.strip() for x in text.splitlines() if x.strip()]
        if not keys:
            await send_message(context.bot, chat_id, "❌ Koi key nahi mili. Dubara keys bhejo")
            return
        pid = temp["addkeys_pid"]
        idx = int(temp["addkeys_plan_index"])
        products = load_json("products.json")
        products[pid]["plans"][idx].setdefault("keys", []).extend(keys)
        save_json("products.json", products)
        temp["waiting"] = ""
        temp["addkeys_pid"] = ""
        temp["addkeys_plan_index"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        plan = products[pid]["plans"][idx]
        await send_message(context.bot, chat_id, f"✅ {len(keys)} Keys Add Ho Gayi!\n\nPlan: {duration_text(plan)}\nTotal Keys: {len(plan['keys'])}")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "edit_name" and is_admin(user_id):
        pid = temp["edit_pid"]
        products[pid]["name"] = text
        save_json("products.json", products)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"✅ Name Update: {html.escape(text)}")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "edit_plan_duration" and is_admin(user_id):
        pid, idx = temp["edit_pid"], int(temp["edit_plan_index"])
        products = load_json("products.json")
        products[pid]["plans"][idx]["duration"] = normalize_duration(text)
        save_json("products.json", products)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"✅ Duration Update: {html.escape(text)}")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "edit_plan_price" and is_admin(user_id):
        pid, idx = temp["edit_pid"], int(temp["edit_plan_index"])
        products = load_json("products.json")
        products[pid]["plans"][idx]["price"] = int(text)
        save_json("products.json", products)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"✅ Price Update: ₹{html.escape(text)}")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "edit_plan_keys" and is_admin(user_id):
        keys = [x.strip() for x in text.splitlines() if x.strip()]
        if not keys:
            await send_message(context.bot, chat_id, "❌ Koi key nahi mili. Dubara keys bhejo")
            return
        pid, idx = temp["edit_pid"], int(temp["edit_plan_index"])
        products = load_json("products.json")
        products[pid]["plans"][idx].setdefault("keys", []).extend(keys)
        save_json("products.json", products)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        plan = products[pid]["plans"][idx]
        await send_message(context.bot, chat_id, f"✅ {len(keys)} Keys Add Ho Gayi!\n\nPlan: {duration_text(plan)}\nTotal Keys: {len(plan['keys'])}")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "broadcast_text" and is_admin(user_id):
        sent, failed, unreachable = await broadcast_to_users(
            context.bot,
            users.keys(),
            chat_id,
            msg_obj.message_id,
        )
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, broadcast_report(len(users), sent, failed, unreachable))
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "adduserbal_id" and is_admin(user_id):
        target = text.strip()
        if target not in users:
            await send_message(context.bot, chat_id, f"❌ User ID <code>{html.escape(target)}</code> nahi mila!", btn([[("Back","backadmin")]]))
            return
        temp["adduserbal_target"] = target
        temp["waiting"] = "adduserbal_amount"
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"💰 <b>Add Balance to {html.escape(str(users[target]['name']))}</b>\n\nKitna amount add karna hai?\n\nExample: 100", btn([[("❌Cancel","backadmin")]]))
    elif waiting == "adduserbal_amount" and is_admin(user_id):
        target = temp["adduserbal_target"]
        amount = int(text)
        if amount <= 0:
            await send_message(context.bot, chat_id, "❌ Amount 0 se zyada hona chahiye!")
            return
        balances = load_json("balances.json")
        balances[target] = balances.get(target, 0) + amount
        save_json("balances.json", balances)
        temp["waiting"] = ""
        temp["adduserbal_target"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"✅ <b>Balance Added!</b>\n\nUser: {html.escape(str(users[target]['name']))}\n🆔 <code>{target}</code>\n💰 Added: ₹{amount}\n💲 New Balance: ₹{balances[target]}")
        try:
            await send_message(context.bot, int(target), f"💰 <b>Balance Added!</b>\n\n₹{amount} aapke account me add kar diya gaya hai.\n💲 <b>New Balance: ₹{balances[target]}</b>")
        except Exception:
            pass
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "order_channel" and is_admin(user_id):
        channel_id = text.strip()
        if not channel_id.startswith("-100"):
            await send_message(context.bot, chat_id, "❌ Invalid Channel ID. Example: <code>-1004301332161</code>")
            return
        settings["order_channel_id"] = channel_id
        save_json("settings.json", settings)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, f"✅ <b>Order Channel ID Updated!</b>\n\nChannel: <code>{html.escape(channel_id)}</code>\n\nBot must be admin with <b>Post Messages</b> permission.")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "maintenance_message" and is_admin(user_id):
        settings = load_json("settings.json")
        # Preserve Telegram formatting as HTML entities (bold, italic, quotes, links, etc.).
        maintenance_text = msg_obj.text_html if getattr(msg_obj, "entities", None) else text
        if not maintenance_text.strip():
            await send_message(context.bot, chat_id, "❌ Maintenance message cannot be empty. Send the message again.")
            return
        settings["maintenance_message"] = maintenance_text
        save_json("settings.json", settings)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, "✅ <b>Maintenance Message Updated!</b>\n\nTelegram text formatting will be preserved when users start the bot during maintenance.")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "start_menu_button_name" and is_admin(user_id):
        key = temp.get("start_menu_button_key", "")
        new_name = text.strip()
        if key not in START_MENU_BUTTON_DEFAULTS or not new_name or len(new_name) > 64:
            await send_message(context.bot, chat_id, "❌ Invalid button name. Send 1–64 characters.")
            return
        st = load_json("settings.json")
        st.setdefault("start_menu_buttons", {}).setdefault(key, {})["text"] = new_name
        save_json("settings.json", st)
        temp["waiting"] = ""
        temp.pop("start_menu_button_key", None)
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, "✅ <b>Start menu button name updated!</b>")
        await send_admin_panel(context.bot, chat_id)
    elif waiting == "start_menu_template" and is_admin(user_id):
        settings = load_json("settings.json")
        temp_all = load_json("temp.json")
        # Telegram clients may send formatting as Message entities rather than
        # literal HTML. Convert those entities to HTML before saving; if the admin
        # typed raw HTML directly, keep that source unchanged.
        template = msg_obj.text_html if getattr(msg_obj, "entities", None) else text
        # Validate Telegram HTML before saving so a broken template cannot break /start.
        import re
        probe = re.sub(r"\[(?:FIRST_NAME|SECOND_NAME|USERNAME|BALANCE|USER_ID)\]", "VALUE", template)
        try:
            from html.parser import HTMLParser
            class _TemplateHTMLValidator(HTMLParser):
                def error(self, message):
                    raise ValueError(message)
            _TemplateHTMLValidator(convert_charrefs=True).feed(probe)
        except Exception:
            await send_message(context.bot, chat_id, "❌ Invalid HTML formatting. Please check your tags and send again.")
            return
        settings["start_menu_template"] = template
        settings.pop("start_menu_media", None)
        save_json("settings.json", settings)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        await send_message(context.bot, chat_id, "✅ <b>Start Menu Updated Successfully!</b>\n\nThe variables will be replaced with each user's details. Formatting around variables will be preserved.")
        await send_admin_panel(context.bot, chat_id)
    elif waiting in ("proof","howto","support","download") and is_admin(user_id):
        key = {"proof":"proof_link","howto":"howto_link","support":"support_user","download":"download_link"}[waiting]
        settings[key] = text.strip()
        save_json("settings.json", settings)
        temp["waiting"] = ""
        temp_all[str(user_id)] = temp
        save_json("temp.json", temp_all)
        reply = f"✅ {key.replace('_',' ').title()} Update: {html.escape(text)}"
        await send_message(context.bot, chat_id, reply)
        await send_admin_panel(context.bot, chat_id)

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user_id = update.effective_user.id
    msg = update.message
    temp_user = get_temp(user_id)
    if temp_user.get("waiting") == "ticket_issue" and not is_admin(user_id):
        await submit_ticket_message(update, context)
        return
    if is_admin(user_id) and context.user_data.get("ticket_reply_id"):
        tid = str(context.user_data.pop("ticket_reply_id"))
        ticket = load_json("tickets.json").get(tid)
        if not ticket:
            await send_message(context.bot, update.effective_chat.id, "Ticket not found.")
            return
        try:
            await context.bot.send_message(chat_id=int(ticket["user_id"]), text=f"📩 SUPPORT REPLY — TICKET #{html.escape(tid)}")
            await context.bot.copy_message(chat_id=int(ticket["user_id"]), from_chat_id=update.effective_chat.id, message_id=msg.message_id)
            ticket["reply"] = msg.caption or "Media reply sent" 
            ticket["replied_at"] = time.time()
            tickets = load_json("tickets.json")
            tickets[tid] = ticket
            save_json("tickets.json", tickets)
            await send_message(context.bot, update.effective_chat.id, f"✅ Reply sent privately to the user for Ticket #{html.escape(tid)}.")
        except Exception as exc:
            context.user_data["ticket_reply_id"] = tid
            await send_message(context.bot, update.effective_chat.id, f"❌ Could not send reply: {html.escape(str(exc)[:200])}")
        return
    if not is_admin(user_id):
        return
    temp = get_temp(user_id)
    waiting = temp.get("waiting") or context.user_data.get("auto_bc_waiting", "")
    if is_admin(user_id) and waiting == "auto_bc_channel":
        await handle_auto_bc_forwarded_channel(update, context)
        return
    if waiting == "start_menu_template":
        media_type = None
        file_id = None
        if msg.photo:
            media_type, file_id = "photo", msg.photo[-1].file_id
        elif msg.video:
            media_type, file_id = "video", msg.video.file_id
        elif msg.animation:
            media_type, file_id = "animation", msg.animation.file_id
        if not media_type:
            await send_message(context.bot, update.effective_chat.id,
                "Please send a photo, video, or GIF with an optional caption. To use text-only Start Menu, send text instead.")
            return
        caption_template = msg.caption_html if getattr(msg, "caption_entities", None) else (msg.caption or "")
        settings = load_json("settings.json")
        settings["start_menu_template"] = caption_template
        settings["start_menu_media"] = {"type": media_type, "file_id": file_id, "caption": caption_template}
        save_json("settings.json", settings)
        all_temp = load_json("temp.json")
        temp = all_temp.get(str(user_id), {})
        temp["waiting"] = ""
        all_temp[str(user_id)] = temp
        save_json("temp.json", all_temp)
        await send_message(context.bot, update.effective_chat.id,
            "✅ <b>Start Menu Media Updated!</b>\n\nThe photo/video and its caption formatting have been saved. All Telegram caption formatting and variables will be preserved.")
        await send_admin_panel(context.bot, update.effective_chat.id)
        return
    if waiting == "auto_bc_bot_add_message":
        item_type = "message"
        if msg.video: item_type = "video"
        elif msg.photo: item_type = "photo"
        elif msg.document: item_type = "document"
        elif msg.audio: item_type = "audio"
        elif msg.voice: item_type = "voice"
        elif msg.animation: item_type = "animation"
        s = load_json("settings.json"); cfg = s.setdefault("auto_broadcast_bot", {"enabled": False, "interval": "10M", "items": [], "index": 0, "next_at": 0})
        cfg.setdefault("items", []).append({"chat_id": int(update.effective_chat.id), "message_id": int(msg.message_id), "type": item_type})
        s["auto_broadcast_bot"] = cfg; save_json("settings.json", s)
        await send_message(context.bot, update.effective_chat.id, f"Bot broadcast message saved. Total: <b>{len(cfg['items'])}</b>.", btn([[ ("Done", "auto_bc_bot_home") ]]))
        return
    if waiting == "auto_bc_add_message":
        item_type = "message"
        if msg.video: item_type = "video"
        elif msg.photo: item_type = "photo"
        elif msg.document: item_type = "document"
        elif msg.audio: item_type = "audio"
        elif msg.voice: item_type = "voice"
        elif msg.animation: item_type = "animation"
        s = load_json("settings.json"); channels = auto_bc_channels(s)
        target = str(temp.get("auto_bc_target", s.get("auto_broadcast_selected_channel", "")))
        channel = channels.get(target)
        if not channel:
            await send_message(context.bot, update.effective_chat.id, "Select a verified channel before adding messages."); return
        channel.setdefault("items", []).append({"chat_id": int(update.effective_chat.id), "message_id": int(msg.message_id), "type": item_type})
        channels[target] = channel; s["auto_broadcast_channels"] = channels; save_json("settings.json", s)
        await send_message(context.bot, update.effective_chat.id,
            f"Message added to <b>{html.escape(str(channel.get('title') or target))}</b>. Total: <b>{len(channel['items'])}</b>. Send another message or press Done.",
            btn([[ ("Done", f"auto_bc_open_{target}") ]]))
        return
    if waiting == "edit_product_video":
        message = update.message
        if not message.video:
            await send_message(context.bot, update.effective_chat.id, "❌ Please send a video file.", btn([[ ("❌Cancel", "backadmin") ]]))
            return
        pid = temp.get("edit_pid")
        products = load_json("products.json")
        if not pid or pid not in products:
            return
        products[pid]["video_file_id"] = message.video.file_id
        save_json("products.json", products)
        temp["waiting"] = ""
        all_temp=load_json("temp.json"); all_temp[str(user_id)]=temp; save_json("temp.json",all_temp)
        await send_message(context.bot, update.effective_chat.id, "✅ <b>Product Video Added Successfully!</b>\n\nThe existing product text will be the video caption, with the plan buttons underneath.")
        await send_admin_panel(context.bot, update.effective_chat.id)
        return
    if waiting != "broadcast_text":
        return

    message = update.message
    users = load_json("users.json")
    caption = message.caption or ""
    kind = None
    file_id = None

    if message.photo:
        kind, file_id = "photo", message.photo[-1].file_id
    elif message.video:
        kind, file_id = "video", message.video.file_id
    elif message.voice:
        kind, file_id = "voice", message.voice.file_id
    elif message.document:
        kind, file_id = "document", message.document.file_id

    if not kind:
        return

    sent, failed, unreachable = await broadcast_to_users(
        context.bot,
        users.keys(),
        update.effective_chat.id,
        message.message_id,
    )
    all_temp = load_json("temp.json")
    all_temp.setdefault(str(user_id), {})["waiting"] = ""
    save_json("temp.json", all_temp)

    await send_message(context.bot, update.effective_chat.id, broadcast_report(len(users), sent, failed, unreachable))
    await send_admin_panel(context.bot, update.effective_chat.id)

# ============================================================
# COMMANDS / ENTRY POINT
# ============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if not is_admin(user_id) and not load_json("settings.json").get("bot_enabled", True):
        settings = load_json("settings.json")
        maintenance_text = settings.get("maintenance_message") or DEFAULT_SETTINGS["maintenance_message"]
        await send_message(context.bot, update.effective_chat.id, maintenance_text)
        return

    # Telegram deep-link routing. Examples:
    #   /start product_p35  -> opens product p35
    #   /start plan_p35_0   -> opens the first plan of product p35
    if context.args:
        start_arg = str(context.args[0]).strip()
        if start_arg.startswith("product_"):
            pid = start_arg[len("product_"):].strip()
            products = load_json("products.json")
            product = products.get(pid)
            if product:
                if not product.get("enabled", True):
                    await send_message(context.bot, update.effective_chat.id, "🛠️ <b>This Product Is Under Maintaince</b>")
                    return
                # Ensure user is registered/balance exists, then jump straight to the product.
                balances = load_json("balances.json")
                users = load_json("users.json")
                balances.setdefault(str(user_id), 0)
                if str(user_id) not in users:
                    users[str(user_id)] = {
                        "name": user.first_name or "User",
                        "username": user.username or "",
                        "join": datetime.now().strftime("%d %b %Y"),
                        "referrer": "", "referral_rewards": {}, "referrals": [], "referral_earned": 0.0
                    }
                    save_json("users.json", users)
                save_json("balances.json", balances)
                await send_product_plans(context.bot, update.effective_chat.id, 0, pid, user_id)
                return

        if start_arg.startswith("plan_"):
            parts = start_arg.split("_")
            if len(parts) == 3:
                pid = parts[1]
                try:
                    plan_index = int(parts[2])
                except ValueError:
                    plan_index = -1
                products = load_json("products.json")
                product = products.get(pid)
                if product and 0 <= plan_index < len(product.get("plans", [])):
                    if not product.get("enabled", True):
                        await send_message(context.bot, update.effective_chat.id, "🛠️ <b>This Product Is Under Maintaince</b>")
                        return
                    balances = load_json("balances.json")
                    balances.setdefault(str(user_id), 0)
                    save_json("balances.json", balances)
                    # Show the product plan screen; the exact plan remains selected by the button flow.
                    await send_product_plans(context.bot, update.effective_chat.id, 0, pid, user_id)
                    return

    balances = load_json("balances.json")
    users = load_json("users.json")

    balances.setdefault(str(user_id), 0)
    if str(user_id) not in users:
        referrer = ""
        if context.args:
            arg = str(context.args[0]).strip()
            if arg.startswith("ref_"):
                arg = arg[4:]
            if arg.isdigit() and arg != str(user_id) and arg in users:
                referrer = arg
        users[str(user_id)] = {
            "name": user.first_name or "User",
            "username": user.username or "",
            "join": datetime.now().strftime("%d %b %Y"),
            "referrer": referrer,
            "referral_rewards": {},
            "referrals": [],
            "referral_earned": 0.0
        }
        save_json("users.json", users)
        if referrer:
            ref_user = users.get(referrer, {})
            ref_user.setdefault("referrals", [])
            if str(user_id) not in ref_user["referrals"]:
                ref_user["referrals"].append(str(user_id))
            users[referrer] = ref_user
            save_json("users.json", users)
            await reward_referrer(context.bot, user_id, "invite")
    save_json("balances.json", balances)
    await send_main_menu(context.bot, update.effective_chat.id, user.first_name or "User", balances[str(user_id)], telegram_user=user)

async def restartgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await send_message(context.bot, update.effective_chat.id, "❌ Only admin can use /restartgame.")
        return
    for filename in (TT_FILE, RPS_FILE):
        games = load_json(filename)
        for game in games.values():
            if isinstance(game, dict):
                game["last_play"] = 0
        save_json(filename, games)
    await send_message(context.bot, update.effective_chat.id,
        "✅ <b>Game cooldowns reset!</b>\n\nAll users can play both TicTacToe and Rock Paper Scissors again now.\nBalances and rewards were not changed.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await send_message(context.bot, update.effective_chat.id, "❌Only admin")
        return
    await send_admin_panel(context.bot, update.effective_chat.id)


# ============================================================
# SEPARATE RESELLER PANEL BOT (shares the same JSON data directory)
# ============================================================
def reseller_panel_keyboard(digits="", step="id"):
    shown = ("•" * len(digits)) if step == "password" else (digits or "—")
    rows = [
        [InlineKeyboardButton("1", callback_data="rp_d_1", style="primary"), InlineKeyboardButton("2", callback_data="rp_d_2", style="primary"), InlineKeyboardButton("3", callback_data="rp_d_3", style="primary")],
        [InlineKeyboardButton("4", callback_data="rp_d_4", style="primary"), InlineKeyboardButton("5", callback_data="rp_d_5", style="primary"), InlineKeyboardButton("6", callback_data="rp_d_6", style="primary")],
        [InlineKeyboardButton("7", callback_data="rp_d_7", style="primary"), InlineKeyboardButton("8", callback_data="rp_d_8", style="primary"), InlineKeyboardButton("9", callback_data="rp_d_9", style="primary")],
        [InlineKeyboardButton("Delete", callback_data="rp_del", style="danger"), InlineKeyboardButton("0", callback_data="rp_d_0", style="primary"), InlineKeyboardButton("OK", callback_data="rp_ok", style="success")],
        [InlineKeyboardButton("❌Cancel", callback_data="rp_cancel", style="danger")],
    ]
    title = "Reseller ID" if step == "id" else "Password"
    return f"<b>Enter your {title} using the dial pad.</b>\n\n<b>{title}:</b> <code>{shown}</code>", InlineKeyboardMarkup(rows)

async def reseller_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Keep a separate list of people who have opened the Reseller Panel bot,
    # so reseller broadcasts never target Shop Bot-only users.
    panel_users = load_json("reseller_panel_users.json")
    panel_users[str(update.effective_user.id)] = {
        "name": update.effective_user.first_name or "User",
        "username": update.effective_user.username or "",
        "last_seen": int(time.time()),
    }
    save_json("reseller_panel_users.json", panel_users)
    # Keep the reseller signed in on this Telegram account until the paid plan expires.
    uid = str(update.effective_user.id)
    users = load_json("users.json")
    info = users.get(uid, {}).get("reseller", {}) if isinstance(users.get(uid, {}), dict) else {}
    if not is_admin(update.effective_user.id) and info.get("panel_logged_in") and reseller_is_active(uid):
        context.user_data["rp_logged_in"] = True
        context.user_data.pop("rp_login", None)
        context.user_data.pop("rp_pending_buy", None)
        await update.effective_message.reply_text(
            f"<b>TURBO RESELLER PANEL</b>\n\nWelcome back!\n\nAvailable balance: <b>₹{_reseller_balance(uid):.2f}</b>",
            parse_mode="HTML", reply_markup=_reseller_home_markup()
        )
        return
    if is_admin(update.effective_user.id):
        await update.effective_message.reply_text(
            "<b>TURBO RESELLER ADMIN PANEL</b>\n\nChoose an admin action.",
            parse_mode="HTML", reply_markup=_reseller_admin_markup()
        )
        return
    context.user_data.pop("rp_pending_buy", None)
    context.user_data["rp_login"] = {"step": "id", "digits": ""}
    text, markup = reseller_panel_keyboard()
    await update.effective_message.reply_text(
        "<b>TURBO RESELLER PANEL</b>\n\n" + text,
        parse_mode="HTML", reply_markup=markup
    )


def _reseller_home_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("View Products", callback_data="rp_products", style="primary")],
        [InlineKeyboardButton("My Balance", callback_data="rp_balance", style="success"),
         InlineKeyboardButton("Add Balance", callback_data="rp_request_balance", style="success")],
        [InlineKeyboardButton("Logout", callback_data="rp_logout", style="danger")],
    ])


def _reseller_discount():
    try:
        return max(0.0, min(90.0, float(load_json("settings.json").get("reseller_discount_percent", 50))))
    except (TypeError, ValueError):
        return 50.0


def _reseller_balance(uid):
    """Reseller Panel reads the same wallet used by the Shop Bot."""
    return round(float(load_json("balances.json").get(str(uid), 0) or 0), 2)


def _reseller_require_login(context, uid):
    users = load_json("users.json")
    info = users.get(str(uid), {}).get("reseller", {}) if isinstance(users.get(str(uid), {}), dict) else {}
    active = reseller_is_active(uid)
    if active and info.get("panel_logged_in"):
        context.user_data["rp_logged_in"] = True
    return bool(context.user_data.get("rp_logged_in") and active and info.get("panel_logged_in"))


async def reseller_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    data = q.data or ""
    shop_link = str(load_json("settings.json").get("shop_bot_link") or "https://t.me/TurboPaidPanelStoreBot")

    if data == "rp_cancel":
        context.user_data.pop("rp_login", None)
        context.user_data.pop("rp_logged_in", None)
        await q.edit_message_text("Login cancelled. Send /start to try again.")
        return

    if data == "rp_logout":
        context.user_data.pop("rp_login", None)
        context.user_data.pop("rp_logged_in", None)
        context.user_data.pop("rp_pending_buy", None)
        users = load_json("users.json")
        row = users.get(uid, {}) if isinstance(users.get(uid, {}), dict) else {}
        info = row.get("reseller", {}) if isinstance(row.get("reseller", {}), dict) else {}
        info["panel_logged_in"] = False
        row["reseller"] = info
        users[uid] = row
        save_json("users.json", users)
        await q.edit_message_text("You have been logged out. Send /start to log in again.")
        return

    # Shop Bot and Reseller Panel use the same balances.json wallet.
    if data == "rp_admin_home":
        if not is_admin(q.from_user.id):
            await q.edit_message_text("Admin access only.")
            return
        await q.edit_message_text("<b>TURBO RESELLER ADMIN PANEL</b>\n\nChoose an admin action.", parse_mode="HTML", reply_markup=_reseller_admin_markup())
        return

    if data == "rp_admin_stats":
        if not is_admin(q.from_user.id):
            await q.edit_message_text("Admin access only.")
            return
        users = load_json("users.json")
        resellers = [uid for uid, row in users.items() if isinstance(row, dict) and isinstance(row.get("reseller"), dict) and row["reseller"].get("active")]
        wallets = load_json("balances.json")
        total = round(sum(float(v or 0) for v in wallets.values()), 2)
        await q.edit_message_text(f"<b>RESELLER PANEL STATS</b>\n\nActive reseller accounts: <b>{len(resellers)}</b>\nWallets with balance: <b>{sum(1 for v in wallets.values() if float(v or 0) > 0)}</b>\nTotal shared balance of listed users: <b>₹{total:.2f}</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Admin Panel", callback_data="rp_admin_home", style="danger")]]))
        return

    if data in ("rp_admin_add_balance", "rp_admin_deduct_balance"):
        if not is_admin(q.from_user.id):
            await q.edit_message_text("Admin access only.")
            return
        context.user_data["rp_admin_action"] = "add_balance" if data == "rp_admin_add_balance" else "deduct_balance"
        action_label = "ADD" if data == "rp_admin_add_balance" else "DEDUCT"
        await q.edit_message_text(f"<b>{action_label} RESELLER BALANCE</b>\n\nSend one message in this format:\n<code>USER_ID AMOUNT</code>\n\nExample: <code>123456789 100</code>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌Cancel", callback_data="rp_admin_home", style="danger")]]))
        return

    if data == "rp_admin_resellers":
        if not is_admin(q.from_user.id):
            await q.edit_message_text("Admin access only.")
            return
        users = load_json("users.json")
        rows = []
        lines = ["<b>RESELLER ACCOUNTS</b>", ""]
        for rid, row in users.items():
            if not isinstance(row, dict):
                continue
            info = row.get("reseller", {})
            if isinstance(info, dict) and info.get("active"):
                lines.append(f"ID: <code>{html.escape(str(rid))}</code> | Shared balance: <b>₹{_reseller_balance(rid):.2f}</b>")
        if len(lines) == 2:
            lines.append("No active reseller accounts found.")
        await q.edit_message_text("\n".join(lines)[:3900], parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Admin Panel", callback_data="rp_admin_home", style="danger")]]))
        return

    if data == "rp_admin_discount":
        if not is_admin(q.from_user.id):
            await q.edit_message_text("Admin access only.")
            return
        context.user_data["rp_admin_action"] = "discount"
        await q.edit_message_text(f"<b>SET RESELLER DISCOUNT</b>\n\nCurrent discount: <b>{_reseller_discount():g}%</b>\nSend a percentage from 0 to 90.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌Cancel", callback_data="rp_admin_home", style="danger")]]))
        return

    if data == "rp_admin_broadcast":
        if not is_admin(q.from_user.id):
            await q.edit_message_text("Admin access only.")
            return
        context.user_data["rp_admin_action"] = "broadcast"
        await q.edit_message_text("<b>RESELLER PANEL BROADCAST</b>\n\nSend the message to broadcast to users who have opened the Reseller Panel bot.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌Cancel", callback_data="rp_admin_home", style="danger")]]))
        return

    if data == "rp_request_balance":
        if not _reseller_require_login(context, uid):
            await q.edit_message_text("Please log in with an active reseller account first. Send /start.")
            return
        try:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=f"Reseller balance request\nUser ID: {uid}\nCurrent shared balance: ₹{_reseller_balance(uid):.2f}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Add Balance", callback_data=f"rp_admin_add_for_{uid}", style="success")]]))
        except Exception:
            pass
        await q.edit_message_text("<b>Balance request sent to admin.</b>\nYour Shop Bot and Reseller Panel use the same shared balance.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Panel", callback_data="rp_home", style="danger")]]))
        return

    if data.startswith("rp_admin_add_for_"):
        if not is_admin(q.from_user.id):
            await q.edit_message_text("Admin access only.")
            return
        target_uid = data[len("rp_admin_add_for_"):]
        context.user_data["rp_admin_action"] = "add_balance_target"
        context.user_data["rp_admin_target"] = target_uid
        await q.edit_message_text(f"Send the amount to add to reseller user <code>{html.escape(target_uid)}</code>.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌Cancel", callback_data="rp_admin_home", style="danger")]]))
        return

    if data == "rp_balance":
        if not _reseller_require_login(context, uid):
            await q.edit_message_text("Please log in with an active reseller account first. Send /start.")
            return
        bal = _reseller_balance(uid)
        await q.edit_message_text(
            f"<b>MY RESELLER BALANCE</b>\n\n"
            f"Available balance: <b>₹{bal:.2f}</b>\n\n"
            "This is your shared Turbo balance. The same balance is available in the Shop Bot and Reseller Panel.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Refresh Balance", callback_data="rp_balance", style="primary")],
                [InlineKeyboardButton("Add Balance", callback_data="rp_request_balance", style="success")],
                [InlineKeyboardButton("Back to Panel", callback_data="rp_home", style="danger")],
            ])
        )
        return

    if data == "rp_home":
        if not _reseller_require_login(context, uid):
            await q.edit_message_text("Please log in with an active reseller account first. Send /start.")
            return
        await q.edit_message_text(
            f"<b>TURBO RESELLER PANEL</b>\n\nBalance: <b>₹{_reseller_balance(uid):.2f}</b>\n\nSelect an option.",
            parse_mode="HTML", reply_markup=_reseller_home_markup()
        )
        return

    if data == "rp_products":
        if not _reseller_require_login(context, uid):
            await q.edit_message_text("Please log in with an active reseller account first. Send /start.")
            return
        products = load_json("products.json")
        discount = _reseller_discount()
        rows = []
        for pid, prod in products.items():
            if not isinstance(prod, dict) or not prod.get("enabled", True):
                continue
            rows.append([InlineKeyboardButton(str(prod.get("name", pid))[:55], callback_data=f"rp_product_{pid}", style="primary")])
        rows.extend([
            [InlineKeyboardButton(f"My Balance: ₹{_reseller_balance(uid):.2f}", callback_data="rp_balance", style="success")],
            [InlineKeyboardButton("Add Balance", callback_data="rp_request_balance", style="success")],
            [InlineKeyboardButton("Back to Panel", callback_data="rp_home", style="danger")],
        ])
        await q.edit_message_text(
            f"<b>RESELLER PRODUCTS</b>\n\nAll listed prices include your <b>{discount:g}% reseller discount</b>.\n"
            f"Available balance: <b>₹{_reseller_balance(uid):.2f}</b>\n\nSelect a product.",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows)
        )
        return

    if data.startswith("rp_product_"):
        if not _reseller_require_login(context, uid):
            await q.edit_message_text("Please log in with an active reseller account first. Send /start.")
            return
        pid = data[len("rp_product_"):]
        products = load_json("products.json")
        prod = products.get(pid)
        if not isinstance(prod, dict) or not prod.get("enabled", True):
            await q.edit_message_text("Product not found or unavailable.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Products", callback_data="rp_products", style="danger")]]))
            return
        discount = _reseller_discount()
        lines = [f"<b>{html.escape(str(prod.get('name', 'Product')))}</b>",
                 f"Your discount: <b>{discount:g}%</b>",
                 f"Your balance: <b>₹{_reseller_balance(uid):.2f}</b>", "", "Select a plan to purchase:"]
        rows = []
        for idx, plan in enumerate(prod.get("plans", [])):
            original = float(plan.get("price", 0) or 0)
            sale = round(original * (100.0 - discount) / 100.0, 2)
            stock = len(plan.get("keys", []))
            lines.append(f"• {html.escape(duration_text(plan))}: <b>₹{sale:.2f}</b> <s>₹{original:.2f}</s> — Stock: {stock}")
            rows.append([InlineKeyboardButton(f"Buy {duration_text(plan)} — ₹{sale:.2f}", callback_data=f"rp_select_{pid}_{idx}", style="success")])
        rows.extend([
            [InlineKeyboardButton("My Balance", callback_data="rp_balance", style="primary"), InlineKeyboardButton("Add Balance", callback_data="rp_request_balance", style="success")],
            [InlineKeyboardButton("Back to Products", callback_data="rp_products", style="danger")],
        ])
        await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("rp_select_"):
        if not _reseller_require_login(context, uid):
            await q.edit_message_text("Please log in with an active reseller account first. Send /start.")
            return
        try:
            payload = data[len("rp_select_"):]
            pid, index_text = payload.rsplit("_", 1)
            index = int(index_text)
            prod = load_json("products.json").get(pid)
            plan = prod["plans"][index]
            sale = round(float(plan.get("price", 0) or 0) * (100.0 - _reseller_discount()) / 100.0, 2)
        except Exception:
            await q.edit_message_text("That plan is no longer available.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Products", callback_data="rp_products", style="danger")]]))
            return
        context.user_data["rp_pending_buy"] = {"pid": pid, "index": index}
        await q.edit_message_text(
            f"<b>Confirm Reseller Purchase</b>\n\nProduct: <b>{html.escape(str(prod.get('name', 'Product')))}</b>\n"
            f"Plan: <b>{html.escape(duration_text(plan))}</b>\nPrice after discount: <b>₹{sale:.2f}</b>\n"
            f"Current balance: <b>₹{_reseller_balance(uid):.2f}</b>\n\nConfirm purchase?",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Confirm & Buy", callback_data=f"rp_confirm_{pid}_{index}", style="success")],
                [InlineKeyboardButton("❌Cancel", callback_data=f"rp_product_{pid}", style="danger")],
            ])
        )
        return

    if data.startswith("rp_confirm_"):
        if not _reseller_require_login(context, uid):
            await q.edit_message_text("Please log in with an active reseller account first. Send /start.")
            return
        try:
            payload = data[len("rp_confirm_"):]
            pid, index_text = payload.rsplit("_", 1)
            index = int(index_text)
        except Exception:
            await q.edit_message_text("Invalid purchase request. Please select the plan again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Products", callback_data="rp_products", style="primary")]]))
            return
        # Re-read all data at confirmation time so stale buttons cannot sell a
        # deleted product, an out-of-stock key, or charge an old price.
        products = load_json("products.json")
        product = products.get(pid)
        if not isinstance(product, dict) or not product.get("enabled", True):
            await q.edit_message_text("Product is unavailable now.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Products", callback_data="rp_products", style="danger")]]))
            return
        plans = product.get("plans", [])
        if index < 0 or index >= len(plans):
            await q.edit_message_text("Plan is no longer available.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Products", callback_data="rp_products", style="danger")]]))
            return
        plan = plans[index]
        keys = plan.get("keys", [])
        if not keys:
            await q.edit_message_text("This plan is out of stock. No balance was deducted.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Product", callback_data=f"rp_product_{pid}", style="danger")]]))
            return
        discount = _reseller_discount()
        price = round(float(plan.get("price", 0) or 0) * (100.0 - discount) / 100.0, 2)
        balances = load_json("balances.json")
        balance = round(float(balances.get(uid, 0) or 0), 2)
        if balance < price:
            await q.edit_message_text(
                f"<b>Insufficient Reseller Balance</b>\n\nPrice: <b>₹{price:.2f}</b>\nYour shared balance: <b>₹{balance:.2f}</b>\n\nTap Add Balance to request a top-up from the admin. Your Shop Bot and Reseller Panel use the same shared balance.",
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Add Balance", callback_data="rp_request_balance", style="success")],
                    [InlineKeyboardButton("Back to Products", callback_data="rp_products", style="danger")],
                ])
            )
            return
        # Deduct from the shared Shop/Reseller wallet; inventory and orders are shared too.
        balance = round(balance - price, 2)
        balances[uid] = balance
        key = keys.pop(0)
        products[pid]["plans"][index]["keys"] = keys
        save_json("balances.json", balances)
        save_json("products.json", products)
        orders = load_json("orders.json")
        order_id = f"RSP{int(time.time())}{random.randint(100, 999)}"
        now = datetime.now().strftime("%d %b %Y %H:%M")
        try:
            chat = await context.bot.get_chat(int(uid))
            username = getattr(chat, "username", "") or ""
            name = getattr(chat, "first_name", "") or "User"
        except Exception:
            username, name = "", "User"
        orders[order_id] = {
            "user": int(uid), "username": username, "name": name,
            "product_id": pid, "product_name": product.get("name", "Product"),
            "plan": plan, "price": price, "duration": duration_text(plan),
            "days": plan.get("days"), "status": "Delivered", "date": now,
            "key": key, "source": "reseller_panel"
        }
        save_json("orders.json", orders)
        context.user_data.pop("rp_pending_buy", None)
        await q.edit_message_text(
            "━━━━━━━━━━━━━━━━━━━━\n<b>Reseller Purchase Successful</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"Product: <b>{html.escape(str(product.get('name', 'Product')))}</b>\n"
            f"Plan: <b>{html.escape(duration_text(plan))}</b>\n"
            f"Order ID: <code>{html.escape(order_id)}</code>\n"
            f"Price paid (50% reseller discount): <b>₹{price:.2f}</b>\n"
            f"Remaining reseller balance: <b>₹{balance:.2f}</b>\n\n"
            f"License key:\n<blockquote><code>{html.escape(str(key))}</code></blockquote>",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Copy Key", copy_text=CopyTextButton(text=str(key)))],
                [InlineKeyboardButton("View More Products", callback_data="rp_products", style="primary")],
                [InlineKeyboardButton("My Balance", callback_data="rp_balance", style="success")],
                [InlineKeyboardButton("Back to Panel", callback_data="rp_home", style="danger")],
            ])
        )
        return

    state = context.user_data.get("rp_login")
    if not isinstance(state, dict):
        if data == "rp_products":
            await q.edit_message_text("Please log in first. Send /start.")
        else:
            await q.edit_message_text("Session ended. Send /start to log in again.")
        return
    if data == "rp_del":
        state["digits"] = state.get("digits", "")[:-1]
    elif data.startswith("rp_d_"):
        digit = data[-1]
        if len(state.get("digits", "")) < 12:
            state["digits"] = state.get("digits", "") + digit
    elif data == "rp_ok":
        digits = str(state.get("digits", ""))
        users = load_json("users.json")
        row = users.get(uid, {}) if isinstance(users.get(uid, {}), dict) else {}
        info = row.get("reseller", {}) if isinstance(row.get("reseller", {}), dict) else {}
        if state.get("step") == "id":
            if not reseller_is_active(uid) or not info.get("active") or str(info.get("login_id", "")) != digits:
                state["digits"] = ""
                context.user_data["rp_login"] = state
                text, markup = reseller_panel_keyboard("", "id")
                await q.edit_message_text("<b>Reseller ID not found or access is expired.</b>\n\n" + text, parse_mode="HTML", reply_markup=markup)
                return
            state["step"] = "password"
            state["digits"] = ""
            context.user_data["rp_login"] = state
            text, markup = reseller_panel_keyboard("", "password")
            await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
            return
        try:
            salt = bytes.fromhex(str(info.get("password_salt", "")))
            supplied = hashlib.pbkdf2_hmac("sha256", digits.encode(), salt, 160000).hex()
            valid = bool(salt) and hmac.compare_digest(supplied, str(info.get("password_hash", "")))
        except Exception:
            valid = False
        if not valid or not reseller_is_active(uid):
            state["digits"] = ""
            context.user_data["rp_login"] = state
            text, markup = reseller_panel_keyboard("", "password")
            await q.edit_message_text("<b>Incorrect password or reseller access expired.</b>\n\n" + text, parse_mode="HTML", reply_markup=markup)
            return
        context.user_data.pop("rp_login", None)
        context.user_data["rp_logged_in"] = True
        info["panel_logged_in"] = True
        row["reseller"] = info
        users[uid] = row
        save_json("users.json", users)
        await q.edit_message_text(
            f"<b>Reseller login successful.</b>\n\nAvailable balance: <b>₹{_reseller_balance(uid):.2f}</b>\n\n"
            "You will stay logged in on this Telegram account until your reseller plan expires.\nYour Shop Bot and Reseller Panel use the same shared balance. Use Request Balance to ask the admin for a top-up.",
            parse_mode="HTML", reply_markup=_reseller_home_markup()
        )
        return
    text, markup = reseller_panel_keyboard(state.get("digits", ""), state.get("step", "id"))
    context.user_data["rp_login"] = state
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

def _reseller_admin_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Statistics", callback_data="rp_admin_stats", style="primary"), InlineKeyboardButton("Reseller List", callback_data="rp_admin_resellers", style="primary")],
        [InlineKeyboardButton("Add Balance", callback_data="rp_admin_add_balance", style="success"), InlineKeyboardButton("Deduct Balance", callback_data="rp_admin_deduct_balance", style="danger")],
        [InlineKeyboardButton("Set Discount", callback_data="rp_admin_discount", style="primary")],
        [InlineKeyboardButton("Broadcast", callback_data="rp_admin_broadcast", style="primary")],
    ])

async def reseller_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("Admin access only.")
        return
    await update.effective_message.reply_text("<b>TURBO RESELLER ADMIN PANEL</b>\n\nChoose an admin action.", parse_mode="HTML", reply_markup=_reseller_admin_markup())

async def reseller_panel_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    action = context.user_data.get("rp_admin_action")
    if not action:
        return
    if not is_admin(uid):
        context.user_data.pop("rp_admin_action", None)
        return
    message = (update.effective_message.text or "").strip()
    if action in ("add_balance", "deduct_balance"):
        try:
            target, amount_text = message.split(maxsplit=1)
            amount = float(amount_text)
            if not target.isdigit() or amount <= 0:
                raise ValueError
        except Exception:
            await update.effective_message.reply_text("Invalid format. Send: USER_ID AMOUNT (example: 123456789 100)")
            return
        wallets = load_json("balances.json")
        old = round(float(wallets.get(target, 0) or 0), 2)
        new = round(old + amount if action == "add_balance" else old - amount, 2)
        if new < 0:
            await update.effective_message.reply_text(f"Cannot deduct ₹{amount:.2f}; current reseller balance is ₹{old:.2f}.")
            return
        wallets[target] = new
        save_json("balances.json", wallets)
        context.user_data.pop("rp_admin_action", None)
        label = "Added" if action == "add_balance" else "Deducted"
        await update.effective_message.reply_text(f"{label} ₹{amount:.2f} for reseller {target}. New shared balance: ₹{new:.2f}.", reply_markup=_reseller_admin_markup())
        try:
            await context.bot.send_message(chat_id=int(target), text=f"Reseller Panel balance updated. {label}: ₹{amount:.2f}. New balance: ₹{new:.2f}.")
        except Exception:
            pass
        return
    if action == "add_balance_target":
        try:
            amount = float(message)
            if amount <= 0:
                raise ValueError
        except Exception:
            await update.effective_message.reply_text("Please send a valid amount greater than zero.")
            return
        target = str(context.user_data.pop("rp_admin_target", ""))
        wallets = load_json("balances.json")
        new = round(float(wallets.get(target, 0) or 0) + amount, 2)
        wallets[target] = new
        save_json("balances.json", wallets)
        context.user_data.pop("rp_admin_action", None)
        await update.effective_message.reply_text(f"Added ₹{amount:.2f} to reseller {target}. New balance: ₹{new:.2f}.", reply_markup=_reseller_admin_markup())
        try:
            await context.bot.send_message(chat_id=int(target), text=f"Your shared Turbo balance was topped up by ₹{amount:.2f}. New balance: ₹{new:.2f}.")
        except Exception:
            pass
        return
    if action == "discount":
        try:
            percent = float(message)
            if not 0 <= percent <= 90:
                raise ValueError
        except Exception:
            await update.effective_message.reply_text("Enter a discount percentage from 0 to 90.")
            return
        settings = load_json("settings.json")
        settings["reseller_discount_percent"] = percent
        save_json("settings.json", settings)
        context.user_data.pop("rp_admin_action", None)
        await update.effective_message.reply_text(f"Reseller discount updated to {percent:g}%.", reply_markup=_reseller_admin_markup())
        return
    if action == "broadcast":
        panel_users = load_json("reseller_panel_users.json")
        targets = {str(target) for target in panel_users if str(target).isdigit()}
        sent = failed = 0
        for target in targets:
            try:
                await context.bot.send_message(chat_id=int(target), text=message, parse_mode="HTML")
                sent += 1
            except Exception:
                failed += 1
        context.user_data.pop("rp_admin_action", None)
        await update.effective_message.reply_text(f"Broadcast finished. Sent: {sent}; failed: {failed}.", reply_markup=_reseller_admin_markup())
        return

async def _run_apps(shop_app, reseller_app=None):
    # Start the main shop bot first. A misconfigured optional reseller token
    # must not prevent the main shop bot from coming online.
    shop_started = False
    reseller_initialized = False
    reseller_started = False
    auto_broadcast_task = None
    try:
        await shop_app.initialize()
        await shop_app.start()
        shop_started = True
        # This app uses manual initialize/start rather than run_polling(), so
        # PTB's post_init hook is not invoked. Start the scheduler explicitly.
        auto_broadcast_task = asyncio.create_task(
            auto_bc_worker(shop_app), name="automatic-channel-broadcast-worker"
        )
        print("[AUTO BROADCAST] Scheduler started and monitoring saved channels.")
        if shop_app.updater:
            await shop_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        print("Main Shop Bot is running.")

        if reseller_app is not None:
            try:
                await reseller_app.initialize()
                reseller_initialized = True
                await reseller_app.start()
                reseller_started = True
                if reseller_app.updater:
                    await reseller_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
                print("Reseller Panel Bot is running.")
            except Exception as exc:
                # Keep the shop bot alive if the separate reseller bot token or
                # its polling setup is invalid. The warning makes this visible.
                print(f"WARNING: Reseller Panel Bot did not start: {type(exc).__name__}: {exc}")
                try:
                    if reseller_app.updater and reseller_app.updater.running:
                        await reseller_app.updater.stop()
                except Exception:
                    pass
                try:
                    if reseller_started:
                        await reseller_app.stop()
                except Exception:
                    pass
                try:
                    if reseller_initialized:
                        await reseller_app.shutdown()
                        reseller_initialized = False
                except Exception:
                    pass

        if not OTP_BOT_TOKEN:
            print("NOTE: OTP_BOT_TOKEN is not set; password-reset OTP delivery will not work until configured.")
        await asyncio.Event().wait()
    finally:
        if auto_broadcast_task is not None:
            auto_broadcast_task.cancel()
            try:
                await auto_broadcast_task
            except asyncio.CancelledError:
                pass
        if shop_app.updater and shop_app.updater.running:
            await shop_app.updater.stop()
        if shop_started:
            await shop_app.stop()
        await shop_app.shutdown()
        if reseller_app is not None and reseller_initialized:
            try:
                if reseller_app.updater and reseller_app.updater.running:
                    await reseller_app.updater.stop()
            except Exception:
                pass


def main():
    shop_app = (Application.builder().token(BOT_TOKEN).connection_pool_size(16).connect_timeout(15).read_timeout(20).write_timeout(20).pool_timeout(10).build())
    shop_app.add_handler(CommandHandler("start", start_command))
    shop_app.add_handler(CommandHandler("admin", admin_command))
    shop_app.add_handler(CommandHandler("restartgame", restartgame_command))
    shop_app.add_handler(CallbackQueryHandler(callback_handler))
    shop_app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & ~filters.TEXT, media_handler))
    shop_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    reseller_app = None
    if RESELLER_BOT_TOKEN:
        reseller_app = Application.builder().token(RESELLER_BOT_TOKEN).connection_pool_size(8).build()
        reseller_app.add_handler(CommandHandler("start", reseller_panel_start))
        reseller_app.add_handler(CommandHandler("admin", reseller_admin_command))
        reseller_app.add_handler(CallbackQueryHandler(reseller_panel_callback))
        reseller_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reseller_panel_text_handler))
    else:
        print("NOTE: RESELLER_BOT_TOKEN is not set; starting only the main shop bot.")
    asyncio.run(_run_apps(shop_app, reseller_app))

if __name__ == "__main__":
    main()
