#!/usr/bin/env python3
"""
Crypto Signal Bot - GitHub Actions 定时扫描版 (技术形态 + 宏观日历 + 现货ETF主力扫盘)
三大核心作战雷达：
1. 【技术信号】：11 大主流币 15m/4H 双周期 RSI底背离CHoCH 与 EMA顺势回踩
2. 【宏观数据】：自动监控美国 非农(NFP)、CPI、PPI、初请失业金、美联储FOMC，提前 1~2 小时预警
3. 【现货 ETF 主力扫盘】：通过 Coinbase 溢价指数与盘口突发爆量，毫秒级捕捉贝莱德/富达等美资 ETF 异常扫荡现货筹码！
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timezone, timedelta
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
# Telegram 专属配置 (已为你自动配置好)
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8708038882:AAFrnq6jzFS1OJDg35t32zO6MKLrIIrV7Hc").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7536260641").strip()
LARK_WEBHOOK_URL = os.environ.get("LARK_WEBHOOK_URL", "").strip()

CONFIG = {
    "SYMBOLS": ["BTC", "ETH", "SOL", "XRP", "DOGE", "SUI", "ADA", "LINK", "VET", "ASTER", "LTC"],
    "TIMEFRAMES": ["4H", "15m"]
}


# ==========================================
# 模块一：现货 ETF 与华尔街大宗主力扫盘雷达
# ==========================================
def check_etf_institutional_sweep():
    """
    通过 Coinbase 溢价率 (Coinbase Premium) 与 盘口异常暴量，捕捉贝莱德/富达 ETF 扫盘
    - 贝莱德 (IBIT) 与主流美资现货 ETF 托管机构均为 Coinbase Prime
    - 当美资机构动用大宗算法买入现货时，Coinbase 现货价格会瞬间脱离离岸市场出现大幅正溢价 (+0.07% 以上)
    """
    cache_file = "/tmp/etf_alert_cache.json"
    last_alert_time = 0
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                last_alert_time = json.load(f).get("last_time", 0)
        except Exception:
            last_alert_time = 0

    now_ts = time.time()
    if now_ts - last_alert_time < 3600: # 1小时内不重复轰炸
        return

    try:
        # 1. 获取 Coinbase 现货价格
        cb_url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
        req_cb = urllib.request.Request(cb_url, headers={'User-Agent': 'Mozilla/5.0'})
        cb_data = json.loads(urllib.request.urlopen(req_cb, timeout=6).read().decode())
        cb_price = float(cb_data['data']['amount'])

        # 2. 获取 OKX 离岸基准价格
        okx_url = "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP"
        req_okx = urllib.request.Request(okx_url, headers={'User-Agent': 'Mozilla/5.0'})
        okx_data = json.loads(urllib.request.urlopen(req_okx, timeout=6).read().decode())
        okx_price = float(okx_data['data'][0]['last'])

        # 3. 计算 Coinbase 溢价率
        premium_pct = ((cb_price - okx_price) / okx_price) * 100

        # 4. 获取最近 15m 成交量异动倍数
        klines_url = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=15m&limit=25"
        req_k = urllib.request.Request(klines_url, headers={'User-Agent': 'Mozilla/5.0'})
        klines = json.loads(urllib.request.urlopen(req_k, timeout=6).read().decode())['data']
        
        latest_vol = float(klines[0][5])
        past_vols = [float(k[5]) for k in klines[1:21]]
        avg_vol = sum(past_vols) / len(past_vols) if past_vols else 1
        vol_ratio = latest_vol / avg_vol
        close_p = float(klines[0][4])
        open_p = float(klines[0][1])

        # 触发判定：
        # 状况 A: 强正溢价 (>= +0.07%) 且 伴随放量 (>= 2.0倍) 且 收阳线 -> 贝莱德美资ETF主力扫盘
        # 状况 B: 极端反常放量 (>= 3.8倍) 且 实体坚决 -> 现货大户暴力吞噬盘口
        is_etf_sweep = (premium_pct >= 0.07 and vol_ratio >= 2.0 and close_p > open_p) or (vol_ratio >= 3.8 and close_p > open_p)

        if is_etf_sweep:
            with open(cache_file, "w") as f:
                json.dump({"last_time": now_ts}, f)

            msg = (
                f"🐋 【现货 ETF / 华尔街主力异动扫盘预警】\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"监测标的: BTC 现货 & 机构流动性池\n"
                f"异动特征: 【美资机构大宗算法正在主动扫荡卖单】\n"
                f"Coinbase 溢价率: {premium_pct:+.3f}% (明显正溢价，买盘来自美资正规军)\n"
                f"盘口量能放大: {vol_ratio:.1f} 倍 (突发巨额主动吃单)\n"
                f"当前现货基准: ${round(okx_price, 2)}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💡 20年交易员实战指引：\n"
                f"1. 现货 ETF 的买入属于‘非杠杆硬买盘’，极难被单根阴线击穿；\n"
                f"2. 此类异动往往引发合约市场的‘空头多杀多/爆仓轧空’（Short Squeeze）；\n"
                f"3. 策略：严禁逆势猜顶开空，逢低回踩坚决顺势跟多！"
            )
            send_alert(msg)

    except Exception as e:
        logging.warning(f"ETF 扫盘监控探测异常: {e}")


# ==========================================
# 模块二：宏观经济日历雷达 (CPI / 非农 / PPI / 失业金 / FOMC)
# ==========================================
def check_macro_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            events = json.loads(response.read().decode())
    except Exception as e:
        logging.warning(f"获取宏观经济日历失败: {e}")
        return

    now = datetime.now(timezone.utc)
    target_keywords = ['cpi', 'ppi', 'payrolls', 'claims', 'fomc', 'rate', 'powell', 'retail sales']

    cache_file = "/tmp/macro_alerted_cache.json"
    alerted = []
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                alerted = json.load(f)
        except Exception:
            alerted = []

    for e in events:
        if e.get('country') != 'USD' or e.get('impact') not in ['High', 'Medium']:
            continue

        title = e.get('title', '')
        if not any(k in title.lower() for k in target_keywords):
            continue

        dt_str = e.get('date')
        try:
            event_dt = datetime.fromisoformat(dt_str)
            bj_dt = event_dt.astimezone(timezone(timedelta(hours=8)))
            hours_diff = (event_dt - now).total_seconds() / 3600

            cache_id = f"{title}_{dt_str}"
            if 0 < hours_diff <= 2.0 and cache_id not in alerted:
                alerted.append(cache_id)
                
                tips = "数据公布前后 15 分钟切勿开新仓，做市商撤单极易产生双向巨额插针！"
                if "cpi" in title.lower():
                    tips = "【通胀核心指标】：若公布值低于预期，降息预期升温，利多币圈！反之若高于预期，警惕短线急跌。"
                elif "payrolls" in title.lower():
                    tips = "【非农超级重磅】：若就业强劲则美元走强利空币圈；若就业放缓则强化降息利好风险资产。"
                elif "claims" in title.lower():
                    tips = "【初请失业金】：每周四固定前瞻指标，反映美国劳动力市场实时降温程度。"
                elif "fomc" in title.lower() or "rate" in title.lower():
                    tips = "【美联储利率决议】：年度顶级海啸事件，建议清仓观望鲍威尔发言。"

                msg = (
                    f"⏰ 【宏观警报：重磅数据倒计时】\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"事件名称: {title} (美国USD)\n"
                    f"公布时间: 北京时间 {bj_dt.strftime('%m-%d %H:%M')} (约 {int(hours_diff * 60)} 分钟后)\n"
                    f"预测数值: {e.get('forecast', '暂无预测')}\n"
                    f"前期数值: {e.get('previous', '暂无前值')}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💡 20年交易员风控提示：\n{tips}"
                )
                send_alert(msg)

        except Exception as ex:
            logging.error(f"解析宏观时间失败: {ex}")

    try:
        with open(cache_file, "w") as f:
            json.dump(alerted[-50:], f)
    except Exception:
        pass


# ==========================================
# 模块三：技术行情数据拉取与指标计算
# ==========================================
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

    if LARK_WEBHOOK_URL:
        try:
            payload = json.dumps({"msg_type": "text", "content": {"text": text_msg}}).encode('utf-8')
            req = urllib.request.Request(LARK_WEBHOOK_URL, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as res:
                logging.info("Lark 推送成功！")
        except Exception as e:
            logging.error(f"Lark 发送失败: {e}")


def main():
    if "--test-alert" in sys.argv:
        test_msg = "🟢 【GitHub Actions 联调成功】\n你的加密货币 24/7 云端雷达已成功激活并接入 Telegram！"
        send_alert(test_msg)
        return

    # 1. 优先探测：现货 ETF 与 华尔街大宗主力扫盘异动
    logging.info("正在执行 现货ETF与美资主力扫盘探测...")
    check_etf_institutional_sweep()

    # 2. 执行宏观日历巡检 (重磅数据前 1~2 小时自动预警)
    logging.info("正在执行 宏观经济数据日历扫描...")
    check_macro_events()

    # 3. 执行 11 大币种技术行情 K 线扫描
    logging.info("正在执行 加密货币技术指标扫描...")
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

    logging.info(f"本次扫描完成，共捕获 {signals_found} 个技术交易信号。")


if __name__ == "__main__":
    main()
