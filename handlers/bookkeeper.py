import os
import re
import json
import math
import ast
import operator as op
import logging
from datetime import datetime, timezone, timedelta
from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatMemberUpdated,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatMemberStatus

logger = logging.getLogger(__name__)

# 初始化目录
HISTORY_DIR = "data/bills"
CACHE_DIR = "data/cache"
os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# 群组独立账本缓存，格式：chat_id -> {active, in, out, rate, fee, operator_usernames}
bookkeeping_data = {}

# ----- 缓存文件操作 -----
def now_beijing():
    return datetime.now(timezone.utc) + timedelta(hours=8)

def get_cache_path(chat_id):
    return os.path.join(CACHE_DIR, f"{chat_id}.json")

def save_cache(chat_id):
    data = bookkeeping_data.get(chat_id)
    if data is None:
        # 删除缓存文件（如果没有数据了）
        path = get_cache_path(chat_id)
        if os.path.exists(path):
            os.remove(path)
        return
    path = get_cache_path(chat_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_cache(chat_id):
    path = get_cache_path(chat_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def load_all_caches():
    bookkeeping_data.clear()
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".json"):
            cid_str = f[:-5]
            if cid_str.isdigit():
                cid = int(cid_str)
                data = load_cache(cid)
                if data:
                    bookkeeping_data[cid] = data


# 判断是否是管理员或操作人
# 修改为异步函数
# 判断是否是管理员或操作人（改为async，且统一小写匹配）
async def is_admin_or_operator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return True
    except Exception:
        pass

    user_username = (update.effective_user.username or "").lower()
    group_data = bookkeeping_data.get(chat_id, {})
    operator_usernames = set([u.lower() for u in group_data.get("operator_usernames", [])])
    return user_username in operator_usernames


# 下课：禁言所有成员
async def handle_class_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_or_operator(update, context):
        await update.message.reply_text("❌ 只有管理员可以执行此操作")
        return

    chat_id = update.effective_chat.id
    permissions = ChatPermissions(can_send_messages=False)  # 禁止发言
    await context.bot.set_chat_permissions(chat_id=chat_id, permissions=permissions)
    await update.message.reply_text("🔒 全群已禁言，下课啦！")

# 上课：解除禁言
async def handle_class_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_or_operator(update, context):
        await update.message.reply_text("❌ 只有管理员可以执行此操作")
        return

    chat_id = update.effective_chat.id
    permissions = ChatPermissions(can_send_messages=True)  # 允许发言
    await context.bot.set_chat_permissions(chat_id=chat_id, permissions=permissions)
    await update.message.reply_text("🔓 全群已解除禁言，上课啦！")

# 启动记账命令
async def handle_bookkeeping_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type == "private":
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ 添加我进群", url=f"https://t.me/{context.bot.username}?startgroup=true")
        ]])
        await update.message.reply_text(
            "❗️请将机器人添加进群组，并由管理员或操作人在群组中使用记账功能。",
            reply_markup=keyboard
        )
        return

    # 异步调用
    if not await is_admin_or_operator(update, context):
        await update.message.reply_text("只有群管理员或操作人可以使用该功能。")
        return

    chat_id = update.effective_chat.id  # --- 改动部分 START ---
    bookkeeping_data[chat_id] = {
        "active": True,
        "in": [],
        "out": [],
        "rate": 1.0,
        "fee": 0.0,
        "operator_usernames": bookkeeping_data.get(chat_id, {}).get("operator_usernames", []),
    }
    await update.message.reply_text("✅ 已开始记账。请设置汇率和费率后再输入入款记录。")
# --- 改动部分 END ---


# 入款处理（支持备注、汇率、费率）
async def handle_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in bookkeeping_data or not bookkeeping_data[chat_id]["active"]:
        return

    group_data = bookkeeping_data[chat_id]

    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()

    # 支持格式：+金额 [汇率] [费率] [备注]
    match = re.match(
        r"^\+(\d+(\.\d{1,2})?)"            # 金额
        r"(?:\s+(\d+(\.\d{1,4})?))?"       # 可选数字1（汇率或单数字）
        r"(?:\s+(\d+(\.\d{1,2})?))?"       # 可选数字2（费率）
        r"(?:\s+(.+))?$",                  # 可选备注
        text
    )

    if not match:
        return

    amount = float(match.group(1))
    val1 = match.group(3)
    val2 = match.group(5)
    remark = match.group(7) or ""

    # 默认汇率和费率
    rate = group_data.get("rate", 1.0)
    fee = group_data.get("fee", 0.0)

    if val1:
        val1 = float(val1)
        if val2:  # 两个数字同时存在
            rate = val1
            fee = float(val2)
        else:     # 只有一个数字，默认当汇率
            rate = val1

    time_str = now_beijing().strftime("%H:%M:%S")

    bookkeeping_data[chat_id]["in"].append({
        "time": time_str,
        "amount": amount,
        "rate": rate,
        "fee": fee,
        "remark": remark
    })

    await render_summary(update, context)


