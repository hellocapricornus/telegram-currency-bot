import os
import json
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

logger = logging.getLogger(__name__)

MARKED_USERS_FILE = "data/marked_users.json"
OWNER_ID = 7596698993  # 只有这个 ID 可以操作标记

# ================= 工具函数 ================= #
def load_marked_users():
    if not os.path.exists(MARKED_USERS_FILE):
        return {}
    try:
        with open(MARKED_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取标记用户文件出错: {e}")
        return {}

def save_marked_users(data):
    try:
        os.makedirs(os.path.dirname(MARKED_USERS_FILE), exist_ok=True)
        with open(MARKED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"写入标记用户文件出错: {e}")

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# ================= 命令功能 ================= #
async def handle_mark_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return  # 只允许在私聊使用
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔️ 你没有权限执行此操作。")
        return

    if len(context.args) < 2:
        await update.message.reply_text("用法: /mark <user_id> <原因>")
        return

    user_id = context.args[0]
    reason = " ".join(context.args[1:])

    marked = load_marked_users()
    marked[user_id] = reason
    save_marked_users(marked)

    await update.message.reply_text(f"✅ 已标记用户 `{user_id}`，原因：{reason}", parse_mode="Markdown")

async def handle_unmark_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔️ 你没有权限执行此操作。")
        return

    if len(context.args) < 1:
        await update.message.reply_text("用法: /unmark <user_id>")
        return

    user_id = context.args[0]
    marked = load_marked_users()

    if user_id in marked:
        del marked[user_id]
        save_marked_users(marked)
        await update.message.reply_text(f"✅ 已删除用户 `{user_id}` 的标记", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ 此用户没有被标记。")

async def handle_list_marked_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔️ 你没有权限执行此操作。")
        return

    marked = load_marked_users()
    if not marked:
        await update.message.reply_text("📂 当前没有被标记的用户。")
        return

    lines = ["📌 已标记的用户："]
    for uid, reason in marked.items():
        lines.append(f"- `{uid}`：{reason}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ================= 群检测 ================= #
async def detect_marked_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    user_id = str(update.effective_user.id)
    marked = load_marked_users()

    if user_id in marked:
        reason = marked[user_id]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ 用户 `{user_id}` 已被标记\n原因：{reason}",
            parse_mode="Markdown"
        )

# ================= 注册入口 ================= #
def register_marked_users_handlers(app):
    """在 main.py 调用时批量注册这些功能"""
    app.add_handler(CommandHandler("mark", handle_mark_user))
    app.add_handler(CommandHandler("unmark", handle_unmark_user))
    app.add_handler(CommandHandler("marked_users", handle_list_marked_users))
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.ALL, detect_marked_user),
        group=0
    )
