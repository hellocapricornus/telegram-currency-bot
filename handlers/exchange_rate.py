import os
import json
from telegram import Update
from telegram.ext import ContextTypes

SCAM_FILE = "data/scam_addresses.json"

# 读取地址标记
def load_scam_addresses():
    if not os.path.exists(SCAM_FILE):
        return {}
    try:
        with open(SCAM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# 保存地址标记
def save_scam_addresses(data):
    os.makedirs(os.path.dirname(SCAM_FILE), exist_ok=True)
    with open(SCAM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 用户点击“地址防诈”
async def handle_scam_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_scam_address"] = True
    await update.message.reply_text("🔍 请发送要查询的钱包地址：")

# 处理用户输入地址
async def handle_scam_address_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    data = load_scam_addresses()
    if address in data:
        await update.message.reply_text(
            f"⚠️ 该地址已被标记！\n\n"
            f"🏷 标记说明：{data[address]}"
        )
    else:
        await update.message.reply_text("✅ 未查询到该地址的标记。")

# 管理员添加标记
async def handle_add_scam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("用法：/add_scam <地址> <标记说明>")
        return
    address = context.args[0]
    note = " ".join(context.args[1:])
    data = load_scam_addresses()
    data[address] = note
    save_scam_addresses(data)
    await update.message.reply_text(f"✅ 已添加标记\n地址：{address}\n说明：{note}")

# 管理员删除标记
async def handle_del_scam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("用法：/del_scam <地址>")
        return
    address = context.args[0]
    data = load_scam_addresses()
    if address in data:
        del data[address]
        save_scam_addresses(data)
        await update.message.reply_text(f"✅ 已删除标记地址：{address}")
    else:
        await update.message.reply_text("⚠️ 未找到该地址的标记。")
