# handlers/usage_guide.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

USAGE_TEXT = (
    "🤖 记账机器人功能介绍：\n\n"
    "🧾【开始记账】\n启动群组记账，管理员和操作员专用。\n\n"
    "📈【点位对比】\n输入点位数字，快速比较行情变化。\n\n"
    "💹【实时U价】\n查询当前USDT汇率，精准折算。\n\n"
    "💰【地址查询】\n支持TRON和以太坊地址余额查询。\n\n"
    "🤝【交易查询】\n查询多个地址间的转账记录。\n\n"
    "💎【代开会员】\n获取会员服务及专属权限。\n\n"
    "📥【商务联系】\n快速联系商务支持人员。\n\n"
    "📊【互转分析】\n分析多地址间的资金流动。\n\n"
    "📢 本机器人永久免费使用，无任何收费。"
)

BACK_BUTTON = InlineKeyboardMarkup(
    [[InlineKeyboardButton("⬅️ 返回主菜单", callback_data="back_to_menu")]]
)

async def handle_usage_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message:
            await update.message.reply_text(USAGE_TEXT, reply_markup=BACK_BUTTON)
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(USAGE_TEXT, reply_markup=BACK_BUTTON)
    except Exception as e:
        logger.error(f"handle_usage_guide异常: {e}")
        if update.message:
            await update.message.reply_text("⚠️ 使用说明加载失败，请稍后重试。")

async def usage_guide_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        # 返回主菜单的逻辑，根据你的main.py按钮回复，这里示例返回固定文本
        await query.edit_message_text(
            "欢迎使用记账机器人，请选择一个功能：",
            reply_markup=None  # 如果你用ReplyKeyboardMarkup，是消息回复键盘，不是内联按钮
        )
    except Exception as e:
        logger.error(f"usage_guide_callback异常: {e}")
        if update.callback_query:
            await update.callback_query.answer(text="操作失败，请稍后重试。", show_alert=True)
