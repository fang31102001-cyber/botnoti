import requests
import pandas as pd
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime, timedelta

from flask import Flask
from threading import Thread

TOKEN = os.getenv("TOKEN")

SYMBOLS = ["BTC_USDT","ETH_USDT","XRP_USDT","SUI_USDT","OP_USDT","PEPE_USDT"]

CHAT_IDS = [5335165612, 3333]
last_messages = {}
CURRENT_SYMBOL = "BTC_USDT"
user_symbols = {}
last_oi = {}
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
        
def get_open_interest(symbol):
    try:
        symbol_binance = symbol.replace("_USDT", "USDT")

        url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol_binance}"
        data = requests.get(url).json()

        return float(data["openInterest"])
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
def analyze_timeframe(symbol, interval):
    try:
        # ===== BINANCE DATA =====

        # đổi symbol sang dạng Binance
        symbol_binance = symbol.replace("_USDT", "USDT")

        # map timeframe
        interval_map = {
            "Min15": "15m",
            "Min60": "1h",
            "Hour4": "4h",
            "Day1": "1d"
        }

        interval_binance = interval_map.get(interval, "15m")

        url = f"https://api.binance.com/api/v3/klines?symbol={symbol_binance}&interval={interval_binance}&limit=100"
        data = requests.get(url).json()

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "ct","qav","trades","tbv","tqv","ignore"
        ])

        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["vol"] = df["volume"].astype(float)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = latest["close"]
        oi = get_open_interest(symbol)
        prev_oi = last_oi.get(symbol)
        last_oi[symbol] = oi

        oi_signal = ""

        if oi and prev_oi:

            oi_change = (oi - prev_oi) / prev_oi

            if oi_change > 0.02 and price > prev["close"]:
                oi_signal = "Dòng tiền mới đang vào mạnh (long chiếm ưu thế)"

            elif oi_change > 0.02 and price < prev["close"]:
                oi_signal = "Dòng tiền vào nhưng phe bán đang kiểm soát (short mạnh)"

            elif oi_change < -0.02 and price > prev["close"]:
                oi_signal = "Short đang bị đóng → khả năng xảy ra short squeeze"

            elif oi_change < -0.02 and price < prev["close"]:
                oi_signal = "Dòng tiền rút ra → thị trường suy yếu"

        # RSI
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        rs = gain.rolling(14).mean() / loss.rolling(14).mean()
        rsi = 100 - (100 / (1 + rs))
        rsi_value = rsi.iloc[-1]

        # volume
        avg_vol = df["vol"].rolling(20).mean().iloc[-1]
        volume_spike = latest["vol"] > avg_vol * 2

        # support/resistance
        support = df["low"].rolling(20).min().iloc[-1]
        resistance = df["high"].rolling(20).max().iloc[-1]

        # ATR
        df["H-L"] = df["high"] - df["low"]
        df["H-C"] = abs(df["high"] - df["close"].shift())
        df["L-C"] = abs(df["low"] - df["close"].shift())
        df["TR"] = df[["H-L","H-C","L-C"]].max(axis=1)
        atr = df["TR"].rolling(14).mean().iloc[-1]

        # ===== LOGIC PRO =====
        near_support = abs(price - support) / price < 0.01
        near_resistance = abs(price - resistance) / price < 0.01

        money_in = volume_spike and price > prev["close"]
        money_out = volume_spike and price < prev["close"]

        # ===== SIGNAL =====
        if money_in and rsi_value > 55:
            signal = "💰 DÒNG TIỀN VÀO MẠNH"
            target = price + atr * 1.5

        elif money_out and rsi_value < 45:
            signal = "🚨 DÒNG TIỀN THOÁT RA"
            target = price - atr * 1.5

        elif near_support:
            signal = "🟢 GẦN VÙNG HỖ TRỢ (có thể bật)"
            target = resistance

        elif near_resistance:
            signal = "🔴 GẦN KHÁNG CỰ (dễ bị đẩy xuống)"
            target = support

        else:
            return None

        return price, rsi_value, support, resistance, signal, target, oi_signal

    except:
        return None

