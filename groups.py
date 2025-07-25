import os
import json
import logging

GROUP_FILE = "data/groups.json"
logger = logging.getLogger(__name__)

def load_groups():
    os.makedirs(os.path.dirname(GROUP_FILE), exist_ok=True)
    if not os.path.exists(GROUP_FILE):
        with open(GROUP_FILE, "w", encoding="utf-8") as f:
            f.write("{}")
    if os.path.getsize(GROUP_FILE) == 0:
        with open(GROUP_FILE, "w", encoding="utf-8") as f:
            f.write("{}")
    try:
        with open(GROUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取群组数据失败: {e}")
        return {}

async def update_group_info(update, context):
    chat = update.effective_chat
    if chat.type not in ["group", "supergroup"]:
        return

    groups = load_groups()
    if str(chat.id) not in groups:
        groups[str(chat.id)] = {
            "title": chat.title,
            "type": chat.type
        }
        try:
            with open(GROUP_FILE, "w", encoding="utf-8") as f:
                json.dump(groups, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 群组信息已更新: {chat.title} ({chat.id})")
        except Exception as e:
            logger.error(f"写入群组信息失败: {e}")