# 入款修正处理（支持备注、汇率、费率）
async def handle_deposit_correction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in bookkeeping_data or not bookkeeping_data[chat_id]["active"]:
        return

    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()

    # 支持格式：-金额 [汇率] [费率] [备注]
    match = re.match(
        r"^(入款-|\-)(\d+(\.\d{1,2})?)"   # 金额
        r"(?:\s+(\d+(\.\d{1,4})?))?"       # 数字1（汇率或单数字）
        r"(?:\s+(\d+(\.\d{1,2})?))?"       # 数字2（费率）
        r"(?:\s+(.+))?$",                  # 备注
        text, re.IGNORECASE
    )

    if not match:
        return

    amount = float(match.group(2))
    val1 = match.group(4)
    val2 = match.group(6)
    remark = match.group(7) or ""

    # 默认汇率和费率
    rate = bookkeeping_data[chat_id].get("rate", 1.0)
    fee = bookkeeping_data[chat_id].get("fee", 0.0)

    if val1:
        val1 = float(val1)
        if val2:
            rate = val1
            fee = float(val2)
        else:
            rate = val1

    time_str = now_beijing().strftime("%H:%M:%S")

    bookkeeping_data[chat_id]["in"].append({
        "time": time_str,
        "amount": -amount,  # 修正为负数
        "rate": rate,
        "fee": fee,
        "remark": remark
    })

    await render_summary(update, context)


# 下发处理
async def handle_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in bookkeeping_data or not bookkeeping_data[chat_id]["active"]:
        return

    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    # 支持可选备注
    match = re.match(r"^下发(\d+(\.\d{1,2})?)([Uu])?(?:\s+(.+))?$", text)
    if not match:
        return

    amount = float(match.group(1))
    has_u = match.group(3) is not None
    remark = match.group(4) or ""

    rate = bookkeeping_data[chat_id].get("rate", 1.0)
    fee = bookkeeping_data[chat_id].get("fee", 0.0)
    time_str = now_beijing().strftime("%H:%M:%S")

    if has_u:
        coin_amount = amount * rate / (1 - fee / 100)
        bookkeeping_data[chat_id]["out"].append({
            "time": time_str,
            "amount": coin_amount,
            "usdt_amount": amount,
            "is_usdt": True,
            "remark": remark
        })
    else:
        usdt_val = amount * (1 - fee / 100) / rate
        bookkeeping_data[chat_id]["out"].append({
            "time": time_str,
            "amount": amount,
            "usdt_amount": usdt_val,
            "is_usdt": False,
            "remark": remark
        })

    await render_summary(update, context)

# 下发修正处理
async def handle_payout_correction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in bookkeeping_data or not bookkeeping_data[chat_id]["active"]:
        return

    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    # 支持可选备注
    match = re.match(r"^下发(-?\d+(\.\d{1,2})?)([Uu])?(?:\s+(.+))?$", text)
    if not match:
        return

    amount_str = match.group(1)
    has_u = match.group(3) is not None
    remark = match.group(4) or ""

    try:
        amount = float(amount_str)
    except ValueError:
        return

    rate = bookkeeping_data[chat_id].get("rate", 1.0)
    fee = bookkeeping_data[chat_id].get("fee", 0.0)
    time_str = now_beijing().strftime("%H:%M:%S")

    if has_u:
        coin_amount = amount * rate / (1 - fee / 100)
        bookkeeping_data[chat_id]["out"].append({
            "time": time_str,
            "amount": coin_amount,
            "usdt_amount": amount,
            "is_usdt": True,
            "remark": remark
        })
    else:
        usdt_val = amount * (1 - fee / 100) / rate
        bookkeeping_data[chat_id]["out"].append({
            "time": time_str,
            "amount": amount,
            "usdt_amount": usdt_val,
            "is_usdt": False,
            "remark": remark
        })

    await render_summary(update, context)

