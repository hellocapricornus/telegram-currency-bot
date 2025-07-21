from telegram import Update
from telegram.ext import ContextTypes

async def handle_usage_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 使用说明书如下（尚未实现）")
