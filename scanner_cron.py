#!/usr/bin/env python3
"""
Crypto Signal Bot - GitHub Actions 定时扫描版 (Telegram 官方直连)
每 15 分钟由 GitHub 云端自动唤醒一次，扫描 11 大核心资产的 15m 与 4H 信号，
一旦发现底背离CHoCH或EMA回踩，立即推送到你的 Telegram，扫描完毕后自动关机，100% 零费用！
"""

import os
import sys
import time
import json
import logging
from typing import List, Dict, Optional
import urllib.request
import urllib.parse
import urllib.error

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ==========================================
# Telegram 专属配置 (已为你自动配置完毕！)
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8708038882:AAFrnq6jzFS1OJDg35t32zO6MKLrIIrV7Hc").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7536260641").strip()

CONFIG = {
    "SYMBOLS": ["BTC", "ETH", "SOL", "XRP", "DOGE", "SUI", "ADA", "LINK", "VET", "ASTER", "LTC"],
    "TIMEFRAMES": ["4H", "15m"]
}


def fetch_klines(coin: str, interval: str = "15m", limit: int = 50) -> Optional[List[Dict]]:
    if coin == "VET":
        url = f"https://api.binance.us/api/v3/klines?symbol=VETUSDT&interval={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                raw_data = json.loads(response.read().decode())
                return [{
                    "time": int(x[0]), "open": float(x[1]), "high": float(x[2]),
                    "low": float(x[3]), "close": float(x[4]), "volume": float(x[5])
                } for x in raw_data]
        except Exception as e:
            logging.error(f"获取 VET 行情失败: {e}")
            return None
    else:
        inst_id = f"{coin}-USDT-SWAP"
        url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode())
                if res.get("code") != "0" or not res.get("data"):
                    return None
                raw_data = list(reversed(res["data"]))
                return [{
                    "time": int(x[0]), "open": float(x[1]), "high": float(x[2]),
                    "low": float(x[3]), "close": float(x[4]), "volume": float(x[5])
                } for x in raw_data]
        except Exception as e:
            logging.error(f"获取 {coin} 行情失败: {e}")
            return None


def calculate_ema(prices: List[float], period: int) -> List[float]:
    ema = []
    multiplier = 2.0 / (period + 1)
    for i, price in enumerate(prices):
        if i == 0:
            ema.append(price)
        else:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    if len(prices) < period + 1:
        return [50.0] * len(prices)
    rsi = [50.0] * len(prices)
    gains = [max(prices[i] - prices[i-1], 0.0) for i in range(1, len(prices))]
    losses = [max(-(prices[i] - prices[i-1]), 0.0) for i in range(1, len(prices))]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    for i in range(period + 1, len(prices)):
        avg_gain = (avg_gain * (period - 1) + gains[i-1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i-1]) / period
        rsi[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return rsi


def check_strategy_1_divergence_choch(klines: List[Dict], rsis: List[float], timeframe: str) -> Optional[Dict]:
    if len(klines) < 30:
        return None
    window = klines[-25:-1]
    window_rsi = rsis[-25:-1]
    latest = klines[-1]

    low_indices = [i for i in range(2, len(window) - 2)
                   if window[i]['low'] < window[i-1]['low'] and window[i]['low'] < window[i-2]['low']
                   and window[i]['low'] < window[i+1]['low'] and window[i]['low'] < window[i+2]['low']]

    if len(low_indices) < 2:
        return None

    idx1, idx2 = low_indices[-2], low_indices[-1]
    price_low1, price_low2 = window[idx1]['low'], window[idx2]['low']
    rsi_low1, rsi_low2 = window_rsi[idx1], window_rsi[idx2]

    if not ((price_low2 < price_low1) and (rsi_low2 > rsi_low1 + 2.0) and (rsi_low2 < 48)):
        return None

    intermediate_high = max(window[k]['high'] for k in range(idx1, idx2 + 1))

    if latest['close'] > intermediate_high and window[-1]['close'] <= intermediate_high:
        stop_loss = price_low2 * 0.995 if timeframe == "4H" else price_low2 * 0.997
        risk = latest['close'] - stop_loss
        tp1 = latest['close'] + risk * 2.0
        tp2 = latest['close'] + risk * 3.5

        return {
            "scope_tag": "🔥 【战略级·超级大底反转】" if timeframe == "4H" else "⚡ 【战术级·日内波段反转】",
            "strategy": "RSI 底背离 + 结构破坏 (CHoCH)",
            "timeframe": timeframe,
            "action": "做多 (BUY / LONG)",
            "holding_desc": "几天至数周（吃大级别反转）" if timeframe == "4H" else "数小时至1天（日内高盈亏比）",
            "entry": latest['close'],
            "stop_loss": round(stop_loss, 4),
            "tp1": round(tp1, 4),
            "tp2": round(tp2, 4),
            "reason": f"{timeframe}级别价格破新低(${price_low2})但RSI底背离，且最新强势踩破前哨兵高点(${intermediate_high})！"
        }
    return None


def check_strategy_2_ema_pullback(klines: List[Dict], ema20: List[float], ema50: List[float], timeframe: str) -> Optional[Dict]:
    if len(klines) < 15:
        return None
    candle = klines[-2]
    e20 = ema20[-2]
    e50 = ema50[-2]

    if not (e20 > e50 and ema20[-4] > ema50[-4]):
        return None

    high, low, open_p, close = candle['high'], candle['low'], candle['open'], candle['close']
    candle_range = high - low
    lower_wick = min(open_p, close) - low

    if candle_range <= 0:
        return None

    if (lower_wick / candle_range >= 0.45) and (close >= open_p) and (low <= e20 * 1.002) and (close >= e20):
        stop_loss = low * 0.996 if timeframe == "4H" else low * 0.998
        risk = close - stop_loss
        tp1 = close + risk * 1.8
        tp2 = close + risk * 3.0

        return {
            "scope_tag": "🚀 【战略级·主升浪波段跟车】" if timeframe == "4H" else "🚗 【战术级·日内顺风车跟车】",
            "strategy": "EMA 20/50 顺势回踩 + 金针探底 (Pinbar)",
            "timeframe": timeframe,
            "action": "顺势做多 (BUY / LONG)",
            "holding_desc": "数天（顺大单边趋势）" if timeframe == "4H" else "数小时（吃日内拉升）",
            "entry": close,
            "stop_loss": round(stop_loss, 4),
            "tp1": round(tp1, 4),
            "tp2": round(tp2, 4),
            "reason": f"{timeframe}级别处于强多头排列，回踩 EMA20(${round(e20, 4)}) 留出长下影线拒跌踩稳！"
        }
    return None


def send_alert(text_msg: str):
    logging.info(f"\n[发送通知]:\n{text_msg}\n")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text_msg}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as res:
                logging.info("Telegram 手机推送成功！")
        except Exception as e:
            logging.error(f"Telegram 发送失败: {e}")