# 保存账单命令
async def handle_save_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in bookkeeping_data:
        return

    # 异步调用
    if not await is_admin_or_operator(update, context):
        return

    now = now_beijing().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(HISTORY_DIR, f"{chat_id}_{now}.json")

    data_to_save = bookkeeping_data[chat_id].copy()
    data_to_save["operator_usernames"] = list(data_to_save.get("operator_usernames", []))

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

    bookkeeping_data[chat_id].update({
        "in": [],
        "out": [],
        "rate": 1.0,
        "fee": 0.0,
        "active": False,
    })

    await update.message.reply_text("✅ 账单已保存，记账数据已清空。")

# 结束记账命令（自动保存）
async def handle_end_bookkeeping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_save_bill(update, context)


# --- 改动部分 START ---
# 查询账单按钮点击处理，支持分页和筛选
async def handle_query_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    # 进入年份选择菜单
    files = [f for f in os.listdir(HISTORY_DIR) if f.startswith(str(chat_id))]
    if not files:
        await query.edit_message_text("暂无历史账单记录。")
        return

    # 提取所有年份，去重排序
    years = sorted(set(f[ len(str(chat_id))+1:len(str(chat_id))+5 ] for f in files), reverse=True)
    buttons = []
    for y in years:
        buttons.append([InlineKeyboardButton(y, callback_data=f"bill_year:{y}")])
    buttons.append([InlineKeyboardButton("全部账单", callback_data="bill_list:all:0")])
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text("📅 请选择年份查看账单：", reply_markup=markup)


async def handle_bill_year_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # 格式 bill_year:<year>
    year = data.split(":")[1]
    chat_id = query.message.chat_id

    # 提取该年所有账单文件
    files = [f for f in os.listdir(HISTORY_DIR) if f.startswith(str(chat_id))]
    filtered_files = [f for f in files if f[len(str(chat_id))+1:len(str(chat_id))+5] == year]

    if not filtered_files:
        await query.edit_message_text("该年份暂无账单记录。")
        return

    # 提取月份，去重排序
    months = sorted(set(f[len(str(chat_id))+5:len(str(chat_id))+7] for f in filtered_files), reverse=True)
    buttons = []
    for m in months:
        buttons.append([InlineKeyboardButton(f"{year}-{m}", callback_data=f"bill_month:{year}{m}:0")])
    buttons.append([InlineKeyboardButton("返回年份选择", callback_data="query_bill")])
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(f"📅 请选择 {year} 年的月份：", reply_markup=markup)


async def handle_bill_month_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # 格式 bill_month:<yyyymm>:<page>
    parts = data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("参数错误。")
        return

    yyyymm = parts[1]
    page = int(parts[2])
    chat_id = query.message.chat_id

    files = [f for f in os.listdir(HISTORY_DIR) if f.startswith(str(chat_id))]
    filtered_files = [f for f in files if f[len(str(chat_id))+1:len(str(chat_id))+7] == yyyymm]

    await show_bill_list(update, context, filtered_files, page, prefix=f"账单列表 {yyyymm}")


async def handle_bill_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # 格式 bill_list:<all|yyyymm>:<page>
    parts = data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("参数错误。")
        return

    filter_ = parts[1]
    page = int(parts[2])
    chat_id = query.message.chat_id

    files = [f for f in os.listdir(HISTORY_DIR) if f.startswith(str(chat_id))]
    if filter_ != "all":
        files = [f for f in files if f[len(str(chat_id))+1:len(str(chat_id))+7] == filter_]

    await show_bill_list(update, context, files, page, prefix="账单列表")


