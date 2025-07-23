import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

def is_tron_address(addr):
    return addr.startswith("T") and len(addr) == 34

def parse_addresses(text):
    parts = [p.strip() for p in text.replace(",", " ").split()]
    addrs = [a for a in parts if is_tron_address(a)]
    return addrs[:2]  # 互转分析只取前两个地址

async def fetch_json(session, url):
    async with session.get(url) as resp:
        return await resp.json()

async def fetch_all_trc20_transfers(addr, max_pages=5):
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

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "请输入两个 TRON 钱包地址，用空格或逗号分隔，我帮你分析是否存在第三方地址与这两个地址都有过 TRC20 转账。"
    )
    context.user_data.clear()
    context.user_data["awaiting_contact_addresses"] = True

async def handle_contact_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_contact_addresses"):
        return

    text = update.message.text.strip()
    addrs = parse_addresses(text)

    if len(addrs) != 2:
        await update.message.reply_text("❌ 地址格式错误，请确保输入两个有效 TRON 地址。")
        return

    addr1, addr2 = addrs

    await update.message.reply_text("🔍 正在分析判断，请稍候...")

    # 分别拉取两个地址的转账记录
    txs1 = await fetch_all_trc20_transfers(addr1)
    txs2 = await fetch_all_trc20_transfers(addr2)

    # 统计每个地址与 addr1 的交互次数（from/to中除去 addr1）
    counter1 = {}
    for tx in txs1:
        frm = tx.get("from_address", "")
        to = tx.get("to_address", "")
        other = None
        if frm == addr1:
            other = to
        elif to == addr1:
            other = frm
        if other:
            counter1[other] = counter1.get(other, 0) + 1

    # 同理统计 addr2
    counter2 = {}
    for tx in txs2:
        frm = tx.get("from_address", "")
        to = tx.get("to_address", "")
        other = None
        if frm == addr2:
            other = to
        elif to == addr2:
            other = frm
        if other:
            counter2[other] = counter2.get(other, 0) + 1

    # 找共同的第三方地址
    common_addresses = set(counter1.keys()) & set(counter2.keys())

    if not common_addresses:
        await update.message.reply_text("❌ 未发现与这两个地址都有交互的第三方地址。")
        context.user_data.clear()
        return

    lines = ["🔎 发现共同地址及与两地址的转账次数："]
    for ca in common_addresses:
        # 将地址转换为可点击链接，保持原始大小写
        ca_link = f"<a href='https://tronscan.org/#/address/{ca}'>[{ca}]</a>"
        lines.append(
            f"{ca_link}\n"
            f"  与地址一交互次数: {counter1[ca]}\n"
            f"  与地址二交互次数: {counter2[ca]}\n"
            "--------------------------"
        )

    await update.message.reply_text("\n".join(lines), parse_mode='HTML')
    context.user_data.clear()
