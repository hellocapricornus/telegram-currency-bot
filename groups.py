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

# 在 update_group_info 内增加成员信息
async def update_group_info(update: Update):
    groups = load_groups()
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    group_id = str(chat.id)
    if group_id not in groups:
        groups[group_id] = {
            "title": chat.title,
            "users": {}
        }

    # 记录用户
    if user.id not in groups[group_id]["users"]:
        groups[group_id]["users"][user.id] = {
            "name": user.full_name,
            "username": user.username,
            "joined": datetime.utcnow().isoformat()
        }
    else:
        # 更新用户名（防止改名）
        groups[group_id]["users"][user.id]["name"] = user.full_name
        groups[group_id]["users"][user.id]["username"] = user.username

    save_groups(groups)


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