async def show_bill_list(update: Update, context: ContextTypes.DEFAULT_TYPE, files, page, prefix="账单列表"):
    query = update.callback_query

    PAGE_SIZE = 10
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_files = files[start:end]

    if not page_files:
        await query.edit_message_text("无更多账单。")
        return

    buttons = []
    for f in page_files:
        buttons.append([
            InlineKeyboardButton(f[len(str(update.effective_chat.id))+1:-5], callback_data=f"bill_view:{f}"),
            InlineKeyboardButton("删除", callback_data=f"bill_delete:{f}")
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"bill_list:all:{page-1}"))
    if end < len(files):
        nav_buttons.append(InlineKeyboardButton("下一页 ➡️", callback_data=f"bill_list:all:{page+1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton("返回", callback_data="query_bill")])

    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(f"📄 {prefix}（第{page+1}页，共{math.ceil(len(files)/PAGE_SIZE)}页）", reply_markup=markup)

async def handle_bill_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    filepath = os.path.join(HISTORY_DIR, filename)
    if not os.path.exists(filepath):
        await query.edit_message_text("账单不存在。")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = [f"账单时间: {filename[-19:-5]}\n"]
    lines.append(f"操作人: {', '.join(data.get('operator_usernames', [])) or '无'}")

    def calculate_usdt(amount, fee, rate):
        if rate is None or fee is None:
            return 0
        return amount * (1 - fee / 100) / rate if rate else 0

    total_deposit = sum([item["amount"] for item in data.get("in", [])])
    total_payout = sum([item["amount"] for item in data.get("out", [])])

    total_deposit_usdt = sum([calculate_usdt(rec["amount"], rec.get("fee", 0), rec.get("rate")) for rec in data.get("in", [])])
    total_payout_usdt = 0
    for item in data.get("out", []):
        if "usdt_amount" in item:
            total_payout_usdt += item["usdt_amount"]
        else:
            fee = data.get("fee", 0)
            rate = data.get("rate", 1)
            total_payout_usdt += calculate_usdt(item["amount"], fee, rate)

    lines.append("\n入款记录:")
    for rec in data.get("in", []):
        usdt_val = calculate_usdt(rec["amount"], rec.get("fee", 0), rec.get("rate"))
        remark = f" {rec.get('remark','')}" if rec.get("remark") else ""
        lines.append(
            f"{rec['time']} +{rec['amount']:.2f} ({rec.get('rate', 'N/A')}/{rec.get('fee', 'N/A')}%) ≈ {usdt_val:.2f} USDT {remark}"
        )

    lines.append("\n下发记录:")
    for rec in data.get("out", []):
        usdt_val = rec.get("usdt_amount")
        if usdt_val is None:
            fee = data.get("fee", 0)
            rate = data.get("rate", 1)
            usdt_val = calculate_usdt(rec["amount"], fee, rate)
        remark = f" {rec.get('remark','')}" if rec.get("remark") else ""
        lines.append(f"{rec['time']} -{usdt_val:.2f} USDT {remark}")

    lines.append(f"\n默认费率: {data.get('fee', 0):.2f}%")
    lines.append(f"默认汇率: {data.get('rate', 0) if data.get('rate') is not None else '未设置'}")

    lines.append(f"\n总入款: {total_deposit:.2f} | {total_deposit_usdt:.2f} USDT")
    lines.append(f"已下发: {total_payout_usdt:.2f} USDT")
    lines.append(f"未下发: {total_deposit_usdt - total_payout_usdt:.2f} USDT")

    await query.edit_message_text("\n".join(lines))

async def handle_bill_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filename = query.data.split(":", 1)[1]
    filepath = os.path.join(HISTORY_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        await query.edit_message_text(f"✅ 账单 {filename} 已删除。")
    else:
        await query.edit_message_text("账单文件不存在。")
# --- 改动部分 END ---


# 设置汇率
async def handle_set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    match = re.match(r"^设置汇率\s*(\d+(\.\d{1,2})?)$", text, re.IGNORECASE)
    if not match:
        return

    if not await is_admin_or_operator(update, context):
        return

    rate = float(match.group(1))
    group_data = bookkeeping_data.setdefault(chat_id, {})
    previously_set = "rate" in group_data and group_data["rate"] is not None
    group_data.update({"rate": rate})

    if group_data.get("active") and previously_set:
        await update.message.reply_text(f"✅ 汇率已设置为 {rate:.2f}（已影响当前记账）")
    else:
        await update.message.reply_text(f"✅ 汇率已设置为 {rate:.2f}（当前记账已立即生效）")

    # 设置后显示摘要（仅在已启用记账时）
    if group_data.get("active"):
        await render_summary(update, context)



# 设置费率
async def handle_set_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    match = re.match(r"^设置费率\s*(-?\d+(\.\d{1,2})?)%?$", text, re.IGNORECASE)
    if not match:
        return

    if not await is_admin_or_operator(update, context):
        return

    fee = float(match.group(1))
    group_data = bookkeeping_data.setdefault(chat_id, {})
    previously_set = "fee" in group_data and group_data["fee"] is not None
    group_data.update({"fee": fee})

    if group_data.get("active") and previously_set:
        await update.message.reply_text(f"✅ 费率已设置为 {fee:.2f}%（已影响当前记账）")
    else:
        await update.message.reply_text(f"✅ 费率已设置为 {fee:.2f}%（当前记账已立即生效）")

    # 设置后显示摘要（仅在已启用记账时）
    if group_data.get("active"):
        await render_summary(update, context)


# 添加操作人（支持一次多个）
async def handle_add_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    match = re.match(r"^添加操作人\s+(.+)$", text, re.IGNORECASE)
    if not match:
        return

    usernames_str = match.group(1)
    # 支持空格或逗号分隔多个用户名
    usernames = re.split(r"[\s,]+", usernames_str)
    usernames = [u.lstrip("@").lower() for u in usernames if u.strip()]

    existing_usernames = bookkeeping_data.setdefault(chat_id, {}).setdefault("operator_usernames", [])
    added_users = []
    for u in usernames:
        if u not in [x.lower() for x in existing_usernames]:
            existing_usernames.append(u)
            added_users.append(u)

    if added_users:
        await update.message.reply_text(f"✅ 已添加操作人：{', '.join(added_users)}")
    else:
        await update.message.reply_text("⚠️ 所有用户名已存在或无效")

# 删除操作人（支持一次多个）
async def handle_remove_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    match = re.match(r"^删除操作人\s+(.+)$", text, re.IGNORECASE)
    if not match:
        return

    usernames_str = match.group(1)
    usernames = re.split(r"[\s,]+", usernames_str)
    usernames = [u.lstrip("@").lower() for u in usernames if u.strip()]

    existing_usernames = bookkeeping_data.setdefault(chat_id, {}).setdefault("operator_usernames", [])
    deleted_users = []

    for u in usernames:
        lower_existing = [x.lower() for x in existing_usernames]
        if u in lower_existing:
            index = lower_existing.index(u)
            existing_usernames.pop(index)
            deleted_users.append(u)

    if deleted_users:
        await update.message.reply_text(f"✅ 已删除操作人：{', '.join(deleted_users)}")
    else:
        await update.message.reply_text("⚠️ 用户名不存在或无效")

# 渲染账单摘要
async def render_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = bookkeeping_data.get(chat_id, {})
    if not data:
        return

    deposit_records = data.get("in", [])[-8:]
    payout_records = data.get("out", [])[-8:]

    # 计算总入款USDT，每条用对应的 rate 和 fee
    def calculate_usdt(amount, fee, rate):
        if rate is None or fee is None:
            return 0
        return amount * (1 - fee / 100) / rate if rate else 0

    total_deposit = sum([item["amount"] for item in data.get("in", [])])
    total_deposit_usdt = sum([calculate_usdt(rec["amount"], rec.get("fee", 0), rec.get("rate")) for rec in data.get("in", [])])

    total_payout_usdt = 0
    for item in data.get("out", []):
        if "usdt_amount" in item:
            total_payout_usdt += item["usdt_amount"]
        else:
            fee = data.get("fee", 0)
            rate = data.get("rate", 1)
            total_payout_usdt += calculate_usdt(item["amount"], fee, rate)

    total_payout = sum([item["amount"] for item in data.get("out", [])])
    remain_usdt = total_deposit_usdt - total_payout_usdt

    now = now_beijing().strftime("%Y年%m月%d日  %H:%M:%S")
    lines = [f"{now}\n"]

    # 入款摘要
    lines.append(f"入款({len(deposit_records)}笔)")
    for rec in deposit_records:
        usdt_val = calculate_usdt(rec["amount"], rec.get("fee", 0), rec.get("rate"))
        remark = f" {rec.get('remark','')}" if rec.get("remark") else ""
        sign = "+" if rec["amount"] >= 0 else "-"
        lines.append(
            f"{rec['time']} {sign}{abs(rec['amount']):.2f} ({rec.get('rate','N/A')}/{rec.get('fee','N/A')}%) ≈ {usdt_val:.2f} USDT {remark}"
        )

    # 下发摘要
    lines.append(f"\n下发({len(payout_records)}笔)")
    for rec in payout_records:
        usdt_val = rec.get("usdt_amount", 0)
        remark = f"{rec.get('remark','')}" if rec.get("remark") else ""
        lines.append(f"{rec['time']} -{usdt_val:.2f} USDT {remark}")

    lines.append(f"\n默认费率: {data.get('fee', 0):.2f}%")
    lines.append(f"默认汇率: {data.get('rate', 0) if data.get('rate') is not None else '未设置'}")

    lines.append(f"\n总入款: {total_deposit:.2f} | {total_deposit_usdt:.2f}USDT")
    lines.append(f"应下发: {total_deposit_usdt:.2f}USDT")
    lines.append(f"已下发: {total_payout_usdt:.2f}USDT")
    lines.append(f"未下发: {remain_usdt:.2f}USDT")
    lines.append(f"\n总记录: {len(data.get('in', [])) + len(data.get('out', []))}条, 显示{len(deposit_records) + len(payout_records)}条")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("查询账单", callback_data="query_bill")]
    ])

    await update.message.reply_text(
        "\n".join(lines)
    )