def main():
    if "--test-alert" in sys.argv:
        test_msg = "🟢 【GitHub Actions 联调成功】\n你的加密货币 24/7 云端雷达已成功激活并接入 Telegram！"
        send_alert(test_msg)
        return

    logging.info("GitHub Actions 定时扫描任务开始...")
    signals_found = 0

    for coin in CONFIG["SYMBOLS"]:
        klines_4h = fetch_klines(coin, interval="4H", limit=40)
        macro_bullish = False
        if klines_4h and len(klines_4h) >= 20:
            closes_4h = [k["close"] for k in klines_4h]
            ema20_4h = calculate_ema(closes_4h, 20)
            ema50_4h = calculate_ema(closes_4h, 50)
            macro_bullish = ema20_4h[-1] > ema50_4h[-1]

        for tf in CONFIG["TIMEFRAMES"]:
            klines = fetch_klines(coin, interval=tf, limit=50)
            if not klines or len(klines) < 30:
                continue

            closes = [k["close"] for k in klines]
            ema20 = calculate_ema(closes, 20)
            ema50 = calculate_ema(closes, 50)
            rsis = calculate_rsi(closes, 14)

            sig1 = check_strategy_1_divergence_choch(klines, rsis, tf)
            if sig1:
                signals_found += 1
                resonance = "🌟🌟🌟 【多周期共振！4H大方向顺势 + 15m精准扳机】 🌟🌟🌟\n" if (tf == "15m" and macro_bullish) else ""
                msg = (
                    f"{resonance}🚨 交易信号触发：{sig1['scope_tag']}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"标的币种: {coin} / USDT\n"
                    f"监控周期: 【 {sig1['timeframe']} 级别 】\n"
                    f"策略类型: {sig1['strategy']}\n"
                    f"建议操作: {sig1['action']}\n"
                    f"预期持仓: {sig1['holding_desc']}\n"
                    f"入场参考: ${sig1['entry']}\n"
                    f"严格止损: ${sig1['stop_loss']} (破位必须认输保命)\n"
                    f"第一目标: ${sig1['tp1']} (到此减半并提保本损)\n"
                    f"第二目标: ${sig1['tp2']} (大波段终点全部止盈)\n"
                    f"触发逻辑: {sig1['reason']}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💡 纪律：单笔亏损严格锁死在总账户资金 1%~2%！"
                )
                send_alert(msg)

            sig2 = check_strategy_2_ema_pullback(klines, ema20, ema50, tf)
            if sig2:
                signals_found += 1
                resonance = "🌟🌟🌟 【多周期共振！4H大方向顺势 + 15m精准扳机】 🌟🌟🌟\n" if (tf == "15m" and macro_bullish) else ""
                msg = (
                    f"{resonance}🚨 交易信号触发：{sig2['scope_tag']}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"标的币种: {coin} / USDT\n"
                    f"监控周期: 【 {sig2['timeframe']} 级别 】\n"
                    f"策略类型: {sig2['strategy']}\n"
                    f"建议操作: {sig2['action']}\n"
                    f"预期持仓: {sig2['holding_desc']}\n"
                    f"入场参考: ${sig2['entry']}\n"
                    f"严格止损: ${sig2['stop_loss']} (破位必须认输保命)\n"
                    f"第一目标: ${sig2['tp1']} (到此减半并提保本损)\n"
                    f"第二目标: ${sig2['tp2']} (大波段终点全部止盈)\n"
                    f"触发逻辑: {sig2['reason']}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💡 纪律：单笔亏损严格锁死在总账户资金 1%~2%！"
                )
                send_alert(msg)

    logging.info(f"本次扫描完成，共捕获 {signals_found} 个交易信号。")


if __name__ == "__main__":
    main()
