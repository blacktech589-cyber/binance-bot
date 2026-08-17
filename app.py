#!/usr/bin/env python3
"""Binance Spot USDT paritelerinde düşük fiyat + yükseliş başlangıcı tarayıcısı.

Emir göndermez, API anahtarı istemez. Yatırım tavsiyesi değildir.
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
import urllib.parse
import urllib.request
from dataclasses import dataclass


BASE_URL = "https://data-api.binance.vision"
TRADING_URL = "https://api.binance.com"
STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "TRY", "AEUR"}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def api_get(path: str, params: dict | None = None, retries: int = 3):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "coin-scanner/1.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.load(response)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)


def signed_get(path: str, params: dict | None = None):
    """BINANCE_API_KEY / BINANCE_API_SECRET ile salt-okunur imzalı istek."""
    api_key = os.environ.get("BINANCE_API_KEY")
    secret = os.environ.get("BINANCE_API_SECRET")
    if not api_key or not secret:
        raise RuntimeError("BINANCE_API_KEY ve BINANCE_API_SECRET ortam değişkenleri eksik")
    payload = dict(params or {})
    payload.update({"timestamp": int(time.time() * 1000), "recvWindow": 5000})
    query = urllib.parse.urlencode(payload)
    signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        f"{TRADING_URL}{path}?{query}&signature={signature}",
        headers={"X-MBX-APIKEY": api_key, "User-Agent": "coin-scanner/2.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def ema(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def rsi(values: list[float], period: int = 14) -> float:
    changes = [b - a for a, b in zip(values, values[1:])]
    gains = [max(x, 0.0) for x in changes[-period:]]
    losses = [max(-x, 0.0) for x in changes[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    tr = []
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return sum(tr[-period:]) / period


def macd_histogram(values: list[float]) -> tuple[float, float]:
    line = [a - b for a, b in zip(ema(values, 12), ema(values, 26))]
    signal = ema(line, 9)
    return line[-1] - signal[-1], line[-2] - signal[-2]


def order_book_metrics(symbol: str) -> tuple[float, float]:
    book = api_get("/api/v3/depth", {"symbol": symbol, "limit": 20})
    bids = [(float(p), float(q)) for p, q in book["bids"]]
    asks = [(float(p), float(q)) for p, q in book["asks"]]
    bid_value = sum(p * q for p, q in bids)
    ask_value = sum(p * q for p, q in asks)
    imbalance = bid_value / (bid_value + ask_value) if bid_value + ask_value else 0.5
    mid = (bids[0][0] + asks[0][0]) / 2
    spread_bps = (asks[0][0] - bids[0][0]) / mid * 10_000
    return imbalance, spread_bps


@dataclass
class Candidate:
    symbol: str
    price: float
    quote_volume: float
    change_24h: float


def liquid_low_price_coins(max_price: float, min_volume: float, scan_limit: int) -> list[Candidate]:
    """Algoritma 1: İşleme açık, likit, düşük nominal fiyatlı USDT pariteleri."""
    info = api_get("/api/v3/exchangeInfo")
    tickers = {x["symbol"]: x for x in api_get("/api/v3/ticker/24hr")}
    symbols = []
    for item in info["symbols"]:
        base = item["baseAsset"]
        if (
            item["status"] != "TRADING"
            or item["quoteAsset"] != "USDT"
            or not item.get("isSpotTradingAllowed", False)
            or base in STABLES
            or base.endswith(LEVERAGED_SUFFIXES)
        ):
            continue
        ticker = tickers.get(item["symbol"])
        if not ticker:
            continue
        price = float(ticker["lastPrice"])
        volume = float(ticker["quoteVolume"])
        if 0 < price <= max_price and volume >= min_volume:
            symbols.append(Candidate(item["symbol"], price, volume, float(ticker["priceChangePercent"])))
    # API yükünü sınırlarken likiditesi en yüksek adayları önce inceler.
    return sorted(symbols, key=lambda x: x.quote_volume, reverse=True)[:scan_limit]


def rising_score(candidate: Candidate, interval: str) -> dict | None:
    """Scalping topluluğu: bağımsız stratejilerin uzlaşısını puanlar."""
    rows = api_get("/api/v3/klines", {"symbol": candidate.symbol, "interval": interval, "limit": 100})
    # Son mum hâlâ oluşuyor olabilir; yanlış sinyali azaltmak için onu dışarıda bırak.
    rows = rows[:-1]
    highs = [float(x[2]) for x in rows]
    lows = [float(x[3]) for x in rows]
    closes = [float(x[4]) for x in rows]
    volumes = [float(x[5]) for x in rows]
    e9, e21 = ema(closes, 9), ema(closes, 21)
    rsi14 = rsi(closes)
    baseline_volume = sum(volumes[-21:-1]) / 20
    volume_ratio = volumes[-1] / baseline_volume if baseline_volume else 0
    recent_cross = any(e9[i - 1] <= e21[i - 1] and e9[i] > e21[i] for i in range(len(e9) - 3, len(e9)))
    trend = e9[-1] > e21[-1] and e9[-1] > e9[-2]
    breakout = closes[-1] > max(closes[-11:-1])
    not_overheated = 48 <= rsi14 <= 68 and -5 <= candidate.change_24h <= 15

    typical = [(h + l + c) / 3 for h, l, c in zip(highs[-20:], lows[-20:], closes[-20:])]
    vwap20 = sum(p * v for p, v in zip(typical, volumes[-20:])) / sum(volumes[-20:])
    mean20 = statistics.fmean(closes[-20:])
    sd20 = statistics.pstdev(closes[-20:])
    lower_band, upper_band = mean20 - 2 * sd20, mean20 + 2 * sd20
    macd_now, macd_prev = macd_histogram(closes)
    book_imbalance, spread_bps = order_book_metrics(candidate.symbol)

    strategies = []
    # 1) EMA trend/momentum
    if trend and (recent_cross or macd_now > macd_prev > 0):
        strategies.append("EMA_TREND")
    # 2) Hacimli kısa dönem direnç kırılımı
    if breakout and volume_ratio >= 1.5:
        strategies.append("VOLUME_BREAKOUT")
    # 3) VWAP üstüne geri dönüş
    if closes[-2] <= vwap20 < closes[-1] and volume_ratio >= 1.15:
        strategies.append("VWAP_RECLAIM")
    # 4) Bollinger alt banttan ortalamaya dönüş (düşen bıçağı filtrele)
    if lows[-2] <= lower_band and closes[-1] > closes[-2] and rsi14 >= 42 and e9[-1] >= e9[-2]:
        strategies.append("BOLLINGER_REVERSAL")
    # 5) Emir defteri alış baskısı; geniş spread varsa geçersiz
    if book_imbalance >= 0.58 and spread_bps <= 12:
        strategies.append("ORDERBOOK_PRESSURE")

    score = min(100, len(strategies) * 16)
    score += 8 if 50 <= rsi14 <= 64 else 0
    score += 7 if volume_ratio >= 1.5 else 0
    score += 5 if spread_bps <= 5 else 0
    score = min(score, 100)
    if not (not_overheated and spread_bps <= 12 and len(strategies) >= 2 and score >= 50):
        return None

    current_atr = atr(highs, lows, closes)
    stop = closes[-1] - 1.5 * current_atr
    risk_per_coin = closes[-1] - stop
    return {
        "symbol": candidate.symbol,
        "score": score,
        "price": closes[-1],
        "change_24h_pct": candidate.change_24h,
        "quote_volume_usdt": candidate.quote_volume,
        "rsi14": rsi14,
        "volume_ratio": volume_ratio,
        "recent_ema_cross": recent_cross,
        "breakout_10": breakout,
        "strategies": strategies,
        "vwap20": vwap20,
        "macd_hist": macd_now,
        "orderbook_bid_ratio": book_imbalance,
        "spread_bps": spread_bps,
        "stop": stop,
        "target_2r": closes[-1] + 2 * risk_per_coin,
        "risk_per_coin": risk_per_coin,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance Spot yükseliş başlangıcı tarayıcısı")
    parser.add_argument("--max-price", type=float, default=1.0, help="Azami coin fiyatı (USDT)")
    parser.add_argument("--min-volume", type=float, default=5_000_000, help="Asgari 24s hacim (USDT)")
    parser.add_argument("--interval", default="15m", choices=["5m", "15m", "30m", "1h", "4h"])
    parser.add_argument("--scan-limit", type=int, default=40, help="Kline istenecek azami parite")
    parser.add_argument("--capital", type=float, default=1000.0, help="Örnek toplam sermaye (USDT)")
    parser.add_argument("--risk-pct", type=float, default=0.5, help="İşlem başına risk yüzdesi")
    parser.add_argument("--account", action="store_true", help="API anahtarıyla salt-okunur bakiye özeti")
    args = parser.parse_args()

    if args.account:
        account = signed_get("/api/v3/account", {"omitZeroBalances": "true"})
        balances = [f"{x['asset']}={float(x['free']):.8g}" for x in account.get("balances", []) if float(x["free"]) > 0]
        print("Serbest bakiyeler:", ", ".join(balances) or "yok")

    candidates = liquid_low_price_coins(args.max_price, args.min_volume, args.scan_limit)
    results = []
    for coin in candidates:
        try:
            signal = rising_score(coin, args.interval)
            if signal:
                risk_budget = args.capital * args.risk_pct / 100
                units = risk_budget / signal["risk_per_coin"] if signal["risk_per_coin"] > 0 else 0
                # Tek pozisyonun tüm sermayeyi aşmasını engelle.
                units = min(units, args.capital / signal["price"])
                signal["sample_position_units"] = units
                signal["sample_position_usdt"] = units * signal["price"]
                results.append(signal)
        except Exception as exc:
            print(f"Uyarı: {coin.symbol} atlandı: {exc}")

    results.sort(key=lambda x: (x["score"], x["quote_volume_usdt"]), reverse=True)
    if not results:
        print("Şu anda kurallara uyan sinyal yok. Filtreleri gevşetmek yerine beklemek de bir sonuçtur.")
        return
    print(f"{'PARİTE':12} {'PUAN':>5} {'FİYAT':>12} {'RSI':>6} {'HACİM×':>8} {'SPREAD':>7} {'STOP':>12} {'HEDEF':>12} STRATEJİLER")
    for x in results[:15]:
        print(f"{x['symbol']:12} {x['score']:5.0f} {x['price']:12.8g} {x['rsi14']:6.1f} "
              f"{x['volume_ratio']:8.2f} {x['spread_bps']:7.2f} {x['stop']:12.8g} {x['target_2r']:12.8g} "
              f"{','.join(x['strategies'])}")


if __name__ == "__main__":
    main()
