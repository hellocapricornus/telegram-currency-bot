import re
from telegram import Update
from telegram.ext import ContextTypes

async def handle_price_compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # 匹配格式：5 100/6 110（支持小数）
    pattern = r"^\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$"
    match = re.match(pattern, text)

    if not match:
        await update.message.reply_text(
            "输入格式错误，请按如下格式输入：\n"
            "<费率1> <汇率1>/<费率2> <汇率2>\n"
            "示例：5 100/6 110\n支持整数和小数"
        )
        return

    try:
        # 解析数值
        old_fee = float(match.group(1))
        old_rate = float(match.group(2))
        new_fee = float(match.group(3))
        new_rate = float(match.group(4))

        # 计算百分比变化
        fee_change_pct = (new_fee - old_fee) / 100
        rate_change_pct = (new_rate - old_rate) / new_rate
        total_change_pct = fee_change_pct + rate_change_pct

        # 格式化为百分比，保留1位小数
        fee_pct_str = f"{fee_change_pct * 100:.1f}%"
        rate_pct_str = f"{rate_change_pct * 100:.1f}%"
        total_pct_str = f"{total_change_pct * 100:.1f}%"

        # 盈利/亏损判定
        symbol = "🟢" if total_change_pct > 0 else "🔴"
        label = "赚" if total_change_pct > 0 else "亏"

        # 输出结果
        result = (
            f"{symbol} {label}{total_pct_str}\n"
            f"费率变化：{old_fee:.1f} → {new_fee:.1f}（{fee_pct_str}）\n"
            f"汇率变化：{old_rate:.1f} → {new_rate:.1f}（{rate_pct_str}）"
        )

        await update.message.reply_text(result)

    except Exception as e:
        await update.message.reply_text(f"⚠️ 处理失败：{str(e)}")
