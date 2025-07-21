# Telegram Wallet Checker Bot

## 功能
- 查询 TRON 钱包地址信息：余额、USDT资产、交易次数、能量与带宽
- 支持交易记录分页展示
- 自动识别并解析地址
- Telegram Bot 菜单界面

## 环境配置

### 安装依赖
```bash
pip install python-telegram-bot aiohttp
```

### 设置环境变量
设置你的 Telegram Bot Token：

Linux/macOS:
```bash
export BOT_TOKEN=your_bot_token_here
```

Windows:
```cmd
set BOT_TOKEN=your_bot_token_here
```

### 运行
```bash
python main.py
```

## 文件结构
```
telegram_wallet_checker_bot/
├── main.py
├── handlers/
│   └── address.py
├── utils/
│   └── tronscan.py
└── README.md
```