async def handle_bot_removed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member_update = update.my_chat_member
    if not chat_member_update:
        context.application.logger.warning("handle_bot_removed: update.my_chat_member is None")
        return

    old_status = chat_member_update.old_chat_member.status
    new_status = chat_member_update.new_chat_member.status
    bot_id = context.bot.id

    context.application.logger.info(f"handle_bot_removed triggered for chat {chat_member_update.chat.id}")

    if chat_member_update.new_chat_member.user.id == bot_id:
        if old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and \
           new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:

            chat_id = chat_member_update.chat.id
            # 删除缓存账单
            if chat_id in bookkeeping_data:
                del bookkeeping_data[chat_id]

            # 删除历史账单文件
            for f in os.listdir(HISTORY_DIR):
                if f.startswith(str(chat_id)):
                    try:
                        os.remove(os.path.join(HISTORY_DIR, f))
                    except Exception as e:
                        context.application.logger.error(f"删除群组账单文件失败: {f} 错误: {e}")

            context.application.logger.info(f"机器人被移出群组 {chat_member_update.chat.title}({chat_id})，清除对应账单缓存和历史账单。")

# 新增一个处理文本“查询账单”的函数，触发时发送内联按钮
async def handle_query_bill_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    files = [f for f in os.listdir(HISTORY_DIR) if f.startswith(str(chat_id))]
    if not files:
        await update.message.reply_text("暂无历史账单记录。")
        return

    years = sorted(set(f[len(str(chat_id))+1:len(str(chat_id))+5] for f in files), reverse=True)
    buttons = [[InlineKeyboardButton(y, callback_data=f"bill_year:{y}")] for y in years]
    buttons.append([InlineKeyboardButton("全部账单", callback_data="bill_list:all:0")])
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("📅 请选择年份查看账单：", reply_markup=markup)

