import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

API_KEY = os.environ["API_KEY"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()

    if text.startswith("汇率 "):
        try:
            parts = text.split()
            base = parts[1]
            target = parts[2]
            url = f"https://v6.exchangerate-api.com/v6/{API_KEY}/pair/{base}/{target}"
            response = requests.get(url).json()

            if response.get("result") == "success":
                rate = response["conversion_rate"]
                await update.message.reply_text(f"💱 当前 {base} → {target} 汇率是：{rate}")
            else:
                await update.message.reply_text("❌ 查询失败，请检查币种代码是否正确，例如 USD CNY")
        except:
            await update.message.reply_text("❗ 格式错误，请使用：汇率 USD CNY")
    else:
        await update.message.reply_text("📌 你可以发送：汇率 USD CNY，获取实时汇率")

# 启动机器人
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
