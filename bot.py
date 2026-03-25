import requests
import pandas as pd
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from flask import Flask
from threading import Thread

TOKEN = os.getenv("TOKEN")

SYMBOLS = ["BTC_USDT","ETH_USDT","XRP_USDT","SUI_USDT","OP_USDT","PEPE_USDT"]

# =========================
# WEB SERVER (GIỮ BOT KHÔNG NGỦ)
# =========================
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is running"

def run_web():
    app_web.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# =========================
# LẤY DATA MEXC
# =========================
def get_data(symbol):
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval=Min1&limit=50"
    data = requests.get(url).json()["data"]

    df = pd.DataFrame(data)
    df["close"] = df["close"].astype(float)
    df["vol"] = df["vol"].astype(float)

    return df

# =========================
# PHÂN TÍCH
# =========================
def analyze(df):
    df["ema9"] = df["close"].ewm(span=9).mean()
    df["ema21"] = df["close"].ewm(span=21).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = latest["close"]

    if latest["ema9"] > latest["ema21"]:
        trend = "📈 TĂNG"
    else:
        trend = "📉 GIẢM"

    if latest["vol"] > prev["vol"]:
        if latest["close"] > prev["close"]:
            flow = "💰 TIỀN VÀO"
        else:
            flow = "🚨 TIỀN RA"
    else:
        flow = "⚪ YẾU"

    return price, trend, flow

# =========================
# MESSAGE
# =========================
def build_message():
    msg = "📊 BOT MARKET\n\n"

    for symbol in SYMBOLS:
        try:
            df = get_data(symbol)
            price, trend, flow = analyze(df)

            msg += f"{symbol}\n"
            msg += f"Giá: {price}\n"
            msg += f"{trend} | {flow}\n\n"

        except:
            msg += f"{symbol}: lỗi\n\n"

    return msg

# =========================
# TELEGRAM
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.application.chat_id = update.effective_chat.id
    await update.message.reply_text("✅ Bot đang chạy 24/7")

# =========================
# LOOP
# =========================
async def loop(app):
    while True:
        try:
            if hasattr(app, "chat_id"):
                msg = build_message()
                await app.bot.send_message(chat_id=app.chat_id, text=msg)
        except Exception as e:
            print("Error:", e)

        await asyncio.sleep(60)

# =========================
# MAIN
# =========================
async def main():
    keep_alive()  # chạy web giữ uptime

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    asyncio.create_task(loop(app))

    print("Bot running...")
    await app.run_polling()

asyncio.run(main())
