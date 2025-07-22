# handlers/anti_ads.py

import re
from telegram import Update
from telegram.ext import ContextTypes

# 常见广告关键词/链接
AD_PATTERNS = [
    r"discord\.gg", r"https?://",
    r"加群", r"推广", r"福利", r"邀请码", r"交流群", r"官方", r"投资", r"刷单", r"返利",
    r"代开", r"代办", r"代用户名",  # 匹配 @用户名
]

AD_REGEX = re.compile("|".join(AD_PATTERNS), flags=re.IGNORECASE)

async def detect_and_delete_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not message.text:
        return

    # 忽略管理员
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status in ["administrator", "creator"]:
        return

    match = AD_REGEX.search(message.text)
    if match:
        try:
            await message.delete()
            keyword = match.group(0)
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"🚫 @{user.username or user.id} 发送的消息包含违规内容「{keyword}」，已被删除。\n群组禁止发布广告、推广、加群、代开等信息。"
            )
        except Exception as e:
            print(f"[广告删除失败] {e}")