# ========== 计算功能 ==========
import re
import ast
import operator as op
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# 安全运算符映射
operators = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.USub: op.neg,
}

def safe_eval(expr: str):
    """安全计算表达式"""
    # 替换全角运算符为半角
    expr = expr.replace("＋", "+").replace("－", "-").replace("×", "*").replace("÷", "/")
    node = ast.parse(expr, mode='eval').body

    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            return operators[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            return operators[type(node.op)](_eval(node.operand))
        else:
            raise ValueError("不支持的表达式")
    return _eval(node)

# 支持数字、运算符、括号和空格，但至少有一个运算符
calc_pattern = re.compile(r"^\s*[-+]?(\d+(\.\d+)?|\([^\)]+\))(\s*[-+*/＋－×÷]\s*[-+]?(\d+(\.\d+)?|\([^\)]+\)))+\s*$")

# 屏蔽记账命令关键字
blocked_keywords = ["入款", "下发", "设置汇率", "设置费率", "添加操作人", "删除操作人", "保存账单", "结束记账"]

async def handle_calculation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    logger.info(f"🧮 进入计算模块: {text}")

    # 忽略记账相关命令
    if any(k in text for k in blocked_keywords):
        logger.info("⛔ 忽略记账命令")
        return

    # 不符合计算正则则跳过
    if not calc_pattern.fullmatch(text):
        logger.info("❌ 不是合法计算表达式")
        return

    try:
        result = safe_eval(text)
        # 整数显示整数，浮点数保留 4 位小数
        if isinstance(result, float) and result.is_integer():
            result_str = str(int(result))
        else:
            result_str = f"{result:.4f}"

        await update.message.reply_text(f"🧮 计算结果: {text} = {result_str}")

    except Exception as e:
        logger.warning(f"计算出错: {text} | {e}")
        await update.message.reply_text(f"❌ 计算出错: {e}")
