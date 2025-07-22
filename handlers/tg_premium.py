from telegram import Update
from telegram.ext import ContextTypes

async def handle_premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📱 <b>Telegram Premium（代开）服务</b>\n\n"
        "我们提供 Telegram Premium 月费代开服务，支持 USDT（TRC20）支付。\n\n"
        "<b>价格</b>：\n"
        "• 3 个月：<b>15 USDT</b>\n"
        "• 6 个月：<b>24 USDT</b>\n"
        "• 12 个月：<b>40 USDT</b>\n\n"
        "📌 请在下单前联系人工客服确认可开通状态，并获取付款地址。\n"
        "💬 <a href='https://t.me/LightningPayGroup'>点此联系人工客服</a>\n\n"
        "⚠️ 请勿自行转账，付款请先沟通确认账号及操作流程。"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
