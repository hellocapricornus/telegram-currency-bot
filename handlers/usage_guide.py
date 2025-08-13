from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
import logging
from groups import load_groups  # 你的群组加载函数，返回dict格式 {群ID: {"title": "群名称"}}

logger = logging.getLogger(__name__)

ALLOWED_USER_IDS = {7596698993, 7597598174, 8331810770, 8172118207}  # 允许的 Telegram 用户 ID

async def handle_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("❌ 你没有权限使用此功能。")
        return
        
    context.user_data.clear()
    context.user_data["awaiting_broadcast_content"] = True
    await update.message.reply_text("📢 请输入需要群发的内容：")

# 用户输入群发内容，进入选择群组阶段
async def handle_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["broadcast_content"] = update.message.text
    context.user_data.pop("awaiting_broadcast_content", None)

    groups = load_groups()
    if not groups:
        await update.message.reply_text("⚠️ 暂无可群发的群组记录。")
        return

    # 初始化选中集合为空
    context.user_data["broadcast_selected"] = set()
    context.user_data["awaiting_broadcast_groups"] = True

    keyboard = build_broadcast_group_keyboard(context.user_data["broadcast_selected"], groups)
    await update.message.reply_text("请选择需要发送的群：", reply_markup=InlineKeyboardMarkup(keyboard))


# 根据当前选中状态生成键盘（包含全选/全不选按钮）
def build_broadcast_group_keyboard(selected: set, groups: dict):
    keyboard = []

    all_selected = len(selected) == len(groups) and len(groups) > 0
    all_label = "全不选" if all_selected else "全选"
    keyboard.append([InlineKeyboardButton(f"🔘 {all_label}", callback_data="broadcast_toggle_all")])

    for gid, info in groups.items():
        prefix = "✅" if gid in selected else "⬜"
        keyboard.append([InlineKeyboardButton(f"{prefix} {info['title']}", callback_data=f"broadcast_toggle:{gid}")])

    keyboard.append([InlineKeyboardButton("✅ 确认选择", callback_data="broadcast_confirm")])
    return keyboard


# 处理选择群组或全选按钮的回调
async def handle_broadcast_group_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    groups = load_groups()
    selected = context.user_data.get("broadcast_selected", set())

    if data == "broadcast_toggle_all":
        # 全选或全不选
        if len(selected) == len(groups):
            selected.clear()
        else:
            selected = set(groups.keys())
        context.user_data["broadcast_selected"] = selected
    else:
        # 单个群组切换选择状态
        gid = data.split(":")[1]
        if gid in selected:
            selected.remove(gid)
        else:
            selected.add(gid)
        context.user_data["broadcast_selected"] = selected

    keyboard = build_broadcast_group_keyboard(selected, groups)
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))


# 处理确认按钮，提示发送确认
async def handle_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_ids = context.user_data.get("broadcast_selected", set())
    if not selected_ids:
        await query.edit_message_text("⚠️ 你还没有选择任何群组。")
        return

    groups = load_groups()
    names = [groups[gid]["title"] for gid in selected_ids if gid in groups]

    context.user_data["awaiting_broadcast_confirm"] = True
    await query.edit_message_text(
        f"📢 将向以下群发送消息：\n" + "\n".join(names) + "\n\n请输入 **发送** 确认发送。"
    )


# 监听用户输入“发送”，开始群发
async def handle_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_broadcast_confirm", False):
        await update.message.reply_text("⚠️ 当前没有待发送的群发任务，请先输入群发内容。")
        return

    content = context.user_data.get("broadcast_content")
    selected_ids = context.user_data.get("broadcast_selected", set())

    if not content or not selected_ids:
        await update.message.reply_text("⚠️ 群发数据缺失，请重新开始。")
        context.user_data.clear()
        return

    sent_count = 0
    for gid in selected_ids:
        try:
            await context.bot.send_message(chat_id=int(gid), text=content)
            sent_count += 1
        except Exception as e:
            logger.error(f"向群 {gid} 发送失败: {e}")

    await update.message.reply_text(f"✅ 群发完成，共发送到 {sent_count} 个群。")
    context.user_data.clear()
