import aiohttp
import base58
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

LABELS = {
    "USDT": "稳定币",
    "TRX": "波场币",
    "trx": "TRX 主币",
    "Tether USD": "USDT",
    "freee.vip": "免费能量平台",
    "hash8net": "Hash8 矿池",
    "GasFreeTransferSolution": "免 Gas 转账",
    "fenergy.fun": "Fenergy 能量平台",
    "EnergyRental": "能量租赁",
    "EnergyRentalV2": "能量租赁 V2",
}

PAGE_SIZE = 10

async def fetch_json(session, url):
    async with session.get(url) as resp:
        return await resp.json()


async def query_trx_balance(address):
    url = f"https://api.trongrid.io/v1/accounts/{address}"
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        if "data" in data and len(data["data"]) > 0:
            balance_sun = int(data["data"][0].get("balance", 0))
            return balance_sun / 1e6
        return 0.0


async def query_trx_account_info(address):
    url = f"https://apilist.tronscanapi.com/api/account?address={address}"
    async with aiohttp.ClientSession() as session:
        return await fetch_json(session, url)


async def query_trc20_tokens(address):
    url = f"https://apilist.tronscanapi.com/api/account?address={address}"
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        tokens = []
        for token in data.get("tokens", []):
            try:
                bal = float(token.get("balance", 0))
            except Exception:
                bal = 0.0
            name = token.get("tokenName", "未知")
            label = LABELS.get(name, "其他")
            tokens.append((f"{name}（{label}）", bal / 1e6))
        return tokens


async def query_transfer_records_tron(address, start=0, limit=PAGE_SIZE):
    url = (
        f"https://apilist.tronscanapi.com/api/token_trc20/transfers"
        f"?relatedAddress={address}&limit={limit}&start={start}&sort=-block_ts"
    )
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        transfers = data.get("token_transfers", [])
        total = data.get("total", 0)
        return transfers, total


def format_transfer_records(transfers, address):
    lines = []
    addr_lower = address.lower()
    for tr in transfers:
        ts = tr.get("block_ts", 0) // 1000
        time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

        from_addr = tr.get("from_address", "").lower()
        to_addr = tr.get("to_address", "").lower()

        direction = "⬅ 收到" if to_addr == addr_lower else "➡ 发出"
        other_addr = from_addr if direction == "⬅ 收到" else to_addr

        quant = int(tr.get("quant", 0))
        token_info = tr.get("tokenInfo", {})
        decimals = int(token_info.get("tokenDecimal", 6))
        amount = quant / (10 ** decimals)

        symbol = token_info.get("tokenAbbr", "TOKEN")
        label = LABELS.get(symbol, "其他")

        lines.append(
            f"{time_str} {direction} {amount:.6f} {symbol}（{label}）\n对方地址：{other_addr}"
        )

    return "\n\n".join(lines) if lines else "无转账记录"


async def query_resource(address):
    url = "https://api.trongrid.io/wallet/getAccountResource"
    payload = {"address": base58.b58decode_check(address).hex()}
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"资源查询失败，HTTP {resp.status}")
            return await resp.json()


async def send_transfer_records(update, context, address, start):
    transfers, total = await query_transfer_records_tron(address, start, PAGE_SIZE)
    text = format_transfer_records(transfers, address)

    page_num = start // PAGE_SIZE + 1
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    text = f"{text}\n\n第 {page_num} 页 / 共 {total_pages} 页"

    keyboard = []
    if start > 0:
        keyboard.append(InlineKeyboardButton("⬅ 上一页", callback_data=f"page_{start - PAGE_SIZE}"))
    if start + PAGE_SIZE < total:
        keyboard.append(InlineKeyboardButton("下一页 ➡", callback_data=f"page_{start + PAGE_SIZE}"))

    reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None

    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
        await update.callback_query.answer()
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_address_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    if not address.startswith("T"):
        await update.message.reply_text("❌ 地址格式不正确，请输入TRON地址（以T开头）")
        return

    context.user_data['address'] = address
    context.user_data['start'] = 0

    await update.message.reply_text(f"🔎 正在查询地址：{address}")

    try:
        account_info = await query_trx_account_info(address)
        trx_balance = await query_trx_balance(address)
        tokens = await query_trc20_tokens(address)

        trx_count = account_info.get("totalTransactionCount", 0)
        create_time = account_info.get("date_created") or account_info.get("create_time") or 0
        first_tx = datetime.fromtimestamp(int(create_time) // 1000).strftime("%Y-%m-%d %H:%M") if create_time else "未知"

        last_op = account_info.get("lastActiveTime") or account_info.get("latest_operation_time") or 0
        last_tx = datetime.fromtimestamp(int(last_op) // 1000).strftime("%Y-%m-%d %H:%M") if last_op else "未知"

        signature = account_info.get("active", False) or bool(account_info.get("activePermissions"))
        sig_status = "✅ 已激活" if signature else "❌ 未激活"

        try:
            resource = await query_resource(address)
            energy = resource.get("energy_remaining", 0)
            bandwidth = resource.get("freeNetRemaining", 0)
        except Exception:
            energy = 0
            bandwidth = 0

        usdt = 0.0
        for name, bal in tokens:
            if "USDT" in name:
                usdt = bal
                break

        base_info = (
            f"🔎 查询地址：{address}\n\n"
            f"💡 交易次数：{trx_count} 次\n"
            f"🔰 签名状态：{sig_status}\n\n"
            f"💰 TRX 余额：{trx_balance:.6f} TRX\n"
            f"💰 USDT 余额：{usdt:.6f} USDT\n\n"
            f"📜 最近转账记录："
        )


        await update.message.reply_text(base_info)
        await send_transfer_records(update, context, address, 0)

    except Exception as e:
        await update.message.reply_text(f"❌ 查询失败：{str(e)}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("page_"):
        start = int(data.split("_")[1])
        address = context.user_data.get('address')
        if not address:
            await query.answer("地址信息缺失，请重新发送地址。", show_alert=True)
            return
        await send_transfer_records(update, context, address, start)
