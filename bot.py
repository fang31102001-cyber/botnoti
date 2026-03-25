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

CHAT_IDS = [5335165612, 3333]

last_signals = {}

# =========================
# WEB SERVER
# =========================
app_web = Flask('')

@app_web.route('/')
def home():
    return "OK"

def run_web():
    app_web.run(host='0.0.0.0', port=10000)

def keep_alive():
    Thread(target=run_web).start()

# =========================
# DATA
# =========================
def get_data(symbol):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval=Min1&limit=150"
        res = requests.get(url, timeout=10).json()
        df = pd.DataFrame(res["data"])

        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["vol"] = df["vol"].astype(float)

        return df
    except:
        return None

# =========================
# RSI
# =========================
def calculate_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# =========================
# ATR
# =========================
def calculate_atr(df):
    df["H-L"] = df["high"] - df["low"]
    df["H-C"] = abs(df["high"] - df["close"].shift())
    df["L-C"] = abs(df["low"] - df["close"].shift())

    df["TR"] = df[["H-L","H-C","L-C"]].max(axis=1)
    return df["TR"].rolling(14).mean().iloc[-1]

# =========================
# ANALYZE PRO
# =========================
def analyze(df):
    df["ema9"] = df["close"].ewm(span=9).mean()
    df["ema21"] = df["close"].ewm(span=21).mean()
    df["rsi"] = calculate_rsi(df)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = latest["close"]
    atr = calculate_atr(df)

    # ===== TREND =====
    uptrend = latest["ema9"] > latest["ema21"]
    downtrend = latest["ema9"] < latest["ema21"]

    # ===== VOLUME SPIKE =====
    avg_vol = df["vol"].rolling(20).mean().iloc[-1]
    volume_spike = latest["vol"] > avg_vol * 1.5

    # ===== MOMENTUM =====
    rsi = latest["rsi"]

    strong_buy = uptrend and volume_spike and rsi > 55
    strong_sell = downtrend and volume_spike and rsi < 45

    if strong_buy:
        signal = "🚀 STRONG BUY"
        target = price + atr * 1.5
    elif strong_sell:
        signal = "🔻 STRONG SELL"
        target = price - atr * 1.5
    else:
        signal = None
        target = None

    return price, target, signal, rsi

# =========================
# MESSAGE
# =========================
def build_message():
    global last_signals
    msg = ""

    for symbol in SYMBOLS:
        df = get_data(symbol)
        if df is None:
            continue

        price, target, signal, rsi = analyze(df)

        if signal is None:
            continue

        prev_signal = last_signals.get(symbol)

        if prev_signal != signal:
            last_signals[symbol] = signal

            link = f"https://futures.mexc.com/exchange/{symbol.replace('_','')}"

            msg += f"{symbol}\n"
            msg += f"Giá: {round(price,6)}\n"
            msg += f"RSI: {round(rsi,2)}\n"
            msg += f"Target: {round(target,6)}\n"
            msg += f"{signal}\n"
            msg += f"Chart: {link}\n\n"

    return msg

# =========================
# TELEGRAM
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 BOT PRO ĐANG CHẠY")
# =========================
# LOOP
# =========================
async def loop(app):
    while True:
        try:
            msg = build_message()

            if msg:
                for chat_id in CHAT_IDS:
                    try:
                        await app.bot.send_message(chat_id=chat_id, text=msg)
                    except:
                        pass
        except Exception as e:
            print(e)

        await asyncio.sleep(60)

# =========================
# MAIN
# =========================
async def main():
    keep_alive()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    asyncio.create_task(loop(app))

    print("RUNNING PRO BOT...")
    await app.run_polling()

asyncio.run(main())
