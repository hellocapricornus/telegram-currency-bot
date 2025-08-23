# handlers/anti_ads.py

import re
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus

# 广告关键词正则
AD_PATTERNS = [
    r"discord\.gg", r"https?://",
    r"加群", r"推广", r"福利", r"邀请码", r"交流群", r"官方", r"投资", r"返利",
    r"代开", r"代办", r"代用户名", r"tg群", r"VX", r"vx", r"微信",
]
AD_REGEX = re.compile("|".join(AD_PATTERNS), flags=re.IGNORECASE)

# 仅群组 2615680129 需要关注频道
REQUIRED_CHANNEL_GROUP_ID = -1002615680129
REQUIRED_CHANNEL_ID = -1002739279735
REQUIRED_CHANNEL_LINK = "https://t.me/VEXEGX"

def is_group(update: Update) -> bool:
    return update.effective_chat.type in ["group", "supergroup"]

async def detect_and_delete_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat


    if not chat.type.endswith("group") or not message or not message.text:
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["administrator", "creator"]:
            return
    except Exception as e:
        print(f"[获取成员信息失败] {e}")
        return

    if chat.id == REQUIRED_CHANNEL_GROUP_ID:
        try:
            channel_member = await context.bot.get_chat_member(REQUIRED_CHANNEL_ID, user.id)
            if channel_member.status not in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ]:
                await message.delete()
                name = f"@{user.username}" if user.username else user.full_name
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"⚠️ {name}，请先关注频道：{REQUIRED_CHANNEL_LINK} 才能在本群发言。"
                )
                return
        except Exception as e:
            print(f"[检查频道关注状态失败] {e}")
            await message.delete()
            name = f"@{user.username}" if user.username else user.full_name
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"⚠️ {name}，请先关注频道：{REQUIRED_CHANNEL_LINK} 才能在本群发言。"
            )
            return

    # 检测广告关键词
    match = AD_REGEX.search(message.text)
    if match:
        keyword = match.group(0)
        try:
            await message.delete()
            name = f"@{user.username}" if user.username else str(user.id)
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"🚫 {name} 的消息包含违规词「{keyword}」，已删除。\n请勿发布广告、推广、加群等内容。",
            )
        except Exception as e:
            print(f"[广告删除失败] {e}")
