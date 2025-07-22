import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

ETHERSCAN_API_KEY = "YourEtherscanAPIKey"  # 请替换为你自己的API Key
PAGE_SIZE = 5

async def fetch_json(session, url):
    async with session.get(url) as resp:
        return await resp.json()

async def query_eth_balance(address):
    url = (
        f"https://api.etherscan.io/api"
        f"?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
    )
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        if data.get("status") == "1":
            balance_wei = int(data.get("result", 0))
            return balance_wei / 1e18
        return 0.0

async def query_eth_transactions(address, start=0, limit=PAGE_SIZE):
    page_num = start // limit + 1
    url = (
        f"https://api.etherscan.io/api"
        f"?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&page={page_num}&offset={limit}&sort=desc&apikey={ETHERSCAN_API_KEY}"
    )
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        if data.get("status") == "1":
            return data.get("result", [])
        return []

def format_eth_transactions(transactions, address):
    lines = []
    addr_lower = address.lower()
    for tx in transactions:
        time_stamp = int(tx.get("timeStamp", 0))
        time_str = datetime.fromtimestamp(time_stamp).strftime("%Y-%m-%d %H:%M")
        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()
        direction = "⬅ 收到" if to_addr == addr_lower else "➡ 发出"

        value_eth = int(tx.get("value", 0)) / 1e18

        lines.append(f"{time_str} {direction} {value_eth:.6f} ETH")

    return "\n".join(lines) if lines else "无转账记录"

async def send_eth_transfer_records(update: Update, context: ContextTypes.DEFAULT_TYPE, address, start):
    transactions = await query_eth_transactions(address, start, PAGE_SIZE)
    text = format_eth_transactions(transactions, address)

    page_num = start // PAGE_SIZE + 1
    text = f"{text}\n\n第 {page_num} 页"

    keyboard = []
    if start > 0:
        keyboard.append(InlineKeyboardButton("⬅ 上一页", callback_data=f"eth_page_{start - PAGE_SIZE}"))
    if len(transactions) == PAGE_SIZE:
        keyboard.append(InlineKeyboardButton("下一页 ➡", callback_data=f"eth_page_{start + PAGE_SIZE}"))

    reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None

    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
        await update.callback_query.answer()
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def handle_eth_address_input(update: Update, context: ContextTypes.DEFAULT_TYPE, address):
    context.user_data["address"] = address
    context.user_data["chain"] = "eth"
    context.user_data["start"] = 0

    await update.message.reply_text(f"🔎 查询 ETH 地址：{address}")

    try:
        balance = await query_eth_balance(address)
        base_info = (
            f"💰 ETH 余额：{balance:.6f} ETH\n"
            f"📜 最近转账记录："
        )
        await update.message.reply_text(base_info)
        await send_eth_transfer_records(update, context, address, 0)
    except Exception as e:
        await update.message.reply_text(f"❌ 查询失败：{str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("eth_page_"):
        start = int(data.split("_")[-1])
        address = context.user_data.get("address")
        if not address:
            await query.answer("地址信息缺失，请重新发送地址。", show_alert=True)
            return
        await send_eth_transfer_records(update, context, address, start)
