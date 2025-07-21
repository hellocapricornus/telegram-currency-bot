import os
import re
import logging
import asyncio
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import (
    ReplyKeyboardMarkup,
    InlineKeyboardButton,#新加
    InlineKeyboardMarkup,#新加
    Update,
    BotCommand,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from telegram.constants import ChatType #新加
from groups import load_groups, update_group_info #新加
from handlers.exchange_rate import handle_exchange_rate, handle_exchange_rate_input
from handlers.address import handle_address_input, button_callback as address_button_callback
from handlers.bookkeeper import handle_bookkeeping_start, handle_bookkeeping_end
from handlers.compare_price import handle_price_compare
from handlers.transaction import (
    handle_transaction,
    handle_transaction_input,
    transaction_callback_handler,
)
from handlers.tg_premium import handle_premium_info
from handlers.usage_guide import handle_usage_guide
from handlers.contact import handle_contact, handle_contact_input
from handlers.business_contact import handle_business_contact

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

ADMIN_ID = 7596698993 #新加

# 配置常量
BUTTONS = [
    ["🧾 开始记账", "📈 点位对比", "💹 实时U价"],
    ["💰 地址查询", "🤝 交易查询", "💎 代开会员"],
    ["📥 商务联系", "📖 使用说明", "📊 互转分析"],
]

BUTTON_TEXTS = {btn for row in BUTTONS for btn in row}

COMMANDS = [
    BotCommand("start", "启动机器人并显示功能按钮"),
    BotCommand("help", "帮助信息"),
    BotCommand("start_bookkeeping", "群组中启动记账功能"),
    BotCommand("activate", "群组中激活记账功能"),
    BotCommand("status", "查看试用/激活状态"),
    BotCommand("checkgroup", "查看群组信息和类型"),
]

# 支持多个群组和频道，用户需加入任意一个才视为激活
REQUIRED_CHAT_IDS = [-1002615680129, -1002739279735]  # 群组ID和频道ID
REQUIRED_CHAT_LINKS = [
    "https://t.me/LightningPayCG",
    "https://t.me/LightningPayGC",
]
TRIAL_HOURS = 24

TRIAL_DATA_FILE = "trial_data.json"

def format_required_chat_links():
    return "\n".join(REQUIRED_CHAT_LINKS)

# 群组管理员拉取
async def handle_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ 无权限")
        return

    groups = load_groups()
    if not groups:
        await update.message.reply_text("⚠️ 暂无群组信息。")
        return

    keyboard = []
    for group_id, group in groups.items():
        keyboard.append([InlineKeyboardButton(group["title"], callback_data=f"select_group:{group_id}")])

    await update.message.reply_text("📂 请选择要查询的群组：", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_group_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # 回应回调，防止客户端loading一直转

    data = query.data
    if not data.startswith("select_group:"):
        return

    group_id = data.split(":", 1)[1]
    groups = load_groups()
    group = groups.get(group_id)
    if not group:
        await query.edit_message_text("⚠️ 群组信息不存在")
        return

    try:
        # 异步获取该群组的管理员列表
        admins = await context.bot.get_chat_administrators(group_id)

        text_lines = [
            f"✅ 群组名称：{group['title']}",
            f"🆔 群组 ID：{group_id}",
            "",
            "管理员列表："
        ]

        for admin in admins:
            user = admin.user
            name = user.full_name
            if user.username:
                name += f" (@{user.username})"
            text_lines.append(f"👤 {name}")

        text = "\n".join(text_lines)

        # 只调用一次编辑接口，发送完整文本
        await query.edit_message_text(text)

    except Exception as e:
        # 出错时给出错误提示
        await query.edit_message_text(f"⚠️ 获取管理员列表失败：{e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 机器人已启动")

async def group_message_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        logger.info(f"收到消息：chat_id={update.message.chat.id} user_id={update.effective_user.id} text={update.message.text}")
        await update_group_info(update)

# 地址校验
def is_valid_address(text: str) -> bool:
    pattern = r"^(T[1-9A-HJ-NP-Za-km-z]{33}|0x[a-fA-F0-9]{40})$"
    return re.fullmatch(pattern, text) is not None

# 管理员缓存
class AdminCache:
    def __init__(self, timeout=300):
        self._cache = {}
        self._timeout = timeout

    async def is_admin(self, bot, chat_id, user_id):
        key = (chat_id, user_id)
        now = asyncio.get_event_loop().time()
        if key in self._cache:
            cache_time, is_admin = self._cache[key]
            if now - cache_time < self._timeout:
                return is_admin
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            self._cache[key] = (now, is_admin)
            return is_admin
        except Exception as e:
            logger.error(f"获取管理员状态失败: chat_id={chat_id} user_id={user_id} error={e}")
            return False

admin_cache = AdminCache()

# 试用数据文件操作
def load_trial_data():
    if not os.path.exists(TRIAL_DATA_FILE):
        return {}
    try:
        with open(TRIAL_DATA_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取试用文件出错: {e}")
        return {}

def save_trial_data(data):
    try:
        with open(TRIAL_DATA_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"写入试用文件出错: {e}")

def is_trial_valid_file(user_id):
    data = load_trial_data()
    if str(user_id) not in data:
        return False
    start_str = data[str(user_id)]
    try:
        start_time = datetime.fromisoformat(start_str)
    except Exception as e:
        logger.error(f"试用时间格式错误: {e}")
        return False
    return datetime.utcnow() - start_time < timedelta(hours=TRIAL_HOURS)

def start_trial_file(user_id):
    data = load_trial_data()
    data[str(user_id)] = datetime.utcnow().isoformat()
    save_trial_data(data)
    logger.info(f"用户{user_id}开始试用，时间：{data[str(user_id)]}")

def remove_trial_file(user_id):
    data = load_trial_data()
    if str(user_id) in data:
        del data[str(user_id)]
        save_trial_data(data)
        logger.info(f"用户{user_id}试用记录已移除")

# 多聊天检测激活
async def is_user_activated(bot, user_id: int) -> bool:
    for chat_id in REQUIRED_CHAT_IDS:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ["member", "administrator", "creator"]:
                remove_trial_file(user_id)
                return True
        except Exception as e:
            logger.warning(f"查询用户{user_id}在群/频道{chat_id}成员状态失败: {e}")
    return False

# 访问权限检查
async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    bot = context.bot

    if await is_user_activated(bot, user_id):
        return True

    if is_trial_valid_file(user_id):
        return True

    start_trial_file(user_id)

    await update.message.reply_text(
        f"⏳ 您正在使用24小时免费试用期。\n"
        f"试用结束后请加入以下群组或频道以继续使用机器人：\n{format_required_chat_links()}"
    )
    return False

STATE_HANDLERS = {
    "awaiting_price_compare": handle_price_compare,
    "awaiting_exchange_currency": handle_exchange_rate_input,
    "awaiting_contact_addresses": handle_contact_input,
    "awaiting_tx_addresses": handle_transaction_input,
}

async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ["group", "supergroup"]:
        return True
    return await admin_cache.is_admin(context.bot, chat.id, user.id)

async def handle_bookkeeping_start_safe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.chat.type in ["group", "supergroup"]:
            if not await is_user_admin(update, context):
                await update.message.reply_text("❌ 只有群管理员可以启动记账功能。")
                return
        if update.message.chat.type == "private":
            if not await check_access(update, context):
                return
        await handle_bookkeeping_start(update, context)
    except Exception as e:
        logger.error(f"handle_bookkeeping_start_safe异常: {e}")
        await update.message.reply_text("⚠️ 启动记账时发生错误，请稍后重试。")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.chat.type in ["group", "supergroup"]:
            await update.message.reply_text("✅ 群组已接入机器人，请发送 /start_bookkeeping 启动记账功能。")
            return

        keyboard = ReplyKeyboardMarkup(BUTTONS, resize_keyboard=True)
        await update.message.reply_text("欢迎使用记账机器人，请选择一个功能：", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"start命令异常: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        chat_type = update.message.chat.type
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        logger.info(f"收到消息：chat_id={chat_id} user_id={user_id} text={text}")

        if chat_type in ["group", "supergroup"]:
            if text in ["🧾 开始记账", "/start_bookkeeping", "/activate"]:
                await handle_bookkeeping_start_safe(update, context)
            return

        bot = context.bot
        activated = await is_user_activated(bot, user_id)
        trial = is_trial_valid_file(user_id)

        # 试用期结束且未激活，限制除「商务联系」和「代开会员」外其他按钮
        if not activated and not trial:
            allowed_buttons = {"📥 商务联系", "💎 代开会员"}
            if text not in allowed_buttons:
                await update.message.reply_text(
                    f"⚠️ 您的试用期已结束，请加入以下群组或频道才能使用此功能：\n{format_required_chat_links()}"
                )
                return

        if text in BUTTON_TEXTS:
            context.user_data.clear()

        if text == "🧾 开始记账":
            await handle_bookkeeping_start(update, context)
            return

        if text == "📈 点位对比":
            context.user_data["awaiting_price_compare"] = True
            await update.message.reply_text(
                "请按格式输入点位对比，例如：\n5 100/6 110\n支持整数和小数"
            )
            return

        if text == "💹 实时U价":
            await handle_exchange_rate(update, context)
            return

        if text == "💰 地址查询":
            await update.message.reply_text(
                "请直接发送您想查询的钱包地址（支持以太坊地址和 TRON 地址）"
            )
            return

        if text == "🤝 交易查询":
            context.user_data["awaiting_tx_addresses"] = True
            await handle_transaction(update, context)
            return

        if text == "💎 代开会员":
            await handle_premium_info(update, context)
            return

        if text == "📥 商务联系":
            await handle_business_contact(update, context)
            return

        if text == "📖 使用说明":
            await handle_usage_guide(update, context)
            return

        if text == "📊 互转分析":
            await handle_contact(update, context)
            return

        for state, handler in STATE_HANDLERS.items():
            if context.user_data.get(state):
                await handler(update, context)
                context.user_data[state] = False
                return

        if is_valid_address(text):
            await handle_address_input(update, context)
            return

        await update.message.reply_text("请输入有效指令或点击功能按钮。")

    except Exception as e:
        logger.error(f"handle_message异常: {e}")
        await update.message.reply_text("⚠️ 处理消息时发生错误，请稍后再试。")

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        data = query.data

        if data.startswith("tx_page_"):
            await transaction_callback_handler(update, context)
            return

        await address_button_callback(update, context)
    except Exception as e:
        logger.error(f"callback_query_handler异常: {e}")
        if update.callback_query:
            await update.callback_query.answer(text="操作失败，请稍后重试。", show_alert=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        help_text = (
            "欢迎使用记账机器人！\n\n"
            "使用说明：\n"
            "1. 点击菜单按钮开始操作\n"
            "2. 地址查询：发送TRON或ETH地址\n"
            "3. 交易查询：点击按钮后输入2-5个TRON地址查询互转记录\n"
            "更多功能请查看菜单"
        )
        await update.message.reply_text(help_text)
    except Exception as e:
        logger.error(f"help_command异常: {e}")

async def set_commands(app):
    try:
        await app.bot.set_my_commands(COMMANDS)
        logger.info(f"✅ 命令菜单已设置：{COMMANDS}")
    except Exception as e:
        logger.error(f"set_commands异常: {e}")

async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot = context.bot
    try:
        activated = await is_user_activated(bot, user_id)
        trial = is_trial_valid_file(user_id)
        msg = []
        if activated:
            msg.append("✅ 您已通过加入群组或频道激活，功能无限制。")
        elif trial:
            msg.append("⏳ 您当前处于24小时免费试用期内。")
        else:
            msg.append(
                f"⏳ 您的试用期已结束。\n请加入以下群组或频道 {format_required_chat_links()} 以继续使用机器人。"
            )
        await update.message.reply_text("\n".join(msg))
    except Exception as e:
        logger.error(f"handle_status异常: {e}")
        await update.message.reply_text("查询状态时发生错误，请稍后再试。")

async def check_group_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chats = []
        for chat_id in REQUIRED_CHAT_IDS:
            chat = await context.bot.get_chat(chat_id)
            chats.append(f"{chat.title} ({chat.type})")
        await update.message.reply_text(f"群组/频道信息：\n" + "\n".join(chats))
    except Exception as e:
        await update.message.reply_text(f"获取群组信息失败：{e}")

def main():
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        print("❌ 请设置环境变量 BOT_TOKEN")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list_users", handle_list_users))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("start_bookkeeping", handle_bookkeeping_start_safe))
    app.add_handler(CommandHandler("activate", handle_bookkeeping_start_safe))
    app.add_handler(CommandHandler("checkgroup", check_group_type))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, group_message_listener), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message), group=1)
    app.add_handler(CallbackQueryHandler(handle_group_selection, pattern=r"^select_group:"))
    app.add_handler(CallbackQueryHandler(callback_query_handler))


    app.post_init = set_commands

    print("✅ 机器人已启动")
    app.run_polling()

if __name__ == "__main__":
    main()
