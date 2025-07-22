import os
import re
import json
import math
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatMemberUpdated,
)
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus

# 群组独立账本缓存，格式：chat_id -> {active, in, out, rate, fee, operator_usernames}
bookkeeping_data = {}

# 历史账单存储路径
HISTORY_DIR = "data/bills"
os.makedirs(HISTORY_DIR, exist_ok=True)

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
        "rate": None,
        "fee": None,
        "operator_usernames": bookkeeping_data.get(chat_id, {}).get("operator_usernames", []),
    }
    await update.message.reply_text("✅ 已开始记账。请设置汇率和费率后再输入入款记录。")
# --- 改动部分 END ---


# 入款处理
async def handle_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in bookkeeping_data or not bookkeeping_data[chat_id]["active"]:
        return

    # 获取当前群组的记账数据
    group_data = bookkeeping_data[chat_id]

    # 检查是否已设置汇率和费率
    if group_data.get("rate") is None or group_data.get("fee") is None:
        await update.message.reply_text("⚠️ 请先设置汇率和费率后才能进行入款。")
        return

    # 异步权限判断
    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    match = re.match(r"^(入款|\+)(\d+(\.\d{1,2})?)$", text, re.IGNORECASE)
    if not match:
        return

    amount = float(match.group(2))
    time_str = datetime.now().strftime("%H:%M:%S")
    bookkeeping_data[chat_id]["in"].append({"time": time_str, "amount": amount})

    await render_summary(update, context)


# 入款修正处理
async def handle_deposit_correction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in bookkeeping_data or not bookkeeping_data[chat_id]["active"]:
        return

    # 异步调用
    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    match = re.match(r"^(入款-|\-)(\d+(\.\d{1,2})?)$", text, re.IGNORECASE)
    if not match:
        return

    amount = float(match.group(2))
    time_str = datetime.now().strftime("%H:%M:%S")
    bookkeeping_data[chat_id]["in"].append({"time": time_str, "amount": -amount})
    await render_summary(update, context)

