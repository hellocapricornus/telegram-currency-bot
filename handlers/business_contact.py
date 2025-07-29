from telegram import Update
from telegram.ext import ContextTypes

async def handle_business_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤝 商务合作洽谈 · 官方渠道\n\n"
        "尊敬的合作方您好：\n\n"
        "感谢您对本项目的关注与支持。\n"
        "我们致力于构建高效、安全、可信赖的合作生态，期待与您携手共赢。\n\n"
        "如有以下合作意向，欢迎联系我方商务代表：\n\n"
        "项目对接 / 渠道合作\n\n"
        "技术支持 / 产品定制\n\n"
        "市场推广 / 联合运营\n\n"
        "📨 官方商务代表：@VEXEPay\n"
        "🔐 我们承诺对所有合作意向信息严格保密。\n\n"
        "期待与您展开深度合作，共创未来价值！"
    )
