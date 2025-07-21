import httpx
import logging
from telegram import Update
from telegram.ext import ContextTypes

logging.basicConfig(level=logging.INFO)

# 支持的平台及中英双语名称和图标
PLATFORM_NAMES = {
    "coingecko": "📊 CoinGecko（行情聚合）",
    "okx": "📈 OKX（欧易交易所）",
    "binance": "🏦 Binance（币安交易所）",
}

# 支持的目标币种（简写）
SUPPORTED_CURRENCIES = {
    "AUD", "BRL", "BUSD", "CAD", "CHF", "CNY", "EUR", "GBP",
    "HKD", "INR", "JPY", "KRW", "MXN", "PHP", "RUB", "SGD",
    "THB", "TRY", "USD", "USDT", "VND", "ZAR"
}

async def handle_exchange_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_exchange_currency"] = True
    prompt = (
        "请输入目标国家或货币简写，例如：\n"
        "中国 或 CNY, 美国 或 USD, 欧元区 或 EUR, 日本 或 JPY\n"
        "支持以下币种：\n"
        + ", ".join(sorted(SUPPORTED_CURRENCIES))
    )
    await update.message.reply_text(prompt)

async def handle_exchange_rate_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if text not in SUPPORTED_CURRENCIES:
        await update.message.reply_text(
            f"❌ 不支持的币种或格式错误，请输入支持的币种简写，例如 CNY, USD, EUR 等。\n"
            f"支持币种列表：{', '.join(sorted(SUPPORTED_CURRENCIES))}"
        )
        return

    # 清除等待状态
    context.user_data["awaiting_exchange_currency"] = False

    results = await fetch_all_rates(text)

    msg = f"💹 USDT 实时汇率 - 目标币种：{text}\n\n"
    for platform, rate in results.items():
        platform_name = PLATFORM_NAMES.get(platform, platform)
        if rate is not None:
            msg += f"{platform_name}: 1 USDT ≈ {rate} {text}\n"
        else:
            msg += f"{platform_name}: 获取失败\n"

    await update.message.reply_text(msg)

async def fetch_all_rates(target_currency: str) -> dict:
    results = {
        "coingecko": await fetch_coingecko_rate(target_currency),
        "okx": await fetch_okx_rate(target_currency),
        "binance": await fetch_binance_rate(target_currency),
    }
    return results

async def fetch_coingecko_rate(target_currency: str) -> float | None:
    url = (
        f"https://api.coingecko.com/api/v3/simple/price?"
        f"ids=tether&vs_currencies={target_currency.lower()}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            rate = data.get("tether", {}).get(target_currency.lower())
            if rate is not None:
                return float(rate)
    except Exception as e:
        logging.error(f"CoinGecko API error: {e}")
    return None

async def fetch_okx_rate(target_currency: str) -> float | None:
    symbol = f"usdt{target_currency.lower()}"
    url = "https://www.okx.com/api/v5/market/ticker?instId=" + symbol
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == "0":
                price_str = data.get("data", [{}])[0].get("last")
                if price_str:
                    return float(price_str)
    except Exception as e:
        logging.error(f"OKX API error: {e}")
    return None

async def fetch_binance_rate(target_currency: str) -> float | None:
    symbol = f"usdt{target_currency.lower()}"
    url = "https://api.binance.com/api/v3/ticker/price?symbol=" + symbol.upper()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            price_str = data.get("price")
            if price_str:
                return float(price_str)
    except Exception as e:
        logging.error(f"Binance API error: {e}")
    return None