# 下发处理
async def handle_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in bookkeeping_data or not bookkeeping_data[chat_id]["active"]:
        return

    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    match = re.match(r"^下发(\d+(\.\d{1,2})?)([Uu])?$", text)
    if not match:
        return

    amount = float(match.group(1))
    has_u = match.group(3) is not None

    rate = bookkeeping_data[chat_id].get("rate")
    fee = bookkeeping_data[chat_id].get("fee")

    time_str = datetime.now().strftime("%H:%M:%S")

    if has_u:
        # 反算币种金额 = USDT * 汇率 / (1 - 费率%)
        coin_amount = amount * rate / (1 - fee / 100)
        bookkeeping_data[chat_id]["out"].append({
            "time": time_str,
            "amount": coin_amount,
            "usdt_amount": amount,
            "is_usdt": True
        })
    else:
        bookkeeping_data[chat_id]["out"].append({
            "time": time_str,
            "amount": amount,
            "usdt_amount": amount * (1 - fee / 100) / rate if rate else 0,
            "is_usdt": False
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
    match = re.match(r"^下发-?(\d+(\.\d{1,2})?)([Uu])?$", text)
    if not match:
        return

    amount = float(match.group(1))
    has_u = match.group(3) is not None

    rate = bookkeeping_data[chat_id].get("rate")
    fee = bookkeeping_data[chat_id].get("fee")

    time_str = datetime.now().strftime("%H:%M:%S")

    if has_u:
        coin_amount = amount * rate / (1 - fee / 100)
        bookkeeping_data[chat_id]["out"].append({
            "time": time_str,
            "amount": -coin_amount,
            "usdt_amount": -amount,
            "is_usdt": True
        })
    else:
        bookkeeping_data[chat_id]["out"].append({
            "time": time_str,
            "amount": -amount,
            "usdt_amount": -amount * (1 - fee / 100) / rate if rate else 0,
            "is_usdt": False
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

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(HISTORY_DIR, f"{chat_id}_{now}.json")

    data_to_save = bookkeeping_data[chat_id].copy()
    data_to_save["operator_usernames"] = list(data_to_save.get("operator_usernames", []))

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

    bookkeeping_data[chat_id].update({
        "in": [],
        "out": [],
        "rate": None,
        "fee": None,
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

    for typ in ["in", "out"]:
        lines.append("\n入款记录:" if typ == "in" else "\n下发记录:")
        for rec in data.get(typ, []):
            lines.append(f"{rec['time']}  {rec['amount']:+.2f}")

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

    if bookkeeping_data.get(chat_id, {}).get("rate") is not None and bookkeeping_data[chat_id].get("active"):
        await update.message.reply_text("❌ 当前已启用记账，无法更改汇率。请先保存或结束记账。")
        return

    rate = float(match.group(1))
    bookkeeping_data.setdefault(chat_id, {}).update({"rate": rate})
    await update.message.reply_text(f"✅ 汇率已设置为 {rate:.2f}")


# 设置费率
async def handle_set_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    match = re.match(r"^设置费率\s*(-?\d+(\.\d{1,2})?)%?$", text, re.IGNORECASE)
    if not match:
        return

    if not await is_admin_or_operator(update, context):
        return

    if bookkeeping_data.get(chat_id, {}).get("fee") is not None and bookkeeping_data[chat_id].get("active"):
        await update.message.reply_text("❌ 当前已启用记账，无法更改费率。请先保存或结束记账。")
        return

    fee = float(match.group(1))
    bookkeeping_data.setdefault(chat_id, {}).update({"fee": fee})
    await update.message.reply_text(f"✅ 费率已设置为 {fee:.2f}%")


# 添加操作人
async def handle_add_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    match = re.match(r"^添加操作人\s+@?(\w+)$", text, re.IGNORECASE)
    if not match:
        return

    username = match.group(1).lower()
    usernames = bookkeeping_data.setdefault(chat_id, {}).setdefault("operator_usernames", [])
    if username not in [u.lower() for u in usernames]:
        usernames.append(username)
    await update.message.reply_text(f"✅ 已添加操作人：{username}")

# 删除操作人
async def handle_remove_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await is_admin_or_operator(update, context):
        return

    text = update.message.text.strip()
    match = re.match(r"^删除操作人\s+@?(\w+)$", text, re.IGNORECASE)
    if not match:
        return

    username = match.group(1).lower()
    usernames = bookkeeping_data.setdefault(chat_id, {}).setdefault("operator_usernames", [])

    # 保持不区分大小写删除
    usernames_lower = [u.lower() for u in usernames]
    if username in usernames_lower:
        index = usernames_lower.index(username)
        usernames.pop(index)
        await update.message.reply_text(f"✅ 已删除操作人：{username}")

# 渲染账单摘要
async def render_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = bookkeeping_data.get(chat_id, {})
    if not data:
        return

    deposit_records = data.get("in", [])[-8:]
    payout_records = data.get("out", [])[-8:]
    rate = data.get("rate")
    fee = data.get("fee")

    def calculate_usdt(amount):
        return amount * (1 - fee / 100) / rate if rate else 0

    total_deposit = sum([item["amount"] for item in data.get("in", [])])

    # 计算总下发USDT
    total_payout_usdt = 0
    for item in data.get("out", []):
        if "usdt_amount" in item:
            total_payout_usdt += item["usdt_amount"]
        else:
            total_payout_usdt += calculate_usdt(item["amount"])

    total_deposit_usdt = calculate_usdt(total_deposit)
    total_payout = sum([item["amount"] for item in data.get("out", [])])
    remain = total_deposit - total_payout
    remain_usdt = total_deposit_usdt - total_payout_usdt

    now = datetime.now().strftime("%Y年%m月%d日  %H:%M:%S")
    lines = [f"{now}\n"]

    lines.append(f"入款({len(deposit_records)}笔)")
    for rec in deposit_records:
        lines.append(f"{rec['time']}  +{rec['amount']:.2f}")

    lines.append(f"\n下发({len(payout_records)}笔)")
    for rec in payout_records:
        if rec.get("is_usdt", False):
            lines.append(f"{rec['time']}  -{rec['amount']:.2f} | {rec['usdt_amount']:.2f}USDT")
        else:
            usdt_val = calculate_usdt(rec["amount"])
            lines.append(f"{rec['time']}  -{rec['amount']:.2f} | {usdt_val:.2f}USDT")

    lines.append(f"\n费率: {fee:.2f}%")
    lines.append(f"USDT汇率: {rate:.2f}")
    lines.append(f"\n总入款: {total_deposit:.2f} | {total_deposit_usdt:.2f}USDT")
    lines.append(f"\n应下发: {total_deposit:.2f} | {total_deposit_usdt:.2f}USDT")
    lines.append(f"已下发: {total_payout:.2f} | {total_payout_usdt:.2f}USDT")
    lines.append(f"未下发: {remain:.2f} | {remain_usdt:.2f}USDT")
    lines.append(f"\n总记录: {len(data.get('in', [])) + len(data.get('out', []))}条, 显示{len(deposit_records) + len(payout_records)}条")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("查询账单", callback_data="query_bill")
        ]
    ])

    await update.message.reply_text("\n".join(lines), reply_markup=keyboard)



# 监听机器人被移出群组事件，自动清除缓存账单
async def handle_bot_removed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member_update: ChatMemberUpdated = update.chat_member
    chat = chat_member_update.chat
    old_status = chat_member_update.old_chat_member.status
    new_status = chat_member_update.new_chat_member.status

    bot_id = context.bot.id

    # 判断是否机器人被移出群组
    if chat_member_update.new_chat_member.user.id == bot_id:
        if old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
            chat_id = chat.id
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

            context.application.logger.info(f"机器人被移出群组 {chat.title}({chat_id})，清除对应账单缓存和历史账单。")
