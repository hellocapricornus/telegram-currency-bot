import os
import json
import logging
from telegram import Update
from telegram.ext import ContextTypes

GROUP_FILE = "data/groups.json"
logger = logging.getLogger(__name__)

def load_groups():
    """加载群组信息，若文件不存在或为空则初始化为空字典"""
    os.makedirs(os.path.dirname(GROUP_FILE), exist_ok=True)
    if not os.path.exists(GROUP_FILE) or os.path.getsize(GROUP_FILE) == 0:
        with open(GROUP_FILE, "w", encoding="utf-8") as f:
            f.write("{}")
    try:
        with open(GROUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取群组数据失败: {e}")
        return {}

async def update_group_info(update, context=None):
    """异步更新群组信息（群名或类型）"""
    chat = update.effective_chat
    if chat.type not in ["group", "supergroup"]:
        return

    groups = load_groups()
    group_id = str(chat.id)

    # 如果群组不存在，或群名称、类型发生变化则更新
    if (group_id not in groups or
        groups[group_id].get("title") != chat.title or
        groups[group_id].get("type") != chat.type):

        groups[group_id] = {
            "title": chat.title,
            "type": chat.type
        }
        try:
            with open(GROUP_FILE, "w", encoding="utf-8") as f:
                json.dump(groups, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 群组信息已更新: {chat.title} ({chat.id})")
        except Exception as e:
            logger.error(f"写入群组信息失败: {e}")

    # 🔍 调试：打印当前所有群组
    logger.debug(f"[调试] 当前群组缓存: {json.dumps(groups, ensure_ascii=False, indent=2)}")

def delete_group(group_id: str):
    """删除指定群组ID的记录"""
    groups = load_groups()
    if group_id in groups:
        del groups[group_id]
        try:
            with open(GROUP_FILE, "w", encoding="utf-8") as f:
                json.dump(groups, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 已删除群组记录: {group_id}")
            return True
        except Exception as e:
            logger.error(f"删除群组时写文件失败: {e}")
            return False
    else:
        logger.warning(f"删除群组失败，未找到群组ID: {group_id}")
        return False
