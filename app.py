# -*- coding: utf-8 -*-
"""
Enterprise Binance Multi-Strategy + Optional AI/DL Streamlit Panel (single-file)
451-safe edition: Futures blocked regions auto fallback to Spot-only signal mode.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import os
import time
import json
import math
import hmac
import html
import hashlib
import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from datetime import datetime
from functools import lru_cache
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import pandas as pd
import streamlit as st


# ==========================
# 0) LOGGING / ENV
# ==========================

def load_dotenv(path: str = ".env") -> None:
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except FileNotFoundError:
        pass


load_dotenv()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("enterprise_binance_panel")


# ==========================
# 1) CONFIG
# ==========================

@dataclass(frozen=True)
class Settings:
    symbols: tuple[str, ...]
    min_base_checks: int = 6
    min_confidence: int = 70
    min_quality_checks: int = 3
    min_total_features: int = 14

    max_spread_bps: float = 2.0
    volume_multiplier: float = 1.3
    breakout_lookback: int = 20
    imbalance_threshold: float = 0.08
    taker_ratio_threshold: float = 0.54
    oi_change_threshold_pct: float = 0.02

    max_vwap_deviation_bps: float = 35.0
    max_zscore: float = 2.5
    max_ema_distance_atr: float = 2.0
    min_atr_bps: float = 1.0
    max_atr_bps: float = 60.0

    min_trend_strength_atr: float = 0.15
    min_bollinger_width_bps: float = 4.0
    max_bollinger_width_bps: float = 150.0
    min_candle_body_ratio: float = 0.45

    max_entry_slippage_bps: float = 5.0


# ==========================
# 2) INDICATORS
# ==========================

def ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(alpha * float(v) + (1.0 - alpha) * out[-1])
    return out


def rsi(values: Sequence[float], period: int = 7) -> list[float]:
    if len(values) < 2:
        return [50.0] * len(values)
    gains = [0.0]
    losses = [0.0]
    for p, c in zip(values, values[1:]):
        d = c - p
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = ema(gains, period)
    al = ema(losses, period)
    out = []
    for g, l in zip(ag, al):
        if l == 0:
            out.append(100.0 if g > 0 else 50.0)
        else:
            out.append(100.0 - 100.0 / (1.0 + g / l))
    return out


def macd_hist(values: Sequence[float]) -> list[float]:
    f = ema(values, 12)
    s = ema(values, 26)
    line = [a - b for a, b in zip(f, s)]
    sig = ema(line, 9)
    return [a - b for a, b in zip(line, sig)]


def mean_std(values: Sequence[float], period: int = 20) -> tuple[float, float]:
    w = list(values[-period:])
    if not w:
        return 0.0, 0.0
    m = sum(w) / len(w)
    var = sum((x - m) ** 2 for x in w) / len(w)
    return m, math.sqrt(var)


def zscore(values: Sequence[float], period: int = 20) -> float:
    if not values:
        return 0.0
    m, s = mean_std(values, period)
    return (values[-1] - m) / s if s > 0 else 0.0


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
    if not closes:
        return 0.0
    tr = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return ema(tr, period)[-1]


def rolling_vwap(highs, lows, closes, volumes, period=20) -> float:
    if not closes:
        return 0.0
    s = max(0, len(closes) - period)
    vol = sum(volumes[s:])
    if vol <= 0:
        return closes[-1]
    num = sum(((h + l + c) / 3.0) * v for h, l, c, v in zip(highs[s:], lows[s:], closes[s:], volumes[s:]))
    return num / vol


# ==========================
# 3) DOMAIN MODELS
# ==========================

@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    taker_buy_volume: float


@dataclass(frozen=True)
class Microstructure:
    bid: float = 0.0
    ask: float = 0.0
    imbalance: float = 0.0
    oi_change_pct: float | None = None

    @property
    def spread_bps(self) -> float:
        mid = (self.bid + self.ask) / 2.0
        return ((self.ask - self.bid) / mid * 10000.0) if mid > 0 else float("inf")


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str
    confidence: int
    base_passed: int
    quality_passed: int
    total_passed: int
    entry: float
    tp1: float
    tp2: float
    stop: float
    spread_bps: float
    imbalance: float
    taker_ratio: float
    oi_change_pct: float | None
    vwap_deviation_bps: float
    ema_distance_atr: float
    price_zscore: float
    atr_bps: float
    trend_strength_atr: float
    bollinger_width_bps: float
    candle_body_ratio: float
    checks: dict[str, bool]
    quality_checks: dict[str, bool]
    structure_checks: dict[str, bool]
    strategy_votes: dict[str, float]


# ==========================
# 4) REST LAYER
# ==========================

REST = os.getenv("BINANCE_FUTURES_REST", "https://fapi.binance.com")
SPOT_REST = os.getenv("BINANCE_SPOT_REST", "https://data-api.binance.vision")


def get_json(path: str, params: dict, timeout: float = 12.0, base: str = REST):
    url = f"{base}{path}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "enterprise-binance-panel/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _is_451(exc: Exception) -> bool:
    return isinstance(exc, HTTPError) and exc.code == 451


def is_restricted_location_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("http 451" in msg) or ("restricted location" in msg) or ("eligibility" in msg)


def futures_probe(base_url: str) -> tuple[bool, str]:
    try:
        req = Request(f"{base_url}/fapi/v1/time", headers={"User-Agent": "probe/1.0"})
        with urlopen(req, timeout=8) as r:
            if r.status >= 400:
                return False, f"HTTP {r.status}"
        return True, "OK"
    except Exception as exc:
        if is_restricted_location_error(exc):
            return False, "HTTP 451 restricted location"
        return False, str(exc)


def klines(symbol: str, interval: str, limit: int = 250) -> list[Candle]:
    p = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        rows = get_json("/fapi/v1/klines", p)
    except HTTPError as exc:
        if not _is_451(exc):
            raise
        rows = get_json("/api/v3/klines", p, base=SPOT_REST)
    return [Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9])) for r in rows[:-1]]


def market_snapshot(symbol: str, previous_oi: float | None = None) -> tuple[Microstructure, float | None]:
    try:
        depth = get_json("/fapi/v1/depth", {"symbol": symbol, "limit": 20})
        ticker = get_json("/fapi/v1/ticker/bookTicker", {"symbol": symbol})
        oi_payload = get_json("/fapi/v1/openInterest", {"symbol": symbol})
        current_oi = float(oi_payload["openInterest"])
    except HTTPError as exc:
        if not _is_451(exc):
            raise
        depth = get_json("/api/v3/depth", {"symbol": symbol, "limit": 20}, base=SPOT_REST)
        ticker = get_json("/api/v3/ticker/bookTicker", {"symbol": symbol}, base=SPOT_REST)
        current_oi = None

    bid_qty = sum(float(x[1]) for x in depth["bids"])
    ask_qty = sum(float(x[1]) for x in depth["asks"])
    tot = bid_qty + ask_qty
    imbalance = (bid_qty - ask_qty) / tot if tot else 0.0
    oi_change = ((current_oi / previous_oi) - 1.0) * 100.0 if (current_oi and previous_oi) else None
    return Microstructure(float(ticker["bidPrice"]), float(ticker["askPrice"]), imbalance, oi_change), current_oi


@st.cache_data(ttl=1800, show_spinner=False)
def active_usdt_symbols() -> tuple[list[str], str]:
    try:
        exchange = get_json("/fapi/v1/exchangeInfo", {})
        active = {
            s["symbol"] for s in exchange.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT"
        }
        tickers = get_json("/fapi/v1/ticker/24hr", {})
        source = "USDⓈ-M Futures"
    except HTTPError as exc:
        if not _is_451(exc):
            raise
        exchange = get_json("/api/v3/exchangeInfo", {}, base=SPOT_REST)
        active = {
            s["symbol"] for s in exchange.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT" and s.get("isSpotTradingAllowed", True)
        }
        tickers = get_json("/api/v3/ticker/24hr", {}, base=SPOT_REST)
        source = "Spot fallback (Futures HTTP 451)"

    vols = {x["symbol"]: float(x.get("quoteVolume", 0)) for x in tickers if x.get("symbol") in active}
    return sorted(active, key=lambda s: vols.get(s, 0.0), reverse=True), source


@lru_cache(maxsize=2048)
def binance_all_time_low(symbol: str) -> tuple[float, int]:
    path, base = "/fapi/v1/klines", REST
    start = 0
    low = float("inf")
    low_t = 0
    for _ in range(12):
        lim = 1500 if base == REST else 1000
        p = {"symbol": symbol, "interval": "1d", "limit": lim, "startTime": start}
        try:
            rows = get_json(path, p, timeout=15, base=base)
        except HTTPError as exc:
            if base != REST or not _is_451(exc):
                raise
            path, base = "/api/v3/klines", SPOT_REST
            start = 0
            p["limit"] = 1000
            rows = get_json(path, p, timeout=15, base=base)
        if not rows:
            break
        for r in rows:
            v = float(r[3])
            if v < low:
                low = v
                low_t = int(r[0])
        if len(rows) < lim:
            break
        nxt = int(rows[-1][0]) + 1
        if nxt <= start:
            break
        start = nxt
    if low == float("inf"):
        raise RuntimeError(f"{symbol} için ATL bulunamadı")
    return low, low_t


# ==========================
# 5) STRATEGY ENGINE
# ==========================

def evaluate_symbol(symbol: str, one: list[Candle], five: list[Candle], micro: Microstructure, cfg: Settings,
                    enabled: dict[str, bool], dl_bonus: float = 0.0) -> dict[str, Signal]:
    if len(one) < max(55, cfg.breakout_lookback + 2) or len(five) < 55:
        return {}

    closes = [c.close for c in one]
    highs = [c.high for c in one]
    lows = [c.low for c in one]
    vols = [c.volume for c in one]
    five_closes = [c.close for c in five]
    entry = closes[-1]

    ema20_1m = ema(closes, 20)[-1]
    ema20_1m_series = ema(closes, 20)
    ema20_5m = ema(five_closes, 20)[-1]
    ema50_5m = ema(five_closes, 50)[-1]
    rsi7 = rsi(closes, 7)[-1]
    hist = macd_hist(closes)
    vwap = rolling_vwap(highs, lows, closes, vols, 20)
    atrv = atr(highs, lows, closes, 14)

    vwap_dev = (entry / vwap - 1.0) * 10000.0 if vwap else 0.0
    ema_dist_atr = abs(entry - ema20_1m) / atrv if atrv > 0 else float("inf")
    z = zscore(closes, 20)
    atr_bps = atrv / entry * 10000.0 if entry > 0 else float("inf")

    five_atr = atr([c.high for c in five], [c.low for c in five], five_closes, 14)
    trend_strength = abs(ema20_5m - ema50_5m) / five_atr if five_atr > 0 else 0.0
    _, pstd = mean_std(closes, 20)
    bb_width_bps = (4.0 * pstd / entry * 10000.0) if entry > 0 else 0.0

    candle_range = one[-1].high - one[-1].low
    candle_body_ratio = abs(one[-1].close - one[-1].open) / candle_range if candle_range > 0 else 0.0

    quality_checks = {
        "VWAP Sapması": abs(vwap_dev) <= cfg.max_vwap_deviation_bps,
        "EMA/ATR Mesafesi": ema_dist_atr <= cfg.max_ema_distance_atr,
        "Z-Score": abs(z) <= cfg.max_zscore,
        "Volatilite Rejimi": cfg.min_atr_bps <= atr_bps <= cfg.max_atr_bps,
    }
    quality_passed = sum(quality_checks.values())

    mean_vol = sum(vols[-21:-1]) / 20.0
    ph = max(highs[-cfg.breakout_lookback - 1:-1])
    pl = min(lows[-cfg.breakout_lookback - 1:-1])
    spread_ok = micro.spread_bps <= cfg.max_spread_bps
    taker_ratio = one[-1].taker_buy_volume / one[-1].volume if one[-1].volume > 0 else 0.5
    oi_ok = micro.oi_change_pct is not None and micro.oi_change_pct >= cfg.oi_change_threshold_pct

    out: dict[str, Signal] = {}
    for side in ("LONG", "SHORT"):
        if side == "LONG":
            base = {
                "5M Trend": ema20_5m > ema50_5m,
                "EMA20": entry > ema20_1m,
                "RSI": 50 <= rsi7 <= 70,
                "MACD": hist[-1] > 0 and hist[-1] > hist[-2],
                "Volume": vols[-1] > mean_vol * cfg.volume_multiplier,
                "VWAP": entry > vwap,
                "Breakout": entry > ph,
                "Spread": spread_ok,
            }
            orderbook_ok = micro.imbalance >= cfg.imbalance_threshold
            taker_ok = taker_ratio >= cfg.taker_ratio_threshold
            structure = {
                "Trend Gücü": trend_strength >= cfg.min_trend_strength_atr,
                "EMA Eğimi": ema20_1m_series[-1] > ema20_1m_series[-4],
                "BB Genişliği": cfg.min_bollinger_width_bps <= bb_width_bps <= cfg.max_bollinger_width_bps,
                "Mum Gövdesi": one[-1].close > one[-1].open and candle_body_ratio >= cfg.min_candle_body_ratio,
                "Kısa Momentum": sum(closes[i] > closes[i - 1] for i in range(len(closes) - 3, len(closes))) >= 2,
            }
            stop, tp1, tp2 = entry - 0.8 * atrv, entry + 0.8 * atrv, entry + 1.2 * atrv
        else:
            base = {
                "5M Trend": ema20_5m < ema50_5m,
                "EMA20": entry < ema20_1m,
                "RSI": 30 <= rsi7 <= 50,
                "MACD": hist[-1] < 0 and hist[-1] < hist[-2],
                "Volume": vols[-1] > mean_vol * cfg.volume_multiplier,
                "VWAP": entry < vwap,
                "Breakout": entry < pl,
                "Spread": spread_ok,
            }
            orderbook_ok = micro.imbalance <= -cfg.imbalance_threshold
            taker_ok = taker_ratio <= (1.0 - cfg.taker_ratio_threshold)
            structure = {
                "Trend Gücü": trend_strength >= cfg.min_trend_strength_atr,
                "EMA Eğimi": ema20_1m_series[-1] < ema20_1m_series[-4],
                "BB Genişliği": cfg.min_bollinger_width_bps <= bb_width_bps <= cfg.max_bollinger_width_bps,
                "Mum Gövdesi": one[-1].close < one[-1].open and candle_body_ratio >= cfg.min_candle_body_ratio,
                "Kısa Momentum": sum(closes[i] < closes[i - 1] for i in range(len(closes) - 3, len(closes))) >= 2,
            }
            stop, tp1, tp2 = entry + 0.8 * atrv, entry - 0.8 * atrv, entry - 1.2 * atrv

        micro_checks = {"OrderBook": orderbook_ok, "Taker": taker_ok, "OI": oi_ok}
        all_features = {**base, **quality_checks, **structure, **micro_checks}
        base_passed = sum(base.values())
        total_passed = sum(all_features.values())

        votes = {}
        if enabled.get("trend_follow", True):
            votes["trend_follow"] = 1.0 if ((side == "LONG" and ema20_5m > ema50_5m) or (side == "SHORT" and ema20_5m < ema50_5m)) else 0.0
        if enabled.get("breakout", True):
            votes["breakout"] = 1.0 if base["Breakout"] and base["Volume"] else 0.0
        if enabled.get("mean_reversion", True):
            votes["mean_reversion"] = 1.0 if ((side == "LONG" and z < -1.2) or (side == "SHORT" and z > 1.2)) else 0.0
        if enabled.get("microstructure", True):
            votes["microstructure"] = (float(orderbook_ok) + float(taker_ok) + (1.0 if oi_ok else 0.5)) / 3.0
        if enabled.get("quality_gate", True):
            votes["quality_gate"] = quality_passed / 4.0

        weights = {
            "trend_follow": 0.24,
            "breakout": 0.22,
            "mean_reversion": 0.14,
            "microstructure": 0.22,
            "quality_gate": 0.18,
        }
        vote_score = sum(votes.get(k, 0.0) * weights[k] for k in weights)

        confidence = round(
            base_passed * 5.0
            + quality_passed * 7.5
            + (float(orderbook_ok) + float(taker_ok) + (1.0 if oi_ok else 0.5)) * (20.0 / 3.0)
            + sum(structure.values()) * 2.0
            + vote_score * 10.0
            + dl_bonus
        )
        confidence = max(0, min(confidence, 100))

        out[side] = Signal(
            symbol=symbol,
            side=side,
            confidence=confidence,
            base_passed=base_passed,
            quality_passed=quality_passed,
            total_passed=total_passed,
            entry=entry,
            tp1=tp1,
            tp2=tp2,
            stop=stop,
            spread_bps=micro.spread_bps,
            imbalance=micro.imbalance,
            taker_ratio=taker_ratio,
            oi_change_pct=micro.oi_change_pct,
            vwap_deviation_bps=vwap_dev,
            ema_distance_atr=ema_dist_atr,
            price_zscore=z,
            atr_bps=atr_bps,
            trend_strength_atr=trend_strength,
            bollinger_width_bps=bb_width_bps,
            candle_body_ratio=candle_body_ratio,
            checks=base,
            quality_checks=quality_checks,
            structure_checks=structure,
            strategy_votes=votes,
        )
    return out


# ==========================
# 6) OPTIONAL DL
# ==========================

def dl_predict_bonus(closes: list[float], side: str, enabled: bool) -> tuple[float, str]:
    if not enabled:
        return 0.0, "DL pasif"
    try:
        import numpy as np  # type: ignore

        if len(closes) < 80:
            return 0.0, "DL: yetersiz veri"

        rets = np.diff(np.array(closes[-61:], dtype=float)) / np.array(closes[-61:-1], dtype=float)
        momentum = float(np.mean(rets[-8:]))
        volatility = float(np.std(rets))
        raw = (momentum / (volatility + 1e-9)) * 0.6 + (np.sum(rets[-3:]) * 10.0) * 0.4

        if side == "LONG":
            prob = 1.0 / (1.0 + math.exp(-raw))
        else:
            prob = 1.0 / (1.0 + math.exp(raw))

        bonus = max(0.0, min(8.0, (prob - 0.5) * 16.0))
        return float(bonus), f"DL aktif (bonus={bonus:.2f})"
    except Exception as exc:
        return 0.0, f"DL fallback: {exc}"


# ==========================
# 7) TELEGRAM
# ==========================

def send_telegram(token: str, chat_id: str, text: str) -> None:
    data = urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urlopen(req, timeout=10) as r:
        if r.status >= 400:
            raise RuntimeError(f"Telegram HTTP {r.status}")


def format_signal(sig: Signal) -> str:
    strength = "🔥 VERY STRONG" if sig.confidence >= 90 else "🟢 STRONG" if sig.confidence >= 80 else "🟢 SIGNAL"
    checks = "\n".join(f"{html.escape(k):14} {'✅' if v else '❌'}" for k, v in sig.checks.items())
    q = "\n".join(f"{html.escape(k):18} {'✅' if v else '❌'}" for k, v in sig.quality_checks.items())
    oi = "warming up" if sig.oi_change_pct is None else f"{sig.oi_change_pct:+.3f}%"
    return (
        f"<b>{strength}</b>\n\n"
        f"<b>{sig.symbol} — {sig.side}</b>\n"
        f"Confidence: <b>{sig.confidence}/100</b>\n"
        f"20 özellik: <b>{sig.total_passed}/20</b>\n\n"
        f"<pre>{checks}</pre>\n"
        f"<b>Kalite ({sig.quality_passed}/4)</b>\n<pre>{q}</pre>\n"
        f"VWAP Δ: {sig.vwap_deviation_bps:+.2f} bps\n"
        f"Z: {sig.price_zscore:+.2f} | ATR: {sig.atr_bps:.2f} bps\n"
        f"Spread: {sig.spread_bps:.2f} bps | OI: {oi}\n"
        f"TP1: <code>{sig.tp1:.4f}</code> TP2: <code>{sig.tp2:.4f}</code> SL: <code>{sig.stop:.4f}</code>\n"
        f"<i>Yatırım tavsiyesi değildir.</i>"
    )


# ==========================
# 8) TRADING (FUTURES)
# ==========================

LIVE_BASE = os.getenv("BINANCE_FUTURES_LIVE_REST", "https://fapi.binance.com")
TESTNET_BASE = os.getenv("BINANCE_FUTURES_TESTNET_REST", "https://demo-fapi.binance.com")


class BinanceAPIError(RuntimeError):
    pass


def floor_step(value: float | Decimal, step: str | Decimal) -> Decimal:
    v, s = Decimal(str(value)), Decimal(str(step))
    return (v / s).to_integral_value(rounding=ROUND_DOWN) * s


def trigger_price(value: float | Decimal, tick: str | Decimal, *, up: bool) -> Decimal:
    v, t = Decimal(str(value)), Decimal(str(tick))
    rnd = ROUND_UP if up else ROUND_DOWN
    return (v / t).to_integral_value(rounding=rnd) * t


def dec_text(v: Decimal) -> str:
    return format(v, "f")


@dataclass(frozen=True)
class SymbolRules:
    step_size: str
    tick_size: str
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal


class FuturesClient:
    def __init__(self, api_key: str, api_secret: str, testnet=True, timeout=10.0) -> None:
        if not api_key or not api_secret:
            raise ValueError("API key/secret gerekli")
        self.api_key = api_key
        self.secret = api_secret.encode()
        self.base = TESTNET_BASE if testnet else LIVE_BASE
        self.timeout = timeout
        self.time_offset = 0

    def _request(self, method: str, path: str, params: dict | None = None, signed=False):
        values = {k: v for k, v in (params or {}).items() if v is not None}
        if signed:
            values["timestamp"] = int(time.time() * 1000) + self.time_offset
            values["recvWindow"] = 5000
        q = urlencode(values)
        if signed:
            sig = hmac.new(self.secret, q.encode(), hashlib.sha256).hexdigest()
            q = f"{q}&signature={sig}"
        url = f"{self.base}{path}"
        data = q.encode() if method in {"POST", "PUT", "DELETE"} else None
        if method == "GET" and q:
            url = f"{url}?{q}"

        req = Request(url, data=data, method=method, headers={
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                p = json.loads(body)
                detail = f"{p.get('code')}: {p.get('msg')}"
            except Exception:
                detail = body[:300]
            raise BinanceAPIError(f"Binance HTTP {exc.code} — {detail}") from exc
        except URLError as exc:
            raise BinanceAPIError(f"Ağ hatası: {exc}") from exc

    def sync_time(self):
        p = self._request("GET", "/fapi/v1/time")
        self.time_offset = int(p["serverTime"]) - int(time.time() * 1000)

    def account_balance(self) -> dict[str, float]:
        self.sync_time()
        rows = self._request("GET", "/fapi/v3/balance", signed=True)
        return {r["asset"]: float(r["availableBalance"]) for r in rows}


# ==========================
# 9) STREAMLIT UI
# ==========================

st.set_page_config(page_title="Enterprise Binance AI Radar", page_icon="⚡", layout="wide")

st.title("⚡ Enterprise Binance AI Radar")
st.caption("451-safe sürüm: Futures engelinde Spot-only sinyal moduna geçer.")

with st.sidebar:
    st.header("Ayarlar")
    try:
        all_symbols, source = active_usdt_symbols()
    except Exception as e:
        st.warning(f"Parite kataloğu alınamadı: {e}")
        all_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
        source = "Temel liste"

    symbol = st.selectbox("Detay paritesi", all_symbols, index=0)
    scan_all = st.toggle("Tüm piyasayı tara", True)
    batch_size = st.slider("Her tur coin", 5, 20, 10, 1)
    refresh = st.slider("Yenileme (sn)", 5, 60, 15, 1)
    live = st.toggle("Canlı yenileme", True)

    st.subheader("Sinyal Eşikleri")
    min_checks = st.slider("Min teknik check", 1, 8, 6)
    min_conf = st.slider("Min skor", 0, 100, 70)
    min_q = st.slider("Min kalite", 0, 4, 3)
    min_total = st.slider("Min toplam özellik", 0, 20, 14)

    st.subheader("Algoritmalar")
    alg_trend = st.toggle("Trend Follow", True)
    alg_breakout = st.toggle("Breakout", True)
    alg_mr = st.toggle("Mean Reversion", True)
    alg_micro = st.toggle("Microstructure", True)
    alg_quality = st.toggle("Quality Gate", True)

    st.subheader("AI / DL")
    dl_enabled = st.toggle("Deep Learning filtresi", False)

    st.subheader("Telegram")
    tg_token = st.text_input("Bot token", os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
    tg_chat = st.text_input("Chat ID", os.getenv("TELEGRAM_CHAT_ID", ""))
    auto_send = st.toggle("Uygun sinyali otomatik gönder", False)

    st.subheader("Trade")
    trading_enabled = st.toggle("Trade modu", False)
    env = st.radio("Ortam", ["TESTNET", "LIVE"], horizontal=True)
    key = st.text_input("API key", os.getenv("BINANCE_API_KEY", ""), type="password")
    sec = st.text_input("API secret", os.getenv("BINANCE_API_SECRET", ""), type="password")

    probe_base = TESTNET_BASE if env == "TESTNET" else LIVE_BASE
    probe_ok, probe_msg = futures_probe(probe_base)

    futures_blocked = (not probe_ok and "451" in probe_msg) or ("Spot fallback" in source)

    if futures_blocked:
        st.error("🚫 Futures bu IP/ortamda kullanılamıyor (HTTP 451). Spot-only mode aktif.")
        trading_enabled = False
    else:
        st.success(f"Futures endpoint: {probe_msg}")

    if st.button("API Test"):
        try:
            c = FuturesClient(key, sec, testnet=(env == "TESTNET"))
            bal = c.account_balance()
            st.success(f"USDT: {bal.get('USDT', 0):,.2f}")
        except Exception as e:
            if is_restricted_location_error(e):
                st.error("Binance Futures HTTP 451: API key doğru olsa bile erişim reddediliyor.")
            else:
                st.error(f"API test hata: {e}")

cfg = Settings(
    symbols=(symbol,),
    min_base_checks=min_checks,
    min_confidence=min_conf,
    min_quality_checks=min_q,
    min_total_features=min_total,
)

enabled_algorithms = {
    "trend_follow": alg_trend,
    "breakout": alg_breakout,
    "mean_reversion": alg_mr,
    "microstructure": alg_micro,
    "quality_gate": alg_quality,
}

if "oi" not in st.session_state:
    st.session_state.oi = {}
if "sent" not in st.session_state:
    st.session_state.sent = set()
if "scan_offset" not in st.session_state:
    st.session_state.scan_offset = 0


def scan_symbol(s: str):
    one = klines(s, "1m")
    five = klines(s, "5m")
    h1 = klines(s, "1h", 73)
    micro, cur_oi = market_snapshot(s, st.session_state.oi.get(s))
    drawdown = (one[-1].close / max(c.high for c in h1) - 1.0) * 100.0 if h1 else 0.0
    atl, atl_t = binance_all_time_low(s)
    atl_dist = (one[-1].close / atl - 1.0) * 100.0 if atl > 0 else float("inf")
    dl_long_bonus, dl_state_l = dl_predict_bonus([c.close for c in one], "LONG", dl_enabled)
    dl_short_bonus, dl_state_s = dl_predict_bonus([c.close for c in one], "SHORT", dl_enabled)

    sig_long_short = evaluate_symbol(s, one, five, micro, cfg, enabled_algorithms, 0.0)
    if "LONG" in sig_long_short:
        sig = sig_long_short["LONG"]
        sig_long_short["LONG"] = Signal(**{**sig.__dict__, "confidence": max(0, min(100, sig.confidence + int(dl_long_bonus)))})
    if "SHORT" in sig_long_short:
        sig = sig_long_short["SHORT"]
        sig_long_short["SHORT"] = Signal(**{**sig.__dict__, "confidence": max(0, min(100, sig.confidence + int(dl_short_bonus)))})

    return one, five, micro, cur_oi, sig_long_short, drawdown, atl, atl_t, atl_dist, dl_state_l, dl_state_s


run_every = refresh if live else None


@st.fragment(run_every=run_every)
def dashboard():
    symbols = all_symbols
    if scan_all and symbols:
        off = st.session_state.scan_offset % len(symbols)
        radar = [symbols[(off + i) % len(symbols)] for i in range(min(batch_size, len(symbols)))]
    else:
        off = 0
        radar = [symbol]

    targets = list(dict.fromkeys([symbol, *radar]))
    packets, errors = {}, {}

    try:
        with ThreadPoolExecutor(max_workers=min(6, len(targets))) as ex:
            fmap = {ex.submit(scan_symbol, s): s for s in targets}
            for f in as_completed(fmap):
                s = fmap[f]
                try:
                    packets[s] = f.result()
                except Exception as e:
                    errors[s] = str(e)

        if symbol not in packets:
            raise RuntimeError(errors.get(symbol, "Seçili sembol verisi yok"))

        one, _, micro, _, sigs, _, _, _, _, dl_l, dl_s = packets[symbol]
        for s, p in packets.items():
            st.session_state.oi[s] = p[3]

    except Exception as e:
        logger.exception("Dashboard error")
        st.error(f"Veri alınamadı: {e}")
        if errors:
            st.json(errors)
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Son fiyat", f"{one[-1].close:,.4f}")
    c2.metric("Spread", f"{micro.spread_bps:.2f} bps")
    c3.metric("OI", "N/A" if micro.oi_change_pct is None else f"{micro.oi_change_pct:+.4f}%")
    c4.metric("Güncelleme", datetime.now().strftime("%H:%M:%S"))

    st.caption(f"AI Katmanı: LONG={dl_l} | SHORT={dl_s}")
    st.caption("Aktif algoritmalar: " + ", ".join([k for k, v in enabled_algorithms.items() if v]))

    chart = pd.DataFrame({"Fiyat": [c.close for c in one[-120:]]}, index=pd.to_datetime([c.open_time for c in one[-120:]], unit="ms"))
    st.line_chart(chart, height=260)

    tab1, tab2 = st.tabs(["LONG", "SHORT"])
    eligible_signals = []

    for tab, side in [(tab1, "LONG"), (tab2, "SHORT")]:
        with tab:
            sig = sigs.get(side)
            if not sig:
                st.warning("Yeterli veri yok")
                continue
            eligible = (
                sig.base_passed >= cfg.min_base_checks
                and sig.quality_passed >= cfg.min_quality_checks
                and sig.total_passed >= cfg.min_total_features
                and sig.confidence >= cfg.min_confidence
            )
            if eligible:
                eligible_signals.append(sig)

            st.metric(f"{side} Skor", f"{sig.confidence}/100")
            st.write("Entry/TP/SL", {"entry": sig.entry, "tp1": sig.tp1, "tp2": sig.tp2, "sl": sig.stop})

            if st.button(f"{side} Telegram gönder", key=f"tg_{side}", disabled=not (tg_token and tg_chat)):
                try:
                    send_telegram(tg_token, tg_chat, format_signal(sig))
                    st.success("Telegram gönderildi")
                except Exception as e:
                    st.error(f"Telegram hata: {e}")

    if auto_send and eligible_signals and tg_token and tg_chat:
        best = max(eligible_signals, key=lambda x: x.confidence)
        key_candle = (best.symbol, best.side, one[-1].open_time)
        if key_candle not in st.session_state.sent:
            try:
                send_telegram(tg_token, tg_chat, format_signal(best))
                st.session_state.sent.add(key_candle)
                st.toast(f"Otomatik gönderildi: {best.symbol} {best.side}", icon="📨")
            except Exception as e:
                st.error(f"Otomatik telegram hata: {e}")

    if scan_all and all_symbols:
        st.session_state.scan_offset = (off + len(radar)) % len(all_symbols)

    if errors:
        with st.expander("Hata Teşhisleri"):
            st.json(errors)


try:
    dashboard()
except Exception as e:
    logger.exception("Fatal UI error")
    st.error(f"Panel beklenmeyen hatayla durdu: {e}")
    st.info("Yenileyin. Sorun sürerse API erişimi / internet / sembol listesini kontrol edin.")

st.caption("Yatırım tavsiyesi değildir.")
