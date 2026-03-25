import requests
import pandas as pd
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "DAN_TOKEN_VAO_DAY"

SYMBOLS = ["BTC_USDT","ETH_USDT","XRP_USDT","SUI_USDT","OP_USDT","PEPE_USDT"]

# =========================
# LẤY DỮ LIỆU
# =========================
def get_data(symbol):
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval=Min1&limit=50"
    data = requests.get(url).json()["data"]

    df = pd.DataFrame(data)
    df["close"] = df["close"].astype(float)
    df["vol"] = df["vol"].astype(float)

    return df

# =========================
# PHÂN TÍCH CHUẨN
# =========================
def analyze(df):
    df["ema9"] = df["close"].ewm(span=9).mean()
    df["ema21"] = df["close"].ewm(span=21).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = latest["close"]

    # xu hướng
    if latest["ema9"] > latest["ema21"]:
        trend = "📈 TĂNG"
    else:
        trend = "📉 GIẢM"

    # dòng tiền
    if latest["vol"] > prev["vol"]:
        if latest["close"] > prev["close"]:
            flow = "💰 TIỀN VÀO"
        else:
            flow = "🚨 TIỀN RA"
    else:
        flow = "⚪ YẾU"

    return price, trend, flow

# =========================
# TẠO MESSAGE
# =========================
def build_message():
    msg = "📊 BOT THEO DÕI THỊ TRƯỜNG\n\n"

    for symbol in SYMBOLS:
        try:
            df = get_data(symbol)
            price, trend, flow = analyze(df)

            msg += f"{symbol}\n"
            msg += f"Giá: {price}\n"
            msg += f"{trend} | {flow}\n\n"

        except:
            msg += f"{symbol}: lỗi dữ liệu\n\n"

    return msg

# =========================
# TELEGRAM
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.application.chat_id = update.effective_chat.id
    await update.message.reply_text("✅ Bot đang chạy... sẽ gửi tín hiệu mỗi 60s")

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
            print("Lỗi:", e)

        await asyncio.sleep(60)

# =========================
# MAIN
# =========================
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    asyncio.create_task(loop(app))

    print("Bot đang chạy...")
    await app.run_polling()

asyncio.run(main())
