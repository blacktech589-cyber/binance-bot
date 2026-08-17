#!/usr/bin/env python3
"""Binance Spot oynak piyasa tarayıcısı, Streamlit paneli ve Telegram servisi.

- Emir göndermez.
- Risk filtrelerini gevşetmeden kural tabanlı sinyal üretir.
- Ek teknik stratejileri ve opsiyonel DL filtresini ensemble olarak birleştirir.
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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

MARKET_URL = "https://data-api.binance.vision"
SIGNED_URL = "https://api.binance.com"
STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "TRY", "AEUR"}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
DEFAULT_ALGORITHMS = ("rule_based", "trend_follow", "momentum", "mean_reversion", "breakout")
RETRYABLE_HTTP_CODES = {418, 429, 500, 502, 503, 504}


@dataclass
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class StrategyResult:
    key: str
    label: str
    score: float
    bullish: bool
    summary: str
    details: dict = field(default_factory=dict)


@dataclass
class DLResult:
    enabled: bool
    available: bool
    score: float
    bullish: bool
    confidence: float
    backend: str
    summary: str


@dataclass
class ScanConfig:
    interval: str
    candles: int
    market_limit: int
    min_volume: float
    min_range: float
    cooldown_hours: float
    symbol_delay: float
    state_file: str
    send_digest: bool
    top_recommendations: int
    digest_cooldown_hours: float
    enabled_algorithms: tuple[str, ...]
    enable_dl: bool
    ensemble_threshold: float = 72.0
    allow_telegram: bool = True


def parse_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read(512).decode("utf-8", errors="ignore").strip()
    except Exception:
        body = ""
    detail = body or exc.reason or "Bilinmeyen HTTP hatası"
    if exc.code == 451:
        return "HTTP 451: Bölgesel erişim kısıtı nedeniyle Binance verisine ulaşılamadı."
    return f"HTTP {exc.code}: {detail}"


def request_json(url: str, data: dict | None = None, headers: dict | None = None, retries: int = 4):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    request_headers = headers or {"User-Agent": "long-signal/1.0"}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=request_headers)
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in RETRYABLE_HTTP_CODES and attempt < retries - 1:
                delay = int(exc.headers.get("Retry-After", 2 ** attempt))
                time.sleep(max(1, delay))
                continue
            raise RuntimeError(parse_http_error(exc)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Ağ hatası: {exc}") from exc
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


def interval_ms(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])
    return value * {"m": 60_000, "h": 3_600_000, "d": 86_400_000}[unit]


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def safe_mean(values: list[float], fallback: float = 0.0) -> float:
    return statistics.fmean(values) if values else fallback


def pct_change(start: float, end: float) -> float:
    return 0.0 if start == 0 else (end - start) / start * 100


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
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
    if len(candles) < 2:
        return 0.0
    tr = []
    for i in range(1, len(candles)):
        x, prev = candles[i], candles[i - 1]
        tr.append(max(x.high - x.low, abs(x.high - prev.close), abs(x.low - prev.close)))
    if not tr:
        return 0.0
    return safe_mean(tr[-period:], tr[-1])


def adx(candles: list[Candle], period: int = 14) -> float:
    if len(candles) <= period:
        return 0.0
    tr = plus = minus = 0.0
    for i in range(len(candles) - period, len(candles)):
        x, prev = candles[i], candles[i - 1]
        up, down = x.high - prev.high, prev.low - x.low
        tr += max(x.high - x.low, abs(x.high - prev.close), abs(x.low - prev.close))
        plus += max(up, 0) if up > down else 0
        minus += max(down, 0) if down > up else 0
    if tr == 0:
        return 0.0
    plus_di, minus_di = 100 * plus / tr, 100 * minus / tr
    return 100 * abs(plus_di - minus_di) / (plus_di + minus_di or 1)


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


def build_snapshot(symbol: str, candles: list[Candle], daily_range: float) -> dict | None:
    if len(candles) < 240:
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
    previous_rsi = rsi[-2]
    stoch_window = rsi[-14:]
    stoch_rsi = (rsi14 - min(stoch_window)) / (max(stoch_window) - min(stoch_window) or 1) * 100
    mean20 = safe_mean(closes[-20:], closes[-1])
    sd20 = statistics.pstdev(closes[-20:]) if len(closes) >= 20 else 0.0
    lower, upper = mean20 - 2 * sd20, mean20 + 2 * sd20
    band_position = (closes[-1] - lower) / (upper - lower or 1)
    band_width = (upper - lower) / mean20 * 100 if mean20 else 0.0
    current_atr = atr(candles)
    atr_pct = current_atr / closes[-1] * 100 if closes[-1] else 0.0
    current_adx = adx(candles)
    avg_volume = safe_mean(volumes[-21:-1], volumes[-1] or 1.0)
    volume_ratio = volumes[-1] / (avg_volume or 1.0)
    breakout_20 = closes[-1] > max(closes[-21:-1])
    breakout_55 = closes[-1] > max(closes[-56:-1])
    trend = closes[-1] > e20[-1] > e50[-1] > e200[-1]
    long_trend = e50[-1] > e200[-1] and e200[-1] > e200[-5]
    return {
        "symbol": symbol,
        "candles": candles,
        "closes": closes,
        "volumes": volumes,
        "daily_range": daily_range,
        "e20": e20,
        "e50": e50,
        "e200": e200,
        "e12": e12,
        "e26": e26,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "hist": hist,
        "previous_hist": previous_hist,
        "rsi14": rsi14,
        "previous_rsi": previous_rsi,
        "stoch_rsi": stoch_rsi,
        "mean20": mean20,
        "lower": lower,
        "upper": upper,
        "band_position": band_position,
        "band_width": band_width,
        "atr": current_atr,
        "atr_pct": atr_pct,
        "adx": current_adx,
        "volume_ratio": volume_ratio,
        "breakout_20": breakout_20,
        "breakout_55": breakout_55,
        "trend": trend,
        "long_trend": long_trend,
        "entry": closes[-1],
        "roc_5": pct_change(closes[-6], closes[-1]),
        "roc_20": pct_change(closes[-21], closes[-1]),
        "candle_count": len(candles),
        "candle_time": candles[-1].open_time,
    }


def strategy_rule_based(snapshot: dict) -> StrategyResult:
    votes = {
        "EMA20>50>200": snapshot["trend"],
        "EMA50/200 uzun trend": snapshot["long_trend"],
        "MACD ivmesi": snapshot["hist"] > 0 and snapshot["hist"] > snapshot["previous_hist"],
        "RSI sağlıklı": 50 <= snapshot["rsi14"] <= 68,
        "Stoch RSI": 20 <= snapshot["stoch_rsi"] <= 85,
        "Bollinger konumu": 0.45 <= snapshot["band_position"] <= 0.90,
        "ADX trend gücü": snapshot["adx"] >= 20,
        "Hacim artışı": snapshot["volume_ratio"] >= 1.30,
        "55 mum kırılımı": snapshot["breakout_55"],
        "ATR oynaklığı": snapshot["atr_pct"] >= 1.0,
    }
    weights = [14, 12, 12, 8, 5, 8, 10, 12, 12, 7]
    score = sum(w for w, ok in zip(weights, votes.values()) if ok)
    if snapshot["rsi14"] > 72 or snapshot["band_position"] > 1.15:
        score -= 20
    score = clamp(score)
    bullish = score >= 72 and snapshot["trend"] and snapshot["long_trend"]
    summary = "Mevcut korumalı kural seti" if bullish else "Ana trend filtresi tam onay vermedi"
    return StrategyResult("rule_based", "Mevcut kural tabanlı", score, bullish, summary, {"votes": votes})


def strategy_trend_follow(snapshot: dict) -> StrategyResult:
    checks = {
        "Trend dizilimi": snapshot["trend"],
        "EMA20 yükseliyor": snapshot["e20"][-1] > snapshot["e20"][-5],
        "ADX yeterli": snapshot["adx"] >= 18,
        "Fiyat EMA20 üstü": snapshot["entry"] >= snapshot["e20"][-1],
        "ATR dengeli": 0.6 <= snapshot["atr_pct"] <= 8.0,
        "Hacim nötr+": snapshot["volume_ratio"] >= 1.05,
    }
    weights = [28, 18, 18, 14, 10, 12]
    score = sum(w for w, ok in zip(weights, checks.values()) if ok)
    score = clamp(score - (12 if snapshot["rsi14"] > 78 else 0))
    bullish = score >= 60 and checks["Trend dizilimi"]
    return StrategyResult("trend_follow", "Trend takibi", score, bullish, "EMA/ADX trend uyumu", {"votes": checks})


def strategy_momentum(snapshot: dict) -> StrategyResult:
    checks = {
        "MACD pozitif": snapshot["hist"] > 0,
        "MACD hızlanıyor": snapshot["hist"] > snapshot["previous_hist"],
        "5 mum momentumu": snapshot["roc_5"] >= 1.0,
        "20 mum momentumu": snapshot["roc_20"] >= 3.0,
        "RSI momentum alanı": 55 <= snapshot["rsi14"] <= 75,
        "Hacim desteği": snapshot["volume_ratio"] >= 1.15,
    }
    weights = [20, 15, 15, 20, 15, 15]
    score = clamp(sum(w for w, ok in zip(weights, checks.values()) if ok) - (10 if snapshot["band_position"] > 1.2 else 0))
    bullish = score >= 60 and checks["MACD pozitif"] and checks["20 mum momentumu"]
    return StrategyResult("momentum", "Momentum", score, bullish, "Kısa/orta vade ivme ölçümü", {"votes": checks})


def strategy_mean_reversion(snapshot: dict) -> StrategyResult:
    near_lower_band = snapshot["band_position"] <= 0.35
    oversold_rebound = snapshot["previous_rsi"] <= 40 and snapshot["rsi14"] >= snapshot["previous_rsi"]
    micro_recovery = snapshot["entry"] >= safe_mean(snapshot["closes"][-3:], snapshot["entry"])
    compressed_band = snapshot["band_width"] >= 3.0
    risk_ok = snapshot["atr_pct"] <= 7.0
    checks = {
        "Alt banda yakın": near_lower_band,
        "RSI toparlanıyor": oversold_rebound,
        "Kısa toparlanma": micro_recovery,
        "Bant yeterli": compressed_band,
        "Risk uygun": risk_ok,
        "Günlük aralık canlı": snapshot["daily_range"] >= 4.0,
    }
    weights = [28, 22, 15, 10, 10, 15]
    score = clamp(sum(w for w, ok in zip(weights, checks.values()) if ok))
    bullish = score >= 58 and near_lower_band and oversold_rebound
    return StrategyResult("mean_reversion", "Ortalamaya dönüş", score, bullish, "Bant altı tepki arayışı", {"votes": checks})


def strategy_breakout(snapshot: dict) -> StrategyResult:
    checks = {
        "20 mum kırılımı": snapshot["breakout_20"],
        "55 mum teyidi": snapshot["breakout_55"],
        "ADX trend gücü": snapshot["adx"] >= 18,
        "Hacim güçlü": snapshot["volume_ratio"] >= 1.20,
        "MACD pozitif": snapshot["hist"] > 0,
        "Günlük hareket canlı": snapshot["daily_range"] >= 5.0,
    }
    weights = [24, 18, 16, 16, 12, 14]
    score = clamp(sum(w for w, ok in zip(weights, checks.values()) if ok) - (12 if snapshot["rsi14"] > 80 else 0))
    bullish = score >= 60 and checks["20 mum kırılımı"] and checks["ADX trend gücü"]
    return StrategyResult("breakout", "Kırılım", score, bullish, "Breakout + hacim teyidi", {"votes": checks})


STRATEGY_SPECS = {
    "rule_based": {"label": "Mevcut kural tabanlı", "weight": 1.45, "fn": strategy_rule_based},
    "trend_follow": {"label": "Trend takibi", "weight": 1.10, "fn": strategy_trend_follow},
    "momentum": {"label": "Momentum", "weight": 1.00, "fn": strategy_momentum},
    "mean_reversion": {"label": "Ortalamaya dönüş", "weight": 0.85, "fn": strategy_mean_reversion},
    "breakout": {"label": "Kırılım", "weight": 0.95, "fn": strategy_breakout},
}


def available_dl_backend() -> str | None:
    for backend in ("torch", "tensorflow"):
        try:
            __import__(backend)
            return backend
        except Exception:
            continue
    return None


def build_dl_features(snapshot: dict) -> tuple[list[list[float]], list[int]]:
    closes = snapshot["closes"][-220:]
    volumes = snapshot["volumes"][-220:]
    features: list[list[float]] = []
    labels: list[int] = []
    for idx in range(21, len(closes) - 1):
        prev_close = closes[idx - 1]
        ret1 = pct_change(prev_close, closes[idx]) / 10
        ret3 = pct_change(closes[idx - 3], closes[idx]) / 10
        ret10 = pct_change(closes[idx - 10], closes[idx]) / 10
        mean10 = safe_mean(closes[idx - 10:idx], closes[idx])
        distance_to_mean = (closes[idx] - mean10) / (mean10 or 1)
        vol_ratio = volumes[idx] / (safe_mean(volumes[idx - 10:idx], volumes[idx]) or 1)
        candle = snapshot["candles"][-220:][idx]
        body = (candle.close - candle.open) / (candle.open or 1)
        features.append([ret1, ret3, ret10, distance_to_mean, vol_ratio / 3, body * 5])
        labels.append(1 if closes[idx + 1] > closes[idx] else 0)
    return features, labels


def run_dl_filter(snapshot: dict, enabled: bool) -> DLResult:
    if not enabled:
        return DLResult(False, False, 0.0, False, 0.0, "disabled", "DL filtresi kapalı")
    backend = available_dl_backend()
    if backend is None:
        return DLResult(True, False, 0.0, False, 0.0, "none", "TensorFlow/PyTorch yok, klasik algoritmalarla devam edildi")
    features, labels = build_dl_features(snapshot)
    if len(features) < 40:
        return DLResult(True, False, 0.0, False, 0.0, backend, "DL için yeterli örnek oluşmadı")
    deadline = time.perf_counter() + 2.0
    try:
        if backend == "torch":
            return run_torch_filter(features, labels, deadline)
        return run_tensorflow_filter(features, labels, deadline)
    except Exception as exc:
        return DLResult(True, False, 0.0, False, 0.0, backend, f"DL hata verdi, klasik modda devam edildi: {exc}")


def run_torch_filter(features: list[list[float]], labels: list[int], deadline: float) -> DLResult:
    import torch

    torch.set_num_threads(1)
    x = torch.tensor(features, dtype=torch.float32)
    y = torch.tensor(labels, dtype=torch.float32).unsqueeze(1)
    split = max(24, int(len(features) * 0.8))
    x_train, y_train = x[:split], y[:split]
    x_test = x[split:] if split < len(features) else x[-1:]
    model = torch.nn.Sequential(
        torch.nn.Linear(x.shape[1], 8),
        torch.nn.ReLU(),
        torch.nn.Linear(8, 1),
        torch.nn.Sigmoid(),
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=0.03)
    loss_fn = torch.nn.BCELoss()
    for _ in range(6):
        if time.perf_counter() > deadline:
            break
        optimizer.zero_grad()
        loss = loss_fn(model(x_train), y_train)
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        probability = float(model(x[-1:])[0][0].item())
        test_prob = float(model(x_test).mean().item())
    score = clamp(probability * 100)
    return DLResult(True, True, score, probability >= 0.58, test_prob, "torch", f"PyTorch mini-MLP olasılık={probability:.2f}")


def run_tensorflow_filter(features: list[list[float]], labels: list[int], deadline: float) -> DLResult:
    import tensorflow as tf

    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(1)
    x = tf.convert_to_tensor(features, dtype=tf.float32)
    y = tf.convert_to_tensor([[label] for label in labels], dtype=tf.float32)
    split = max(24, int(len(features) * 0.8))
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(len(features[0]),)),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(0.03), loss="binary_crossentropy")
    max_epochs = 6
    for _ in range(max_epochs):
        if time.perf_counter() > deadline:
            break
        model.fit(x[:split], y[:split], epochs=1, batch_size=min(32, split), verbose=0)
    probability = float(model(x[-1:], training=False).numpy()[0][0])
    confidence = float(model(x[split:], training=False).numpy().mean()) if split < len(features) else probability
    score = clamp(probability * 100)
    return DLResult(True, True, score, probability >= 0.58, confidence, "tensorflow", f"TensorFlow mini-MLP olasılık={probability:.2f}")


def combine_ensemble(snapshot: dict, enabled_algorithms: tuple[str, ...], enable_dl: bool, threshold: float) -> dict:
    selected = [key for key in enabled_algorithms if key in STRATEGY_SPECS]
    if not selected:
        selected = ["rule_based"]
    strategies = []
    total_weight = 0.0
    weighted_score = 0.0
    bullish_weight = 0.0
    base_votes = {}
    for key in selected:
        spec = STRATEGY_SPECS[key]
        result = spec["fn"](snapshot)
        strategies.append(result)
        weighted_score += result.score * spec["weight"]
        total_weight += spec["weight"]
        if result.bullish:
            bullish_weight += spec["weight"]
        if key == "rule_based":
            base_votes = result.details.get("votes", {})
    ensemble_score = weighted_score / (total_weight or 1.0)
    agreement = bullish_weight / (total_weight or 1.0)
    ensemble_score = clamp(ensemble_score * (0.75 + 0.25 * agreement))
    dl_result = run_dl_filter(snapshot, enable_dl)
    if dl_result.available:
        ensemble_score = clamp(ensemble_score * 0.85 + dl_result.score * 0.15)
    bullish = ensemble_score >= threshold and agreement >= 0.35
    if "rule_based" in selected:
        base_rule = next((item for item in strategies if item.key == "rule_based"), None)
        rule_guard = bool(
            base_rule
            and (
                base_rule.score >= 60
                or (agreement >= 0.55 and ensemble_score >= threshold + 5)
            )
        )
        bullish = bullish and rule_guard
    entry = snapshot["entry"]
    stop = entry - 2 * snapshot["atr"]
    risk = max(entry - stop, entry * 0.005)
    target1, target2 = entry + 2 * risk, entry + 3.5 * risk
    return {
        "symbol": snapshot["symbol"],
        "score": round(ensemble_score, 2),
        "entry": entry,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "rsi": snapshot["rsi14"],
        "stoch_rsi": snapshot["stoch_rsi"],
        "adx": snapshot["adx"],
        "atr_pct": snapshot["atr_pct"],
        "band_position": snapshot["band_position"] * 100,
        "band_width": snapshot["band_width"],
        "volume_ratio": snapshot["volume_ratio"],
        "daily_range": snapshot["daily_range"],
        "votes": base_votes,
        "candle_count": snapshot["candle_count"],
        "candle_time": snapshot["candle_time"],
        "strategies": strategies,
        "active_algorithms": [STRATEGY_SPECS[key]["label"] for key in selected],
        "agreement": agreement,
        "bullish": bullish,
        "dl": dl_result,
    }


def analyze(symbol: str, candles: list[Candle], daily_range: float,
            enabled_algorithms: tuple[str, ...] = ("rule_based",), enable_dl: bool = False,
            threshold: float = 72.0) -> dict | None:
    snapshot = build_snapshot(symbol, candles, daily_range)
    if snapshot is None:
        return None
    result = combine_ensemble(snapshot, enabled_algorithms, enable_dl, threshold)
    if not result["bullish"]:
        return None
    return result


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


def format_signal(signal: dict, interval: str) -> str:
    active_rules = ", ".join(key for key, ok in signal["votes"].items() if ok) or "Yok"
    strategy_lines = ", ".join(
        f"{item.label}:{item.score:.0f}" + ("✅" if item.bullish else "•")
        for item in signal["strategies"]
    )
    dl = signal["dl"]
    dl_line = (
        f"{dl.backend} DL: {dl.score:.0f}/100 ({dl.summary})"
        if dl.enabled and dl.available else dl.summary
    )
    return (
        f"🟢 UZUN VADE ARAŞTIRMA SİNYALİ\n\n"
        f"Parite: {signal['symbol']} | Zaman: {interval}\n"
        f"Ensemble skoru: {signal['score']}/100\n"
        f"Algoritma uyumu: %{signal['agreement'] * 100:.0f}\n"
        f"Kapanış: {signal['entry']:.10g}\n"
        f"Örnek stop: {signal['stop']:.10g}\n"
        f"Örnek hedef 1: {signal['target1']:.10g}\n"
        f"Örnek hedef 2: {signal['target2']:.10g}\n\n"
        f"RSI: {signal['rsi']:.1f} | ADX: {signal['adx']:.1f}\n"
        f"ATR: %{signal['atr_pct']:.2f} | Hacim: {signal['volume_ratio']:.2f}x\n"
        f"Bollinger konumu: %{signal['band_position']:.0f} | Bant: %{signal['band_width']:.2f}\n"
        f"24s aralık: %{signal['daily_range']:.1f} | Mum: {signal['candle_count']}\n\n"
        f"Aktif stratejiler: {strategy_lines}\n"
        f"DL durumu: {dl_line}\n"
        f"Olumlu ana kurallar: {active_rules}\n\n"
        "⚠️ Otomatik al emri değildir. Geçmiş performans geleceği garanti etmez."
    )


def format_recommendations(signals: list[dict], interval: str, top_n: int) -> str:
    if not signals:
        return (
            "🔎 OTOMATİK COİN TARAMASI\n\n"
            f"Zaman aralığı: {interval}\n"
            "Şu anda bütün risk ve trend filtrelerini geçen aday yok.\n\n"
            "⚠️ Sinyal olmaması da bir sonuçtur; filtreler otomatik gevşetilmedi."
        )
    lines = [
        "📊 OTOMATİK COİN İZLEME LİSTESİ",
        "",
        f"Zaman aralığı: {interval}",
        f"Uygun aday: {len(signals)}",
        "",
    ]
    for rank, signal in enumerate(signals[:top_n], 1):
        lines.extend([
            f"{rank}) {signal['symbol']} — {signal['score']}/100",
            f"   Kapanış: {signal['entry']:.10g}",
            f"   Stop: {signal['stop']:.10g}",
            f"   Hedef: {signal['target1']:.10g} / {signal['target2']:.10g}",
            f"   Uyumluluk: %{signal['agreement'] * 100:.0f} | RSI {signal['rsi']:.1f} | ADX {signal['adx']:.1f}",
            f"   Stratejiler: {', '.join(signal['active_algorithms'])}",
            "",
        ])
    lines.append("⚠️ İzleme listesi yatırım tavsiyesi veya otomatik alım emri değildir.")
    return "\n".join(lines)


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def diagnose_environment() -> list[tuple[str, str]]:
    diagnostics: list[tuple[str, str]] = []
    if os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_SECRET"):
        diagnostics.append(("success", "Binance API anahtarları tanımlı"))
    else:
        diagnostics.append(("warning", "Binance API anahtarları tanımlı değil; yalnızca halka açık veriler kullanılabilir"))
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        diagnostics.append(("success", "Telegram gönderimi hazır"))
    else:
        diagnostics.append(("warning", "Telegram değişkenleri eksik; panel içi tarama çalışır, mesaj gönderimi pasif kalır"))
    diagnostics.append(("info", "HTTP 451 görürseniz bu genelde bölgesel Binance erişim kısıtı anlamına gelir"))
    return diagnostics


def format_exception(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    if "HTTP 451" in text:
        return "Binance verisi 451 ile engellendi. Bölgesel erişim/VPN/host konumu kontrol edilmeli."
    if "BINANCE_API_KEY" in text:
        return "Binance API anahtarları eksik veya erişilemiyor."
    if "TELEGRAM" in text:
        return "Telegram bilgileri eksik; sinyaller üretildi ama mesaj gönderimi yapılamadı."
    return text


def scan_once(config: ScanConfig, progress_callback: Callable[[int, int, str], None] | None = None,
              emit_logs: bool = True) -> tuple[list[dict], list[str]]:
    diagnostics: list[str] = []
    if emit_logs:
        print(f"[{datetime.now(timezone.utc).isoformat()}] Oynak pariteler seçiliyor...")
    markets = select_volatile_symbols(config.min_volume, config.min_range, config.market_limit)
    state_path = Path(config.state_file)
    state = load_state(state_path)
    now = time.time()
    signals = []
    can_send_telegram = config.allow_telegram and bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
    if config.allow_telegram and not can_send_telegram:
        diagnostics.append("Telegram ortam değişkenleri eksik olduğu için gönderim kapatıldı.")
    for index, market in enumerate(markets, 1):
        symbol = market["symbol"]
        if progress_callback:
            progress_callback(index, len(markets), symbol)
        if emit_logs:
            print(f"[{index}/{len(markets)}] {symbol}: {config.candles} mum indiriliyor...")
        try:
            candles = fetch_closed_klines(symbol, config.interval, config.candles)
            signal = analyze(
                symbol,
                candles,
                market["range_pct"],
                enabled_algorithms=config.enabled_algorithms,
                enable_dl=config.enable_dl,
                threshold=config.ensemble_threshold,
            )
            if not signal:
                continue
            signals.append(signal)
            last_sent = float(state.get(symbol, 0))
            if can_send_telegram and now - last_sent >= config.cooldown_hours * 3600:
                telegram_send(format_signal(signal, config.interval))
                state[symbol] = now
                save_state(state_path, state)
                if emit_logs:
                    print(f"Telegram sinyali gönderildi: {symbol}")
            elif can_send_telegram and emit_logs:
                print(f"Tekrar sinyali engellendi: {symbol}")
        except Exception as exc:
            warning = f"{symbol} atlandı: {format_exception(exc)}"
            diagnostics.append(warning)
            if emit_logs:
                print("Uyarı - " + warning)
        time.sleep(config.symbol_delay)
    signals = sorted(signals, key=lambda x: (x["score"], x["volume_ratio"]), reverse=True)
    if config.send_digest and can_send_telegram:
        digest_key = "__digest__"
        last_digest = float(state.get(digest_key, 0))
        if now - last_digest >= config.digest_cooldown_hours * 3600:
            telegram_send(format_recommendations(signals, config.interval, config.top_recommendations))
            state[digest_key] = now
            save_state(state_path, state)
            if emit_logs:
                print("Telegram sıralı coin özeti gönderildi.")
    return signals, diagnostics


def parse_algorithm_selection(value: str) -> tuple[str, ...]:
    if not value or value.lower() == "all":
        return DEFAULT_ALGORITHMS
    selected = tuple(part.strip() for part in value.split(",") if part.strip() in STRATEGY_SPECS)
    return selected or ("rule_based",)


def is_running_in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


def render_streamlit_app():
    import streamlit as st

    st.set_page_config(page_title="Binance Çoklu Algoritma Paneli", layout="wide")
    st.title("📈 Binance Çoklu Algoritma Paneli")
    st.caption("Kural tabanlı strateji + teknik stratejiler + opsiyonel DL filtresi")

    for level, message in diagnose_environment():
        getattr(st, level if level in {"success", "warning", "info"} else "info")(message)

    with st.sidebar:
        st.header("Tarama Ayarları")
        interval = st.selectbox("Zaman dilimi", ["15m", "30m", "1h", "4h", "1d"], index=2)
        candles = st.slider("Mum sayısı", min_value=500, max_value=3000, value=1200, step=100)
        market_limit = st.slider("Tarama parite limiti", min_value=4, max_value=30, value=12)
        min_volume = st.number_input("Min 24s hacim (USDT)", min_value=1_000_000.0, value=20_000_000.0, step=1_000_000.0)
        min_range = st.slider("Min 24s aralık %", min_value=1.0, max_value=15.0, value=5.0, step=0.5)
        ensemble_threshold = st.slider("Ensemble eşik skoru", min_value=50.0, max_value=90.0, value=72.0, step=1.0)
        allow_telegram = st.checkbox("Telegram gönderimine izin ver", value=False)

        st.header("Algoritma Seçimi")
        selected_algorithms = []
        for key in DEFAULT_ALGORITHMS:
            if st.checkbox(STRATEGY_SPECS[key]["label"], value=True):
                selected_algorithms.append(key)
        enable_dl = st.checkbox("Derin öğrenme filtresini aç", value=False)
        backend = available_dl_backend()
        if enable_dl and backend is None:
            st.warning("TensorFlow/PyTorch bulunamadı; DL kapatılsa da panel çalışmaya devam edecek.")
        elif enable_dl:
            st.info(f"DL backend hazır: {backend}")

        start_scan = st.button("Taramayı Başlat", type="primary", use_container_width=True)
        verify_api = st.button("API Durumunu Kontrol Et", use_container_width=True)

    if verify_api:
        try:
            account = signed_account()
            st.success(f"Binance API doğrulandı. canTrade={account.get('canTrade')}")
        except Exception as exc:
            st.error(format_exception(exc))

    st.subheader("Aktif Algoritmalar")
    if selected_algorithms:
        st.write(" • ".join(STRATEGY_SPECS[key]["label"] for key in selected_algorithms))
    else:
        st.warning("Hiç algoritma seçilmediği için varsayılan olarak mevcut kural tabanlı strateji kullanılacak.")

    if start_scan:
        status = st.empty()
        progress = st.progress(0)

        def progress_callback(index: int, total: int, symbol: str):
            progress.progress(index / max(total, 1), text=f"{symbol} taranıyor ({index}/{total})")
            status.info(f"Veri indiriliyor: {symbol}")

        config = ScanConfig(
            interval=interval,
            candles=candles,
            market_limit=market_limit,
            min_volume=min_volume,
            min_range=min_range,
            cooldown_hours=24.0,
            symbol_delay=0.2,
            state_file="signal_state.json",
            send_digest=False,
            top_recommendations=5,
            digest_cooldown_hours=6.0,
            enabled_algorithms=tuple(selected_algorithms) if selected_algorithms else ("rule_based",),
            enable_dl=enable_dl,
            ensemble_threshold=ensemble_threshold,
            allow_telegram=allow_telegram,
        )
        try:
            with st.spinner("Binance piyasası taranıyor..."):
                signals, diagnostics = scan_once(config, progress_callback=progress_callback, emit_logs=False)
            st.session_state["scan_result"] = {"signals": signals, "diagnostics": diagnostics, "config": config}
            status.success(f"Tarama tamamlandı. Güçlü aday: {len(signals)}")
            progress.empty()
        except Exception as exc:
            status.error(format_exception(exc))
            st.session_state["scan_result"] = {"signals": [], "diagnostics": [format_exception(exc)], "config": config}

    result = st.session_state.get("scan_result")
    if not result:
        st.info("Tarama başlatıldığında sonuçlar burada görünecek.")
        return

    signals = result["signals"]
    diagnostics = result["diagnostics"]
    config = result["config"]

    left, middle, right = st.columns(3)
    left.metric("Sinyal adedi", len(signals))
    middle.metric("Aktif algoritma", len(config.enabled_algorithms))
    right.metric("DL durumu", "Açık" if config.enable_dl else "Kapalı")

    st.subheader("En Güçlü Adaylar")
    if not signals:
        st.warning("Seçilen eşiklerde uygun aday bulunamadı.")
    else:
        rows = [{
            "Parite": item["symbol"],
            "Ensemble": item["score"],
            "Uyum %": round(item["agreement"] * 100, 1),
            "RSI": round(item["rsi"], 1),
            "ADX": round(item["adx"], 1),
            "ATR %": round(item["atr_pct"], 2),
            "Hacim x": round(item["volume_ratio"], 2),
            "DL": item["dl"].backend if item["dl"].available else item["dl"].summary,
        } for item in signals]
        st.dataframe(rows, use_container_width=True)
        for item in signals[:8]:
            with st.expander(f"{item['symbol']} — {item['score']}/100"):
                st.write(
                    f"Stop: `{item['stop']:.10g}` | Hedef1: `{item['target1']:.10g}` | "
                    f"Hedef2: `{item['target2']:.10g}`"
                )
                st.write("Aktif stratejiler: " + ", ".join(item["active_algorithms"]))
                st.write("DL: " + item["dl"].summary)
                strategy_table = [{
                    "Strateji": strategy.label,
                    "Skor": round(strategy.score, 2),
                    "Durum": "AL" if strategy.bullish else "BEKLE",
                    "Özet": strategy.summary,
                } for strategy in item["strategies"]]
                st.table(strategy_table)
                if item["votes"]:
                    st.json(item["votes"])

    with st.expander("Tanı / Diagnostik", expanded=bool(diagnostics)):
        if diagnostics:
            for message in diagnostics:
                st.warning(message)
        else:
            st.success("Son taramada kritik hata gözlenmedi.")
        st.caption("HTTP 451: bölgesel erişim, eksik env değişkenleri ve ağ sorunları burada kısa mesajlarla görünür.")


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binance 10.000 mum + Telegram uzun vade tarayıcı")
    parser.add_argument("--interval", choices=["15m", "30m", "1h", "4h", "1d"], default="1h")
    parser.add_argument("--candles", type=int, default=10_000)
    parser.add_argument("--market-limit", type=int, default=12, help="Taranacak en oynak parite sayısı")
    parser.add_argument("--min-volume", type=float, default=20_000_000, help="Asgari 24s USDT hacmi")
    parser.add_argument("--min-range", type=float, default=5.0, help="Asgari 24s fiyat aralığı yüzdesi")
    parser.add_argument("--loop-minutes", type=int, default=0, help="0: bir kez; pozitif: sürekli çalış")
    parser.add_argument("--cooldown-hours", type=float, default=24.0)
    parser.add_argument("--symbol-delay", type=float, default=0.5)
    parser.add_argument("--state-file", default="signal_state.json")
    parser.add_argument("--account-check", action="store_true")
    parser.add_argument("--telegram-test", action="store_true")
    parser.add_argument("--send-digest", action="store_true", help="En iyi coinleri sıralı Telegram özetiyle gönder")
    parser.add_argument("--top-recommendations", type=int, default=5)
    parser.add_argument("--digest-cooldown-hours", type=float, default=6.0)
    parser.add_argument("--algorithms", default="rule_based", help="Virgülle ayrılmış algoritmalar veya 'all'")
    parser.add_argument("--enable-dl", action="store_true", help="Opsiyonel DL filtresini aç")
    parser.add_argument("--ensemble-threshold", type=float, default=72.0)
    return parser


def main():
    parser = build_cli_parser()
    args = parser.parse_args()
    args.candles = max(500, min(args.candles, 10_000))

    if args.account_check:
        account = signed_account()
        print("Binance API doğrulandı. Hesap işlem izni:", account.get("canTrade"))
    if args.telegram_test:
        telegram_send("✅ Binance sinyal servisi Telegram bağlantı testi başarılı.")
        print("Telegram test mesajı gönderildi.")
        if args.loop_minutes == 0:
            return

    config = ScanConfig(
        interval=args.interval,
        candles=args.candles,
        market_limit=args.market_limit,
        min_volume=args.min_volume,
        min_range=args.min_range,
        cooldown_hours=args.cooldown_hours,
        symbol_delay=args.symbol_delay,
        state_file=args.state_file,
        send_digest=args.send_digest,
        top_recommendations=args.top_recommendations,
        digest_cooldown_hours=args.digest_cooldown_hours,
        enabled_algorithms=parse_algorithm_selection(args.algorithms),
        enable_dl=args.enable_dl,
        ensemble_threshold=args.ensemble_threshold,
        allow_telegram=True,
    )

    while True:
        signals, diagnostics = scan_once(config)
        print(f"Tarama tamamlandı. Güçlü sinyal sayısı: {len(signals)}")
        for line in diagnostics:
            print("Tanı:", line)
        if args.loop_minutes <= 0:
            break
        time.sleep(max(1, args.loop_minutes) * 60)


if __name__ == "__main__":
    if is_running_in_streamlit():
        render_streamlit_app()
    else:
        main()
