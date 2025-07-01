import requests
import pandas as pd
import time
import ta
import pytz
import os
from datetime import datetime
from dotenv import load_dotenv

# Load secrets
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

interval = "15m"
limit = 100
pairs = ["ETHUSDT", "BTCUSDT", "SOLUSDT"]

# Create logs folder
if not os.path.exists("logs"):
    os.makedirs("logs")

# Telegram Alert
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram error:", e)

# Get Price Data
def get_klines(symbol, interval, limit):
    url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()

    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume", "close_time", "ignore"
    ])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit='ms')
    pk_tz = pytz.timezone("Asia/Karachi")
    df["timestamp"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert(pk_tz)
    return df

# Add Indicators
def add_indicators(df):
    df["EMA20"] = ta.trend.ema_indicator(df["close"], window=20)
    df["EMA50"] = ta.trend.ema_indicator(df["close"], window=50)
    df["RSI"] = ta.momentum.rsi(df["close"], window=14)
    macd = ta.trend.MACD(df["close"])
    df["MACD"] = macd.macd_diff()
    bb = ta.volatility.BollingerBands(df["close"])
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["VWAP"] = ta.volume.volume_weighted_average_price(df["high"], df["low"], df["close"], df["volume"])
    df["OBV"] = ta.volume.on_balance_volume(df["close"], df["volume"])
    return df

# Flexible Signal Logic: 3 out of 5 indicators
def generate_signal(df):
    last = df.iloc[-1]

    buy_conditions = [
        last["EMA20"] > last["EMA50"],
        last["RSI"] > 50,
        last["MACD"] > 0,
        last["close"] > last["VWAP"],
        last["close"] > last["BB_upper"]
    ]

    sell_conditions = [
        last["EMA20"] < last["EMA50"],
        last["RSI"] < 50,
        last["MACD"] < 0,
        last["close"] < last["VWAP"],
        last["close"] < last["BB_lower"]
    ]

    if sum(buy_conditions) >= 3:
        return "BUY"
    elif sum(sell_conditions) >= 3:
        return "SELL"
    else:
        return "HOLD"

# Save to CSV
def log_signal(symbol, timestamp, signal, entry, sl, tp):
    log_file = f"logs/{symbol}.csv"
    df = pd.DataFrame([{
        "time": timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        "signal": signal,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp": round(tp, 2)
    }])
    df.to_csv(log_file, mode='a', index=False, header=not os.path.exists(log_file))

# Bot Runner
def run_bot():
    print("📥 Fetching price data...\n")
    for symbol in pairs:
        try:
            df = get_klines(symbol, interval, limit)
            df = add_indicators(df)
            signal = generate_signal(df)
            last = df.iloc[-1]

            print(f"📌 {symbol}")
            print(f"✅ Signal: {signal}")
            print(f"🔍 Price: {last['close']:.2f}")
            print(f"📉 EMA20: {last['EMA20']:.2f} | RSI: {last['RSI']:.2f}")
            print(f"🕒 Time: {last['timestamp'].strftime('%d %b %Y, %I:%M %p')}\n")

            if signal in ["BUY", "SELL"]:
                entry = last["close"]
                sl = entry * 0.98 if signal == "BUY" else entry * 1.02
                tp = entry * 1.03 if signal == "BUY" else entry * 0.97

                send_telegram_message(
                    f"📢 {symbol} - {signal} SIGNAL!\n"
                    f"📍 Entry: {entry:.2f}\n"
                    f"⛔ SL: {sl:.2f}\n"
                    f"🎯 TP: {tp:.2f}\n"
                    f"🕒 Time: {last['timestamp'].strftime('%d %b %Y, %I:%M %p')}"
                )

                log_signal(symbol, last["timestamp"], signal, entry, sl, tp)

        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")

# Auto-loop
if __name__ == "__main__":
    send_telegram_message("✅ Multi-Pair Bot with Flexible Logic & Logging started.")
    while True:
        run_bot()
        print("⏳ Waiting for 60 seconds...\n")
        time.sleep(60)
