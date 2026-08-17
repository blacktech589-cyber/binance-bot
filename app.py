#!/usr/bin/env python3
"""Binance Spot oynak piyasa tarayıcısı ve Telegram sinyal servisi.

- Emir göndermez.
- 10.000 kapanmış mumu Binance'in 1000 mumluk sayfalarıyla indirir.
- API/secret ve Telegram bilgilerini yalnızca ortam değişkenlerinden okur.
- Sinyaller yatırım tavsiyesi değildir.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MARKET_URL = "https://data-api.binance.vision"
SIGNED_URL = "https://api.binance.com"
STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "TRY", "AEUR"}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def request_json(url: str, data: dict | None = None, headers: dict | None = None, retries: int = 4):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers or {"User-Agent": "long-signal/1.0"})
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (418, 429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            delay = int(exc.headers.get("Retry-After", 2 ** attempt))
            time.sleep(max(1, delay))
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def market_get(path: str, params: dict | None = None):
    url = MARKET_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return request_json(url)


def signed_account():
    """Salt-okunur hesap kontrolü; API anahtarının çalıştığını doğrular."""
    key = os.getenv("BINANCE_API_KEY")
    secret = os.getenv("BINANCE_API_SECRET")
    if not key or not secret:
        raise RuntimeError("BINANCE_API_KEY ve BINANCE_API_SECRET eksik")
    params = {"timestamp": int(time.time() * 1000), "recvWindow": 5000, "omitZeroBalances": "true"}
    query = urllib.parse.urlencode(params)
    signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    return request_json(
        f"{SIGNED_URL}/api/v3/account?{query}&signature={signature}",
        headers={"X-MBX-APIKEY": key, "User-Agent": "long-signal/1.0"},
    )


@dataclass
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_closed_klines(symbol: str, interval: str, total: int = 10_000) -> list[Candle]:
    """En yeni kapanmış mumdan geriye doğru sayfalar; oluşan son mumu atar."""
    rows: list[list] = []
    end_time = int(time.time() * 1000)
    while len(rows) < total + 1:
        limit = min(1000, total + 1 - len(rows))
        page = market_get("/api/v3/klines", {
            "symbol": symbol, "interval": interval, "limit": limit, "endTime": end_time
        })
        if not page:
            break
        rows = page + rows
        end_time = int(page[0][0]) - 1
        if len(page) < limit:
            break
        time.sleep(0.12)
    candles = [Candle(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in rows]
    if candles and candles[-1].open_time + interval_ms(interval) > int(time.time() * 1000):
        candles.pop()
    return candles[-total:]


def interval_ms(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])
    return value * {"m": 60_000, "h": 3_600_000, "d": 86_400_000}[unit]


def ema(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def rsi_series(values: list[float], period: int = 14) -> list[float]:
    out = [50.0] * len(values)
    for i in range(period, len(values)):
        changes = [values[k] - values[k - 1] for k in range(i - period + 1, i + 1)]
        gain = sum(max(x, 0) for x in changes) / period
        loss = sum(max(-x, 0) for x in changes) / period
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def atr(candles: list[Candle], period: int = 14) -> float:
    tr = []
    for i in range(1, len(candles)):
        x, prev = candles[i], candles[i - 1]
        tr.append(max(x.high - x.low, abs(x.high - prev.close), abs(x.low - prev.close)))
    return statistics.fmean(tr[-period:])


def adx(candles: list[Candle], period: int = 14) -> float:
    tr = plus = minus = 0.0
    for i in range(len(candles) - period, len(candles)):
        x, prev = candles[i], candles[i - 1]
        up, down = x.high - prev.high, prev.low - x.low
        tr += max(x.high - x.low, abs(x.high - prev.close), abs(x.low - prev.close))
        plus += max(up, 0) if up > down else 0
        minus += max(down, 0) if down > up else 0
    plus_di, minus_di = 100 * plus / tr, 100 * minus / tr
    return 100 * abs(plus_di - minus_di) / (plus_di + minus_di or 1)


def select_volatile_symbols(min_volume: float, min_range_pct: float, limit: int) -> list[dict]:
    info = market_get("/api/v3/exchangeInfo")
    tickers = {x["symbol"]: x for x in market_get("/api/v3/ticker/24hr")}
    allowed = set()
    for item in info["symbols"]:
        base = item["baseAsset"]
        if (item["status"] == "TRADING" and item["quoteAsset"] == "USDT"
                and item.get("isSpotTradingAllowed", False) and base not in STABLES
                and not base.endswith(LEVERAGED_SUFFIXES)):
            allowed.add(item["symbol"])
    out = []
    for symbol in allowed:
        t = tickers.get(symbol)
        if not t:
            continue
        volume = float(t["quoteVolume"])
        low, high = float(t["lowPrice"]), float(t["highPrice"])
        range_pct = (high - low) / low * 100 if low else 0
        if volume >= min_volume and range_pct >= min_range_pct:
            out.append({"symbol": symbol, "volume": volume, "range_pct": range_pct})
    return sorted(out, key=lambda x: (x["range_pct"], math.log10(x["volume"])), reverse=True)[:limit]


def analyze(symbol: str, candles: list[Candle], daily_range: float) -> dict | None:
    if len(candles) < 500:
        return None
    closes = [x.close for x in candles]
    volumes = [x.volume for x in candles]
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    e12, e26 = ema(closes, 12), ema(closes, 26)
    macd_line = [a - b for a, b in zip(e12, e26)]
    macd_signal = ema(macd_line, 9)
    hist = macd_line[-1] - macd_signal[-1]
    previous_hist = macd_line[-2] - macd_signal[-2]
    rsi = rsi_series(closes)
    rsi14 = rsi[-1]
    stoch_window = rsi[-14:]
    stoch_rsi = (rsi14 - min(stoch_window)) / (max(stoch_window) - min(stoch_window) or 1) * 100
    mean20 = statistics.fmean(closes[-20:])
    sd20 = statistics.pstdev(closes[-20:])
    lower, upper = mean20 - 2 * sd20, mean20 + 2 * sd20
    band_position = (closes[-1] - lower) / (upper - lower or 1)
    band_width = (upper - lower) / mean20 * 100
    current_atr = atr(candles)
    atr_pct = current_atr / closes[-1] * 100
    current_adx = adx(candles)
    volume_ratio = volumes[-1] / statistics.fmean(volumes[-21:-1])
    breakout_55 = closes[-1] > max(closes[-56:-1])
    trend = closes[-1] > e20[-1] > e50[-1] > e200[-1]
    long_trend = e50[-1] > e200[-1] and e200[-1] > e200[-5]

    votes = {
        "EMA20>50>200": trend,
        "EMA50/200 uzun trend": long_trend,
        "MACD ivmesi": hist > 0 and hist > previous_hist,
        "RSI sağlıklı": 50 <= rsi14 <= 68,
        "Stoch RSI": 20 <= stoch_rsi <= 85,
        "Bollinger konumu": 0.45 <= band_position <= 0.90,
        "ADX trend gücü": current_adx >= 20,
        "Hacim artışı": volume_ratio >= 1.30,
        "55 mum kırılımı": breakout_55,
        "ATR oynaklığı": atr_pct >= 1.0,
    }
    weights = [14, 12, 12, 8, 5, 8, 10, 12, 12, 7]
    score = sum(w for w, ok in zip(weights, votes.values()) if ok)
    # Aşırı ısınmış hareketleri cezalandır.
    if rsi14 > 72 or band_position > 1.15:
        score -= 20
    if score < 72 or not trend or not long_trend:
        return None

    entry = closes[-1]
    stop = entry - 2 * current_atr
    risk = entry - stop
    target1, target2 = entry + 2 * risk, entry + 3.5 * risk
    return {
        "symbol": symbol, "score": max(0, min(100, score)), "entry": entry,
        "stop": stop, "target1": target1, "target2": target2,
        "rsi": rsi14, "stoch_rsi": stoch_rsi, "adx": current_adx,
        "atr_pct": atr_pct, "band_position": band_position * 100,
        "band_width": band_width, "volume_ratio": volume_ratio,
        "daily_range": daily_range, "votes": votes, "candle_count": len(candles),
        "candle_time": candles[-1].open_time,
    }


def telegram_send(message: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID eksik")
    result = request_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"},
    )
    if not result.get("ok"):
        raise RuntimeError("Telegram mesajı kabul edilmedi: " + str(result.get("description")))


def format_signal(s: dict, interval: str) -> str:
    active = ", ".join(k for k, v in s["votes"].items() if v)
    return (
        f"🟢 UZUN VADE ARAŞTIRMA SİNYALİ\n\n"
        f"Parite: {s['symbol']} | Zaman: {interval}\n"
        f"Uzlaşı skoru: {s['score']}/100\n"
        f"Kapanış: {s['entry']:.10g}\n"
        f"Örnek stop: {s['stop']:.10g}\n"
        f"Örnek hedef 1: {s['target1']:.10g}\n"
        f"Örnek hedef 2: {s['target2']:.10g}\n\n"
        f"RSI: {s['rsi']:.1f} | ADX: {s['adx']:.1f}\n"
        f"ATR: %{s['atr_pct']:.2f} | Hacim: {s['volume_ratio']:.2f}x\n"
        f"Bollinger konumu: %{s['band_position']:.0f} | Bant: %{s['band_width']:.2f}\n"
        f"24s aralık: %{s['daily_range']:.1f} | Mum: {s['candle_count']}\n\n"
        f"Olumlu kurallar: {active}\n\n"
        "⚠️ Otomatik al emri değildir. Geçmiş performans geleceği garanti etmez."
    )


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def scan_once(args) -> list[dict]:
    print(f"[{datetime.now(timezone.utc).isoformat()}] Oynak pariteler seçiliyor...")
    markets = select_volatile_symbols(args.min_volume, args.min_range, args.market_limit)
    state_path = Path(args.state_file)
    state = load_state(state_path)
    now = time.time()
    signals = []
    for index, market in enumerate(markets, 1):
        symbol = market["symbol"]
        print(f"[{index}/{len(markets)}] {symbol}: {args.candles} mum indiriliyor...")
        try:
            candles = fetch_closed_klines(symbol, args.interval, args.candles)
            signal = analyze(symbol, candles, market["range_pct"])
            if not signal:
                continue
            signals.append(signal)
            last_sent = float(state.get(symbol, 0))
            if now - last_sent >= args.cooldown_hours * 3600:
                telegram_send(format_signal(signal, args.interval))
                state[symbol] = now
                save_state(state_path, state)
                print(f"Telegram sinyali gönderildi: {symbol}")
            else:
                print(f"Tekrar sinyali engellendi: {symbol}")
        except Exception as exc:
            print(f"Uyarı - {symbol} atlandı: {exc}")
        time.sleep(args.symbol_delay)
    return sorted(signals, key=lambda x: x["score"], reverse=True)


def main():
    p = argparse.ArgumentParser(description="Binance 10.000 mum + Telegram uzun vade tarayıcı")
    p.add_argument("--interval", choices=["15m", "30m", "1h", "4h", "1d"], default="1h")
    p.add_argument("--candles", type=int, default=10_000)
    p.add_argument("--market-limit", type=int, default=12, help="Taranacak en oynak parite sayısı")
    p.add_argument("--min-volume", type=float, default=20_000_000, help="Asgari 24s USDT hacmi")
    p.add_argument("--min-range", type=float, default=5.0, help="Asgari 24s fiyat aralığı yüzdesi")
    p.add_argument("--loop-minutes", type=int, default=0, help="0: bir kez; pozitif: sürekli çalış")
    p.add_argument("--cooldown-hours", type=float, default=24.0)
    p.add_argument("--symbol-delay", type=float, default=0.5)
    p.add_argument("--state-file", default="signal_state.json")
    p.add_argument("--account-check", action="store_true")
    p.add_argument("--telegram-test", action="store_true")
    args = p.parse_args()
    args.candles = max(500, min(args.candles, 10_000))

    if args.account_check:
        account = signed_account()
        print("Binance API doğrulandı. Hesap işlem izni:", account.get("canTrade"))
    if args.telegram_test:
        telegram_send("✅ Binance sinyal servisi Telegram bağlantı testi başarılı.")
        print("Telegram test mesajı gönderildi.")
        if args.loop_minutes == 0:
            return

    while True:
        signals = scan_once(args)
        print(f"Tarama tamamlandı. Güçlü sinyal sayısı: {len(signals)}")
        if args.loop_minutes <= 0:
            break
        time.sleep(max(1, args.loop_minutes) * 60)


if __name__ == "__main__":
    main()
