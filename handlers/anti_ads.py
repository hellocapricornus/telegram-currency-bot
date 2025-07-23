# handlers/anti_ads.py

import re
from telegram import Update
from telegram.ext import ContextTypes

# 广告关键词正则
AD_PATTERNS = [
    r"discord\.gg", r"https?://",
    r"加群", r"推广", r"福利", r"邀请码", r"交流群", r"官方", r"投资", r"刷单", r"返利",
    r"代开", r"代办", r"代用户名", r"tg群", r"VX", r"vx", r"微信",
]
AD_REGEX = re.compile("|".join(AD_PATTERNS), flags=re.IGNORECASE)

def is_group(update: Update) -> bool:
    return update.effective_chat.type in ["group", "supergroup"]

async def detect_and_delete_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    # 只处理群组消息
    if not is_group(update):
        return

    if not message or not message.text:
        return

    # 忽略管理员或群主
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["administrator", "creator"]:
            return
    except Exception as e:
        print(f"[获取成员信息失败] {e}")
        return

    # 匹配广告关键词
    match = AD_REGEX.search(message.text)
    if match:
        keyword = match.group(0)
        try:
            await message.delete()
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"🚫 @{user.username or user.id} 发送的消息包含违规关键词「{keyword}」，已被删除。\n请勿发布广告、推广、加群等内容。",
            )
        except Exception as e:
            print(f"[广告删除失败] {e}")