# =========================
# MESSAGE
# =========================
def build_message_for_user(chat_id):
    vn_time = datetime.utcnow() + timedelta(hours=7)
    symbols = user_symbols.get(chat_id, SYMBOLS)

    final_msg = ""

    for symbol in symbols:

        data_15m = analyze_timeframe(symbol, "Min15")
        data_1h = analyze_timeframe(symbol, "Min60")
        data_4h = analyze_timeframe(symbol, "Hour4")

        if not data_15m or not data_1h or not data_4h:
            continue

        price, rsi15, sup15, res15, sig15, _, oi15 = data_15m
        _, rsi1h, sup1h, res1h, sig1h, _, _ = data_1h
        _, rsi4h, sup4h, res4h, sig4h, _, _ = data_4h

        msg = f"📊 NHẬN ĐỊNH THỊ TRƯỜNG {symbol.replace('_USDT','')}\n\n"

        # ===== GIÁ =====
        msg += f"Hiện tại giá đang ở vùng {round(price,6)}.\n"

        # ===== 15M =====
        if "TIỀN VÀO" in sig15:
            msg += f"Khung 15m ghi nhận volume tăng mạnh kèm giá tăng, RSI {round(rsi15,1)} → lực mua đang chiếm ưu thế.\n\n"
        elif "THOÁT RA" in sig15:
            msg += f"Khung 15m xuất hiện volume lớn kèm giá giảm, RSI {round(rsi15,1)} → lực bán đang chiếm ưu thế.\n\n"
        else:
            msg += f"Khung 15m thị trường đang đi ngang, RSI ở mức {round(rsi15,1)}.\n\n"
        if oi15 != "":
            msg += f"{oi15}.\n\n"

        # ===== 1H =====
        msg += f"Ở khung 1H, giá đang tiến gần vùng kháng cự {round(res1h,6)} → có thể xuất hiện áp lực chốt lời.\n\n"

        # ===== 4H =====
        msg += f"Khung 4H vẫn duy trì xu hướng chính, vùng hỗ trợ gần nhất tại {round(sup4h,6)}.\n"

        # ===== KỊCH BẢN =====
        msg += "👉 Kịch bản:\n\n"
        
        msg += "👉 Nhận định:\n\n"

        if "TIỀN VÀO" in sig15 and rsi15 > 55:
            msg += "Thị trường đang có dấu hiệu tích cực khi lực mua chiếm ưu thế trong ngắn hạn.\n\n"

        elif "THOÁT RA" in sig15 and rsi15 < 45:
            msg += "Áp lực bán đang gia tăng, thị trường có thể tiếp tục suy yếu trong ngắn hạn.\n\n"

        else:
            msg += "Thị trường đang trong trạng thái giằng co, chưa có xu hướng rõ ràng.\n\n"

        # breakout kháng cự
        msg += f"- Nếu giá đóng nến 15m trên {round(res1h,6)} → xác nhận breakout, mục tiêu tiếp theo {round(res1h*1.01,6)}\n"

        # breakdown hỗ trợ
        msg += f"- Nếu giá đóng nến 1H dưới {round(sup4h,6)} → mất hỗ trợ, giá có thể giảm về {round(sup4h*0.99,6)}\n\n"

        final_msg += msg + "\n----------------------\n\n"

    return final_msg
# =========================
# TELEGRAM
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in CHAT_IDS:
        CHAT_IDS.append(chat_id)

    await update.message.reply_text("🔥 Bot đang chạy")

async def set_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        coins = [c.upper() + "_USDT" for c in context.args]

        user_symbols[chat_id] = coins

        await update.message.reply_text(f"✅ Bạn đang theo dõi: {', '.join(coins)}")

    except:
        await update.message.reply_text("❌ Ví dụ: /set BTC ETH PEPE")
# =========================
# LOOP
# =========================
async def loop(app):
    while True:
        try:
            # 🕒 giờ Việt Nam
            vn_time = datetime.utcnow() + timedelta(hours=7)

            # ⛔ ngoài giờ thì bỏ qua
            if vn_time.hour < 7 or vn_time.hour > 23:
                await asyncio.sleep(60)
                continue

            for chat_id in CHAT_IDS:
                msg = build_message_for_user(chat_id)

                # ❌ nếu không có tín hiệu thì bỏ
                if msg.strip() == "":
                    continue

                try:
                    # ❌ nếu giống tin cũ → không gửi
                    if last_messages.get(chat_id) != msg:
                        await app.bot.send_message(chat_id=chat_id, text=msg)
                        last_messages[chat_id] = msg
                except:
                    pass

        except Exception as e:
            print("Lỗi:", e)

        await asyncio.sleep(60)

# =========================
# MAIN
# =========================
async def main():
    keep_alive()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set", set_coin))

    asyncio.create_task(loop(app))

    print("RUNNING PRO BOT...")
    await app.run_polling()

asyncio.run(main())
