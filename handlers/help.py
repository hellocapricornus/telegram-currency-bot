from telegram import Update
from telegram.ext import ContextTypes

HELP_TEXT = """📘 <b>记账机器人命令说明</b>

🧩 <b>基础设置</b>
设置汇率xxx.xx
设置费率xx%

👤 <b>操作人员管理</b>
添加操作人 用户名
删除操作人 用户名

🧾 <b>记账流程</b>
开始记账
+xxx
+xxx 备注
+xxx 汇率
+xxx 汇率 备注
+xxx 汇率 费率
+xxx 汇率 费率 备注
入款修正：-xxx
入款修正：-xxx 汇率
入款修正：-xxx 汇率 费率
下发-xxx 或 下发xxxU
下发xxxU 备注
下发修正：下发-xxx 或 下发-xxxU
下发修正：下发-xxxU 备注
保存账单
结束记账

📊 <b>账单查看</b>
查询账单

📌 <b>说明</b>
- 汇率/费率设置在开始记账后将锁定
- 费率支持负数，命令不区分大小写
- 入款、下发、折算USDT均以北京时间记录
- 所有计算使用：金额 × (1 - 费率) / 汇率
- 支持分页查询历史账单、按月份筛选
- 仅群管理员/操作员可使用以上命令

如需帮助，请联系管理员。"""

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("请在群组中使用本机器人", quote=True)
        return

    await update.message.reply_html(HELP_TEXT)
