import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

PAGE_SIZE = 15
MAX_PAGES_PER_ADDRESS = 5  # 每个地址最多请求 5 页，每页 50 条 = 最多 250 条记录

def is_tron_address(addr):
    return addr.startswith("T") and len(addr) == 34

def parse_addresses(text):
    parts = [p.strip() for p in text.replace(",", " ").split()]
    addrs = [a for a in parts if is_tron_address(a)]
    return addrs[:5]

async def fetch_json(session, url):
    async with session.get(url) as resp:
        return await resp.json()

async def fetch_all_trc20_transfers(addr, max_pages=MAX_PAGES_PER_ADDRESS):
    all_tx = []
    async with aiohttp.ClientSession() as session:
        for page in range(max_pages):
            url = (
                f"https://apilist.tronscanapi.com/api/token_trc20/transfers"
                f"?relatedAddress={addr}&limit=50&start={page * 50}&sort=-block_ts"
            )
            data = await fetch_json(session, url)
            txs = data.get("token_transfers", [])
            if not txs:
                break
            all_tx.extend(txs)
    return all_tx

async def handle_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "请输入 2~5 个 TRON 地址，使用空格或逗号分隔，机器人将查询它们之间的相互 TRC20 转账记录。"
    )
    context.user_data.clear()
    context.user_data["awaiting_tx_addresses"] = True

async def handle_transaction_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_tx_addresses"):
        return

    text = update.message.text.strip()
    addrs = parse_addresses(text)

    if len(addrs) < 2:
        await update.message.reply_text("❌ 请至少输入两个有效 TRON 地址，最多5个，使用空格或逗号分隔。")
        return

    unique_addrs = list(set(addrs))
    if len(unique_addrs) < 2:
        await update.message.reply_text("❌ 请输入至少两个不同的 TRON 地址，不能全部相同。")
        return

    addrs = unique_addrs

    await update.message.reply_text(f"🔍 正在查询 {len(addrs)} 个地址之间的相互 TRC20 转账记录，请稍候...")

    all_transfers = {}
    for addr in addrs:
        all_transfers[addr] = await fetch_all_trc20_transfers(addr)

    pair_records = []

    for i in range(len(addrs)):
        for j in range(i + 1, len(addrs)):
            a1, a2 = addrs[i], addrs[j]
            txs1 = all_transfers[a1]
            txs2 = all_transfers[a2]

            mutual = []

            for tr in txs1:
                if tr.get("from_address", "").lower() == a2.lower() or tr.get("to_address", "").lower() == a2.lower():
                    mutual.append(tr)

            for tr in txs2:
                if tr.get("from_address", "").lower() == a1.lower() or tr.get("to_address", "").lower() == a1.lower():
                    if tr not in mutual:
                        mutual.append(tr)

            for tr in mutual:
                pair_records.append((f"{a1} <-> {a2}", tr))

    if not pair_records:
        await update.message.reply_text("❌ 未找到相互之间的 TRC20 转账记录。")
        context.user_data.clear()
        return

    context.user_data["tx_query_records"] = pair_records
    context.user_data["tx_query_page"] = 0
    context.user_data["awaiting_tx_addresses"] = False

    await send_tx_page(update, context, 0)

async def send_tx_page(update, context, page):
    records = context.user_data.get("tx_query_records", [])
    total_pages = (len(records) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    context.user_data["tx_query_page"] = page

    page_records = records[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    lines = []
    for _, tr in page_records:
        ts = tr.get("block_ts", 0) // 1000
        time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        amount_raw = int(tr.get("quant", 0))
        decimals = int(tr.get("tokenInfo", {}).get("tokenDecimal", 6))
        amount = amount_raw / (10 ** decimals)
        from_addr = tr.get("from_address", "未知")
        to_addr = tr.get("to_address", "未知")
        symbol = tr.get("tokenInfo", {}).get("tokenAbbr", "TRC20")

        from_link = f'<a href="https://tronscan.org/#/address/{from_addr}">{from_addr}</a>'
        to_link = f'<a href="https://tronscan.org/#/address/{to_addr}">{to_addr}</a>'

        lines.append(
            f"{time_str}\n"
            f"  {amount:.6f} {symbol}\n"
            f"  From: {from_link} → To: {to_link}\n"
            "----------------------------------"
        )

    text = "\n".join(lines)
    text += f"\n\n第 {page+1} 页 / 共 {total_pages} 页"

    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("⬅ 上一页", callback_data="tx_page_" + str(page - 1)))
    if page + 1 < total_pages:
        keyboard.append(InlineKeyboardButton("下一页 ➡", callback_data="tx_page_" + str(page + 1)))

    reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def transaction_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("tx_page_"):
        page = int(data.split("_")[-1])
        await send_tx_page(update, context, page)
