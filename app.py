"""Binance Futures scalping botu — tek dosyalık Streamlit sürümü.

Başlatma: streamlit run scalping_bot_tek_dosya.py
Varsayılan TESTNET; LIVE modu açık onay gerektirir.
"""

from __future__ import annotations


# ==================== config.py ====================


import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    symbols: tuple[str, ...]
    telegram_token: str
    telegram_chat_id: str
    telegram_enabled: bool
    min_base_checks: int
    min_confidence: int
    cooldown_minutes: int
    max_spread_bps: float
    volume_multiplier: float
    breakout_lookback: int
    imbalance_threshold: float
    taker_ratio_threshold: float
    oi_change_threshold_pct: float
    min_quality_checks: int = 3
    max_vwap_deviation_bps: float = 35.0
    max_zscore: float = 2.5
    max_ema_distance_atr: float = 2.0
    min_atr_bps: float = 1.0
    max_atr_bps: float = 60.0
    max_entry_slippage_bps: float = 5.0
    min_total_features: int = 14
    min_trend_strength_atr: float = 0.15
    min_bollinger_width_bps: float = 4.0
    max_bollinger_width_bps: float = 150.0
    min_candle_body_ratio: float = 0.45
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        symbols = tuple(
            dict.fromkeys(
                item.strip().upper().replace("/", "")
                for item in os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
                if item.strip()
            )
        )
        settings = cls(
            symbols=symbols,
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            telegram_enabled=_bool("TELEGRAM_ENABLED", True),
            min_base_checks=int(os.getenv("MIN_BASE_CHECKS", "6")),
            min_confidence=int(os.getenv("MIN_CONFIDENCE", "70")),
            cooldown_minutes=int(os.getenv("COOLDOWN_MINUTES", "15")),
            max_spread_bps=float(os.getenv("MAX_SPREAD_BPS", "2.0")),
            volume_multiplier=float(os.getenv("VOLUME_MULTIPLIER", "1.3")),
            breakout_lookback=int(os.getenv("BREAKOUT_LOOKBACK", "20")),
            imbalance_threshold=float(os.getenv("ORDERBOOK_IMBALANCE_THRESHOLD", "0.08")),
            taker_ratio_threshold=float(os.getenv("TAKER_RATIO_THRESHOLD", "0.54")),
            oi_change_threshold_pct=float(os.getenv("OI_CHANGE_THRESHOLD_PCT", "0.02")),
            min_quality_checks=int(os.getenv("MIN_QUALITY_CHECKS", "3")),
            max_vwap_deviation_bps=float(os.getenv("MAX_VWAP_DEVIATION_BPS", "35")),
            max_zscore=float(os.getenv("MAX_ZSCORE", "2.5")),
            max_ema_distance_atr=float(os.getenv("MAX_EMA_DISTANCE_ATR", "2.0")),
            min_atr_bps=float(os.getenv("MIN_ATR_BPS", "1.0")),
            max_atr_bps=float(os.getenv("MAX_ATR_BPS", "60.0")),
            max_entry_slippage_bps=float(os.getenv("MAX_ENTRY_SLIPPAGE_BPS", "5.0")),
            min_total_features=int(os.getenv("MIN_TOTAL_FEATURES", "14")),
            min_trend_strength_atr=float(os.getenv("MIN_TREND_STRENGTH_ATR", "0.15")),
            min_bollinger_width_bps=float(os.getenv("MIN_BOLLINGER_WIDTH_BPS", "4.0")),
            max_bollinger_width_bps=float(os.getenv("MAX_BOLLINGER_WIDTH_BPS", "150.0")),
            min_candle_body_ratio=float(os.getenv("MIN_CANDLE_BODY_RATIO", "0.45")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
        if not settings.symbols:
            raise ValueError("SYMBOLS en az bir sembol içermeli")
        if not 1 <= settings.min_base_checks <= 8:
            raise ValueError("MIN_BASE_CHECKS 1 ile 8 arasında olmalı")
        if not 0 <= settings.min_confidence <= 100:
            raise ValueError("MIN_CONFIDENCE 0 ile 100 arasında olmalı")
        if not 0 <= settings.min_quality_checks <= 4:
            raise ValueError("MIN_QUALITY_CHECKS 0 ile 4 arasında olmalı")
        if settings.min_atr_bps >= settings.max_atr_bps:
            raise ValueError("MIN_ATR_BPS, MAX_ATR_BPS değerinden küçük olmalı")
        if not 0 <= settings.min_total_features <= 20:
            raise ValueError("MIN_TOTAL_FEATURES 0 ile 20 arasında olmalı")
        if settings.telegram_enabled and not (settings.telegram_token and settings.telegram_chat_id):
            raise ValueError("Telegram etkin: TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID gerekli")
        return settings


def load_dotenv(path: str = ".env") -> None:
    """Small dependency-free .env loader; existing environment always wins."""
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'") )
    except FileNotFoundError:
        pass


# ==================== indicators.py ====================


from collections.abc import Sequence
from math import sqrt


def ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1.0 - alpha) * out[-1])
    return out


def rsi(values: Sequence[float], period: int = 7) -> list[float]:
    if len(values) < 2:
        return [50.0] * len(values)
    gains = [0.0]
    losses = [0.0]
    for previous, current in zip(values, values[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = ema(gains, period)
    avg_loss = ema(losses, period)
    result = []
    for gain, loss in zip(avg_gain, avg_loss):
        if loss == 0:
            result.append(100.0 if gain > 0 else 50.0)
        else:
            result.append(100.0 - 100.0 / (1.0 + gain / loss))
    return result


def macd_histogram(values: Sequence[float]) -> list[float]:
    fast = ema(values, 12)
    slow = ema(values, 26)
    line = [a - b for a, b in zip(fast, slow)]
    signal = ema(line, 9)
    return [a - b for a, b in zip(line, signal)]


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
    if not closes:
        return 0.0
    true_ranges = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        true_ranges.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return ema(true_ranges, period)[-1]


def rolling_vwap(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], volumes: Sequence[float], period: int = 20) -> float:
    start = max(0, len(closes) - period)
    volume = sum(volumes[start:])
    if volume <= 0:
        return closes[-1]
    numerator = sum(((h + l + c) / 3.0) * v for h, l, c, v in zip(highs[start:], lows[start:], closes[start:], volumes[start:]))
    return numerator / volume


def mean_std(values: Sequence[float], period: int = 20) -> tuple[float, float]:
    window = list(values[-period:])
    if not window:
        return 0.0, 0.0
    mean = sum(window) / len(window)
    variance = sum((value - mean) ** 2 for value in window) / len(window)
    return mean, sqrt(variance)


def zscore(values: Sequence[float], period: int = 20) -> float:
    mean, std = mean_std(values, period)
    return (values[-1] - mean) / std if values and std > 0 else 0.0


# ==================== engine.py ====================


from dataclasses import dataclass
from typing import Literal



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
        return ((self.ask - self.bid) / mid * 10_000.0) if mid > 0 else float("inf")


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Literal["LONG", "SHORT"]
    confidence: int
    base_passed: int
    checks: dict[str, bool]
    entry: float
    tp1: float
    tp2: float
    stop: float
    atr: float
    spread_bps: float
    imbalance: float
    taker_ratio: float
    oi_change_pct: float | None
    quality_checks: dict[str, bool]
    quality_passed: int
    vwap_deviation_bps: float
    ema_distance_atr: float
    price_zscore: float
    atr_bps: float
    structure_checks: dict[str, bool]
    all_features: dict[str, bool]
    total_passed: int
    trend_strength_atr: float
    bollinger_width_bps: float
    candle_body_ratio: float


def _evaluate_side(symbol: str, side: Literal["LONG", "SHORT"], one: list[Candle], five: list[Candle], micro: Microstructure, cfg: Settings, require_gate: bool = True) -> Signal | None:
    if len(one) < max(55, cfg.breakout_lookback + 2) or len(five) < 55:
        return None
    closes = [c.close for c in one]
    highs = [c.high for c in one]
    lows = [c.low for c in one]
    volumes = [c.volume for c in one]
    five_closes = [c.close for c in five]
    entry = closes[-1]
    ema20_1m_series = ema(closes, 20)
    ema20_1m = ema20_1m_series[-1]
    ema20_5m_series = ema(five_closes, 20)
    ema20_5m = ema20_5m_series[-1]
    ema50_5m = ema(five_closes, 50)[-1]
    rsi7 = rsi(closes, 7)[-1]
    hist = macd_histogram(closes)
    vwap = rolling_vwap(highs, lows, closes, volumes, 20)
    current_atr = atr(highs, lows, closes, 14)
    vwap_deviation_bps = (entry / vwap - 1.0) * 10_000.0 if vwap else 0.0
    ema_distance_atr = abs(entry - ema20_1m) / current_atr if current_atr > 0 else float("inf")
    price_zscore = zscore(closes, 20)
    atr_bps = current_atr / entry * 10_000.0 if entry > 0 else float("inf")
    five_highs = [c.high for c in five]
    five_lows = [c.low for c in five]
    five_atr = atr(five_highs, five_lows, five_closes, 14)
    trend_strength_atr = abs(ema20_5m - ema50_5m) / five_atr if five_atr > 0 else 0.0
    _, price_std = mean_std(closes, 20)
    bollinger_width_bps = (4.0 * price_std / entry * 10_000.0) if entry > 0 else 0.0
    candle_range = one[-1].high - one[-1].low
    candle_body_ratio = abs(one[-1].close - one[-1].open) / candle_range if candle_range > 0 else 0.0
    quality_checks = {
        "VWAP Sapması": abs(vwap_deviation_bps) <= cfg.max_vwap_deviation_bps,
        "EMA/ATR Mesafesi": ema_distance_atr <= cfg.max_ema_distance_atr,
        "Z-Score": abs(price_zscore) <= cfg.max_zscore,
        "Volatilite Rejimi": cfg.min_atr_bps <= atr_bps <= cfg.max_atr_bps,
    }
    quality_passed = sum(quality_checks.values())
    mean_volume = sum(volumes[-21:-1]) / 20.0
    previous_high = max(highs[-cfg.breakout_lookback - 1:-1])
    previous_low = min(lows[-cfg.breakout_lookback - 1:-1])
    spread_ok = micro.spread_bps <= cfg.max_spread_bps
    if side == "LONG":
        checks = {
            "5M Trend": ema20_5m > ema50_5m,
            "EMA20": entry > ema20_1m,
            "RSI(7)": 50 <= rsi7 <= 70,
            "MACD": hist[-1] > 0 and hist[-1] > hist[-2],
            "Volume": volumes[-1] > mean_volume * cfg.volume_multiplier,
            "VWAP": entry > vwap,
            "Breakout": entry > previous_high,
            "Spread": spread_ok,
        }
        orderbook_ok = micro.imbalance >= cfg.imbalance_threshold
        taker_ratio = one[-1].taker_buy_volume / one[-1].volume if one[-1].volume > 0 else 0.5
        taker_ok = taker_ratio >= cfg.taker_ratio_threshold
        oi_ok = micro.oi_change_pct is not None and micro.oi_change_pct >= cfg.oi_change_threshold_pct
        structure_checks = {
            "Trend Gücü": trend_strength_atr >= cfg.min_trend_strength_atr,
            "EMA20 Eğimi": ema20_1m_series[-1] > ema20_1m_series[-4],
            "Bollinger Genişliği": cfg.min_bollinger_width_bps <= bollinger_width_bps <= cfg.max_bollinger_width_bps,
            "Mum Gövdesi": one[-1].close > one[-1].open and candle_body_ratio >= cfg.min_candle_body_ratio,
            "Kısa Momentum": sum(closes[i] > closes[i - 1] for i in range(len(closes) - 3, len(closes))) >= 2,
        }
    else:
        checks = {
            "5M Trend": ema20_5m < ema50_5m,
            "EMA20": entry < ema20_1m,
            "RSI(7)": 30 <= rsi7 <= 50,
            "MACD": hist[-1] < 0 and hist[-1] < hist[-2],
            "Volume": volumes[-1] > mean_volume * cfg.volume_multiplier,
            "VWAP": entry < vwap,
            "Breakout": entry < previous_low,
            "Spread": spread_ok,
        }
        orderbook_ok = micro.imbalance <= -cfg.imbalance_threshold
        taker_ratio = one[-1].taker_buy_volume / one[-1].volume if one[-1].volume > 0 else 0.5
        taker_ok = taker_ratio <= 1.0 - cfg.taker_ratio_threshold
        oi_ok = micro.oi_change_pct is not None and micro.oi_change_pct >= cfg.oi_change_threshold_pct
        structure_checks = {
            "Trend Gücü": trend_strength_atr >= cfg.min_trend_strength_atr,
            "EMA20 Eğimi": ema20_1m_series[-1] < ema20_1m_series[-4],
            "Bollinger Genişliği": cfg.min_bollinger_width_bps <= bollinger_width_bps <= cfg.max_bollinger_width_bps,
            "Mum Gövdesi": one[-1].close < one[-1].open and candle_body_ratio >= cfg.min_candle_body_ratio,
            "Kısa Momentum": sum(closes[i] < closes[i - 1] for i in range(len(closes) - 3, len(closes))) >= 2,
        }

    base_passed = sum(checks.values())
    micro_checks = {"Order Book": orderbook_ok, "Taker Hacmi": taker_ok, "Open Interest": oi_ok}
    all_features = {**checks, **quality_checks, **micro_checks, **structure_checks}
    total_passed = sum(all_features.values())
    # 20 özellik: klasik teknik %40, sapma/kalite %30, mikro yapı %20, yapı/momentum %10.
    oi_score = float(oi_ok) if micro.oi_change_pct is not None else 0.5
    confidence = round(
        base_passed * 5.0
        + quality_passed * 7.5
        + (float(orderbook_ok) + float(taker_ok) + oi_score) * (20.0 / 3.0)
        + sum(structure_checks.values()) * 2.0
    )
    if require_gate and (base_passed < cfg.min_base_checks or quality_passed < cfg.min_quality_checks or total_passed < cfg.min_total_features or confidence < cfg.min_confidence):
        return None
    if side == "LONG":
        stop, tp1, tp2 = entry - 0.8 * current_atr, entry + 0.8 * current_atr, entry + 1.2 * current_atr
    else:
        stop, tp1, tp2 = entry + 0.8 * current_atr, entry - 0.8 * current_atr, entry - 1.2 * current_atr
    return Signal(symbol, side, max(0, min(confidence, 100)), base_passed, checks, entry, tp1, tp2, stop, current_atr, micro.spread_bps, micro.imbalance, taker_ratio, micro.oi_change_pct, quality_checks, quality_passed, vwap_deviation_bps, ema_distance_atr, price_zscore, atr_bps, structure_checks, all_features, total_passed, trend_strength_atr, bollinger_width_bps, candle_body_ratio)


def evaluate(symbol: str, one: list[Candle], five: list[Candle], micro: Microstructure, cfg: Settings) -> Signal | None:
    candidates = [
        signal for side in ("LONG", "SHORT")
        if (signal := _evaluate_side(symbol, side, one, five, micro, cfg)) is not None
    ]
    return max(candidates, key=lambda item: item.confidence, default=None)


def assess(symbol: str, one: list[Candle], five: list[Candle], micro: Microstructure, cfg: Settings) -> dict[str, Signal]:
    """Return both raw side assessments, including candidates below the signal gate."""
    result = {}
    for side in ("LONG", "SHORT"):
        signal = _evaluate_side(symbol, side, one, five, micro, cfg, require_gate=False)
        if signal is not None:
            result[side] = signal
    return result


# ==================== telegram.py ====================


import html




def _price(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.8f}"


def format_signal(signal: Signal) -> str:
    strength = "🔥 VERY STRONG" if signal.confidence >= 90 else "🟢 STRONG" if signal.confidence >= 80 else "🟢 SIGNAL"
    checks = "\n".join(f"{html.escape(name):14} {'✅' if passed else '❌'}" for name, passed in signal.checks.items())
    quality = "\n".join(f"{html.escape(name):18} {'✅' if passed else '❌'}" for name, passed in signal.quality_checks.items())
    oi = "warming up" if signal.oi_change_pct is None else f"{signal.oi_change_pct:+.3f}%"
    return (
        f"<b>{strength}</b>\n\n"
        f"<b>{html.escape(signal.symbol)} — {signal.side}</b>\n\n"
        f"Entry: <code>{_price(signal.entry)}</code>\n"
        f"Confidence: <b>{signal.confidence}/100</b> ({signal.base_passed}/8)\n\n"
        f"20 özellik: <b>{signal.total_passed}/20</b>\n\n"
        f"<pre>{checks}</pre>\n"
        f"<b>Sapma / kalite ({signal.quality_passed}/4)</b>\n<pre>{quality}</pre>\n"
        f"VWAP Δ: {signal.vwap_deviation_bps:+.2f} bps\n"
        f"EMA uzaklığı: {signal.ema_distance_atr:.2f} ATR\n"
        f"Z-score: {signal.price_zscore:+.2f}\n"
        f"ATR: {signal.atr_bps:.2f} bps\n"
        f"Trend gücü: {signal.trend_strength_atr:.2f} ATR\n"
        f"Bollinger genişliği: {signal.bollinger_width_bps:.2f} bps\n"
        f"Mum gövdesi: {signal.candle_body_ratio:.0%}\n"
        f"Order book: {signal.imbalance:+.3f}\n"
        f"Taker buy: {signal.taker_ratio:.1%}\n"
        f"OI Δ: {oi}\n"
        f"Spread: {signal.spread_bps:.2f} bps\n\n"
        f"TP1: <code>{_price(signal.tp1)}</code>\n"
        f"TP2: <code>{_price(signal.tp2)}</code>\n"
        f"SL: <code>{_price(signal.stop)}</code>\n\n"
        f"<i>ATR tabanlı seviyeler; yatırım tavsiyesi değildir.</i>"
    )


# ==================== rest.py ====================


import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REST = "https://fapi.binance.com"
SPOT_MARKET_REST = "https://data-api.binance.vision"


def get_json(path: str, params: dict[str, str | int], timeout: float = 10.0, base: str = REST):
    url = f"{base}{path}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "scalping-signal-dashboard/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _is_451(exc: Exception) -> bool:
    return isinstance(exc, HTTPError) and exc.code == 451


def klines(symbol: str, interval: str, limit: int = 250) -> list[Candle]:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        rows = get_json("/fapi/v1/klines", params)
    except HTTPError as exc:
        if not _is_451(exc):
            raise
        rows = get_json("/api/v3/klines", params, base=SPOT_MARKET_REST)
    # Son satır açık mumdur. Repaint'i azaltmak için yalnızca kapanmış mumlar kullanılır.
    return [Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9])) for r in rows[:-1]]


def market_snapshot(symbol: str, previous_oi: float | None = None) -> tuple[Microstructure, float | None]:
    try:
        depth = get_json("/fapi/v1/depth", {"symbol": symbol, "limit": 20})
        ticker = get_json("/fapi/v1/ticker/bookTicker", {"symbol": symbol})
        oi_payload = get_json("/fapi/v1/openInterest", {"symbol": symbol})
        current_oi: float | None = float(oi_payload["openInterest"])
    except HTTPError as exc:
        if not _is_451(exc):
            raise
        depth = get_json("/api/v3/depth", {"symbol": symbol, "limit": 20}, base=SPOT_MARKET_REST)
        ticker = get_json("/api/v3/ticker/bookTicker", {"symbol": symbol}, base=SPOT_MARKET_REST)
        current_oi = None
    bid_qty = sum(float(level[1]) for level in depth["bids"])
    ask_qty = sum(float(level[1]) for level in depth["asks"])
    total = bid_qty + ask_qty
    imbalance = (bid_qty - ask_qty) / total if total else 0.0
    oi_change = ((current_oi / previous_oi) - 1.0) * 100.0 if current_oi is not None and previous_oi else None
    return Microstructure(float(ticker["bidPrice"]), float(ticker["askPrice"]), imbalance, oi_change), current_oi


def active_usdt_symbols() -> tuple[list[str], str]:
    """Return active symbols ordered by quote volume and the effective data source."""
    try:
        exchange = get_json("/fapi/v1/exchangeInfo", {})
        active = {
            item["symbol"] for item in exchange.get("symbols", [])
            if item.get("status") == "TRADING"
            and item.get("contractType") == "PERPETUAL"
            and item.get("quoteAsset") == "USDT"
        }
        tickers = get_json("/fapi/v1/ticker/24hr", {})
        source = "USDⓈ-M Futures"
    except HTTPError as exc:
        if not _is_451(exc):
            raise
        exchange = get_json("/api/v3/exchangeInfo", {}, base=SPOT_MARKET_REST)
        active = {
            item["symbol"] for item in exchange.get("symbols", [])
            if item.get("status") == "TRADING"
            and item.get("quoteAsset") == "USDT"
            and item.get("isSpotTradingAllowed", True)
        }
        tickers = get_json("/api/v3/ticker/24hr", {}, base=SPOT_MARKET_REST)
        source = "Spot fallback (Futures HTTP 451)"
    volumes = {item["symbol"]: float(item.get("quoteVolume", 0)) for item in tickers if item.get("symbol") in active}
    return sorted(active, key=lambda item: volumes.get(item, 0.0), reverse=True), source


def exchange_symbol(symbol: str) -> bool:
    payload = get_json("/fapi/v1/exchangeInfo", {})
    return any(item.get("symbol") == symbol and item.get("status") == "TRADING" for item in payload.get("symbols", []))


# ==================== trading.py ====================


import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LIVE_BASE = "https://fapi.binance.com"
TESTNET_BASE = "https://demo-fapi.binance.com"


class BinanceAPIError(RuntimeError):
    pass


def floor_step(value: float | Decimal, step: str | Decimal) -> Decimal:
    value_d, step_d = Decimal(str(value)), Decimal(str(step))
    return (value_d / step_d).to_integral_value(rounding=ROUND_DOWN) * step_d


def trigger_price(value: float | Decimal, tick: str | Decimal, *, up: bool) -> Decimal:
    value_d, tick_d = Decimal(str(value)), Decimal(str(tick))
    rounding = ROUND_UP if up else ROUND_DOWN
    return (value_d / tick_d).to_integral_value(rounding=rounding) * tick_d


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True)
class SymbolRules:
    step_size: str
    tick_size: str
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal


@dataclass(frozen=True)
class TradeResult:
    entry_order_id: int
    quantity: str
    average_price: float
    stop_algo_id: int | str
    tp1_algo_id: int | str
    tp2_algo_id: int | str
    environment: str
    slippage_bps: float


class FuturesClient:
    def __init__(self, api_key: str, api_secret: str, *, testnet: bool = True, timeout: float = 10.0) -> None:
        if not api_key or not api_secret:
            raise ValueError("API key ve secret gerekli")
        self.api_key = api_key
        self._secret = api_secret.encode()
        self.base = TESTNET_BASE if testnet else LIVE_BASE
        self.testnet = testnet
        self.timeout = timeout
        self._time_offset_ms = 0

    def _request(self, method: str, path: str, params: dict[str, object] | None = None, *, signed: bool = False):
        values = {key: value for key, value in (params or {}).items() if value is not None}
        if signed:
            values["timestamp"] = int(time.time() * 1000) + self._time_offset_ms
            values["recvWindow"] = 5000
        query = urlencode(values)
        if signed:
            signature = hmac.new(self._secret, query.encode(), hashlib.sha256).hexdigest()
            query = f"{query}&signature={signature}"
        url = f"{self.base}{path}"
        data = query.encode() if method in {"POST", "PUT", "DELETE"} else None
        if method == "GET" and query:
            url = f"{url}?{query}"
        request = Request(url, data=data, method=method, headers={"X-MBX-APIKEY": self.api_key, "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
                detail = f"{payload.get('code')}: {payload.get('msg')}"
            except json.JSONDecodeError:
                detail = body[:300]
            raise BinanceAPIError(f"Binance HTTP {exc.code} — {detail}") from exc

    def sync_time(self) -> None:
        payload = self._request("GET", "/fapi/v1/time")
        self._time_offset_ms = int(payload["serverTime"]) - int(time.time() * 1000)

    def account_balance(self) -> dict[str, float]:
        self.sync_time()
        rows = self._request("GET", "/fapi/v3/balance", signed=True)
        return {row["asset"]: float(row["availableBalance"]) for row in rows}

    def one_way_mode(self) -> bool:
        payload = self._request("GET", "/fapi/v1/positionSide/dual", signed=True)
        return not bool(payload["dualSidePosition"])

    def ensure_symbol_clear(self, symbol: str) -> None:
        positions = self._request("GET", "/fapi/v2/positionRisk", {"symbol": symbol}, signed=True)
        if any(Decimal(str(row.get("positionAmt", "0"))) != 0 for row in positions):
            raise BinanceAPIError(f"{symbol} üzerinde mevcut pozisyon var; yeni giriş reddedildi")
        orders = self._request("GET", "/fapi/v1/openOrders", {"symbol": symbol}, signed=True)
        if orders:
            raise BinanceAPIError(f"{symbol} üzerinde açık standart emir var; yeni giriş reddedildi")
        algo_orders = self._request("GET", "/fapi/v1/openAlgoOrders", {"symbol": symbol}, signed=True)
        if algo_orders:
            raise BinanceAPIError(f"{symbol} üzerinde açık koruyucu/algo emir var; yeni giriş reddedildi")

    def rules(self, symbol: str) -> SymbolRules:
        payload = self._request("GET", "/fapi/v1/exchangeInfo")
        item = next((row for row in payload["symbols"] if row["symbol"] == symbol), None)
        if item is None or item.get("status") != "TRADING":
            raise BinanceAPIError(f"{symbol} işlemde değil")
        filters = {row["filterType"]: row for row in item["filters"]}
        lot = filters.get("MARKET_LOT_SIZE", filters["LOT_SIZE"])
        price = filters["PRICE_FILTER"]
        notional = filters.get("MIN_NOTIONAL", {})
        return SymbolRules(lot["stepSize"], price["tickSize"], Decimal(lot["minQty"]), Decimal(lot["maxQty"]), Decimal(str(notional.get("notional", "5"))))

    def set_leverage(self, symbol: str, leverage: int) -> None:
        self._request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}, signed=True)

    def set_isolated(self, symbol: str) -> None:
        try:
            self._request("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"}, signed=True)
        except BinanceAPIError as exc:
            if "-4046" not in str(exc):
                raise

    def _order(self, **params):
        return self._request("POST", "/fapi/v1/order", params, signed=True)

    def _algo(self, **params):
        return self._request("POST", "/fapi/v1/algoOrder", {"algoType": "CONDITIONAL", **params}, signed=True)

    @staticmethod
    def _algo_id(payload: dict) -> int | str:
        return payload.get("algoId", payload.get("clientAlgoId", "unknown"))

    def open_protected(self, signal: Signal, notional_usdt: float, leverage: int, *, isolated: bool = True, max_slippage_bps: float = 5.0) -> TradeResult:
        if not self.one_way_mode():
            raise BinanceAPIError("Hedge Mode desteklenmiyor; Binance hesabında Position Mode = One-way yapın")
        self.ensure_symbol_clear(signal.symbol)
        rules = self.rules(signal.symbol)
        quantity = floor_step(Decimal(str(notional_usdt)) / Decimal(str(signal.entry)), rules.step_size)
        if quantity < rules.min_qty or quantity > rules.max_qty:
            raise BinanceAPIError(f"Miktar izin verilen aralıkta değil: {quantity}")
        if quantity * Decimal(str(signal.entry)) < rules.min_notional:
            raise BinanceAPIError(f"Minimum nominal değer {rules.min_notional} USDT")
        self.set_leverage(signal.symbol, leverage)
        if isolated:
            self.set_isolated(signal.symbol)
        entry_side = "BUY" if signal.side == "LONG" else "SELL"
        exit_side = "SELL" if signal.side == "LONG" else "BUY"
        quote = self._request("GET", "/fapi/v1/ticker/bookTicker", {"symbol": signal.symbol})
        executable_price = float(quote["askPrice"] if signal.side == "LONG" else quote["bidPrice"])
        quote_deviation = abs(executable_price / signal.entry - 1.0) * 10_000.0
        if quote_deviation > max_slippage_bps:
            raise BinanceAPIError(f"Fiyat sinyalden {quote_deviation:.2f} bps saptı; maksimum {max_slippage_bps:.2f} bps")
        qty_text = decimal_text(quantity)
        entry = self._order(symbol=signal.symbol, side=entry_side, type="MARKET", quantity=qty_text, newOrderRespType="RESULT")
        filled = Decimal(str(entry.get("executedQty", qty_text)))
        average_price = float(entry.get("avgPrice") or signal.entry)
        slippage_bps = ((average_price / signal.entry) - 1.0) * 10_000.0
        adverse_slippage = slippage_bps if signal.side == "LONG" else -slippage_bps
        if adverse_slippage > max_slippage_bps:
            try:
                self._order(symbol=signal.symbol, side=exit_side, type="MARKET", quantity=decimal_text(filled), reduceOnly="true", newOrderRespType="RESULT")
            except Exception as close_error:
                raise BinanceAPIError(f"KRİTİK: Slippage {adverse_slippage:.2f} bps ve acil kapanış başarısız: {close_error}") from close_error
            raise BinanceAPIError(f"Slippage {adverse_slippage:.2f} bps; pozisyon acil kapatıldı")
        stop_price = trigger_price(signal.stop, rules.tick_size, up=signal.side == "SHORT")
        tp1_price = trigger_price(signal.tp1, rules.tick_size, up=signal.side == "LONG")
        tp2_price = trigger_price(signal.tp2, rules.tick_size, up=signal.side == "LONG")
        half = floor_step(filled / 2, rules.step_size)
        try:
            stop = self._algo(symbol=signal.symbol, side=exit_side, type="STOP_MARKET", triggerPrice=decimal_text(stop_price), closePosition="true", workingType="MARK_PRICE", priceProtect="true")
        except Exception as stop_error:
            try:
                self._order(symbol=signal.symbol, side=exit_side, type="MARKET", quantity=decimal_text(filled), reduceOnly="true", newOrderRespType="RESULT")
            except Exception as close_error:
                raise BinanceAPIError(f"KRİTİK: Stop kurulamadı ({stop_error}); acil kapanış da başarısız ({close_error}). Binance'i hemen kontrol edin.") from close_error
            raise BinanceAPIError(f"Stop kurulamadı; pozisyon acil piyasa emriyle kapatıldı: {stop_error}") from stop_error
        try:
            if half >= rules.min_qty and half * Decimal(str(average_price)) >= rules.min_notional:
                tp1 = self._algo(symbol=signal.symbol, side=exit_side, type="TAKE_PROFIT_MARKET", triggerPrice=decimal_text(tp1_price), quantity=decimal_text(half), reduceOnly="true", workingType="MARK_PRICE", priceProtect="true")
            else:
                tp1 = {"algoId": "skipped-small-qty"}
            tp2 = self._algo(symbol=signal.symbol, side=exit_side, type="TAKE_PROFIT_MARKET", triggerPrice=decimal_text(tp2_price), closePosition="true", workingType="MARK_PRICE", priceProtect="true")
        except Exception as exc:
            raise BinanceAPIError(f"Giriş ve stop aktif; TP emirlerinden biri kurulamadı: {exc}. Binance emirlerini kontrol edin.") from exc
        return TradeResult(int(entry["orderId"]), qty_text, average_price, self._algo_id(stop), self._algo_id(tp1), self._algo_id(tp2), "TESTNET" if self.testnet else "LIVE", slippage_bps)


# ==================== streamlit_app.py ====================


import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st



st.set_page_config(page_title="Futures Scalping Radar", page_icon="⚡", layout="wide")
load_dotenv()

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at 15% 0%, #13233d 0, #07111f 38%, #040914 100%);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0c1728 0%, #07101d 100%);
        border-right: 1px solid rgba(70, 211, 154, .16);
    }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(18, 35, 57, .94), rgba(8, 18, 32, .94));
        border: 1px solid rgba(102, 190, 255, .15);
        border-radius: 14px;
        padding: 14px 16px;
        box-shadow: 0 8px 28px rgba(0, 0, 0, .18);
    }
    [data-testid="stMetricValue"] { color: #e9f7ff; }
    .hero {
        padding: 22px 26px;
        border-radius: 20px;
        background: linear-gradient(120deg, rgba(18, 55, 88, .92), rgba(10, 28, 51, .9));
        border: 1px solid rgba(65, 213, 157, .22);
        box-shadow: 0 14px 45px rgba(0,0,0,.22);
        margin-bottom: 18px;
    }
    .hero h1 { margin: 0; color: #f4fbff; font-size: 2rem; }
    .hero p { margin: 8px 0 0; color: #9fb4c9; }
    .status-chip {
        display: inline-block; padding: 5px 10px; border-radius: 999px;
        color: #66efb7; background: rgba(34, 197, 130, .11);
        border: 1px solid rgba(34, 197, 130, .25); font-size: .78rem;
    }
    div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
    .stButton > button { border-radius: 10px; font-weight: 650; }
    </style>
    """,
    unsafe_allow_html=True,
)


def secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, "")))
    except Exception:
        return os.getenv(name, "")


def send_telegram(token: str, chat_id: str, text: str) -> None:
    data = urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    request = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urlopen(request, timeout=10) as response:
        if response.status >= 400:
            raise RuntimeError(f"Telegram HTTP {response.status}")


def score_label(score: int) -> str:
    if score >= 90:
        return "🔥 VERY STRONG"
    if score >= 80:
        return "🟢 STRONG"
    if score >= 70:
        return "🟢 SIGNAL"
    return "⚪ NO SIGNAL"


def scan_symbol(symbol: str, cfg: Settings, previous_oi: float | None):
    one = klines(symbol, "1m")
    five = klines(symbol, "5m")
    hourly = klines(symbol, "1h", 73)
    micro, current_oi = market_snapshot(symbol, previous_oi)
    three_day_high = max(candle.high for candle in hourly) if hourly else one[-1].close
    drawdown_pct = (one[-1].close / three_day_high - 1.0) * 100.0 if three_day_high > 0 else 0.0
    last_three = one[-3:]
    three_candle_reversal = (
        len(last_three) == 3
        and all(candle.close > candle.open for candle in last_three)
        and last_three[0].close < last_three[1].close < last_three[2].close
    )
    return one, five, micro, current_oi, assess(symbol, one, five, micro, cfg), drawdown_pct, three_candle_reversal


@st.cache_data(ttl=1800, show_spinner=False)
def futures_catalog() -> tuple[list[str], str]:
    return active_usdt_symbols()


def render_signal(signal: Signal, eligible: bool) -> None:
    st.subheader(f"{signal.side} · {score_label(signal.confidence)}")
    a, b, c, d = st.columns(4)
    a.metric("Skor", f"{signal.confidence}/100")
    b.metric("20 özellik", f"{signal.total_passed}/20")
    c.metric("Spread", f"{signal.spread_bps:.2f} bps")
    d.metric("Order book", f"{signal.imbalance:+.3f}")
    rows = [{"Koşul": key, "Durum": "✅" if value else "❌"} for key, value in signal.checks.items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.markdown(f"**Sapma ve piyasa kalitesi: {signal.quality_passed}/4**")
    quality_rows = [{"Filtre": key, "Durum": "✅" if value else "❌"} for key, value in signal.quality_checks.items()]
    st.dataframe(pd.DataFrame(quality_rows), hide_index=True, use_container_width=True)
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("VWAP sapması", f"{signal.vwap_deviation_bps:+.2f} bps")
    q2.metric("EMA mesafesi", f"{signal.ema_distance_atr:.2f} ATR")
    q3.metric("20m Z-score", f"{signal.price_zscore:+.2f}")
    q4.metric("ATR volatilitesi", f"{signal.atr_bps:.2f} bps")
    st.markdown("**Trend, yapı ve momentum**")
    structure_rows = [{"Özellik": key, "Durum": "✅" if value else "❌"} for key, value in signal.structure_checks.items()]
    st.dataframe(pd.DataFrame(structure_rows), hide_index=True, use_container_width=True)
    s1, s2, s3 = st.columns(3)
    s1.metric("5m trend gücü", f"{signal.trend_strength_atr:.2f} ATR")
    s2.metric("Bollinger genişliği", f"{signal.bollinger_width_bps:.2f} bps")
    s3.metric("Mum gövdesi", f"{signal.candle_body_ratio:.0%}")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Entry", f"{signal.entry:,.4f}")
    p2.metric("TP1", f"{signal.tp1:,.4f}")
    p3.metric("TP2", f"{signal.tp2:,.4f}")
    p4.metric("SL", f"{signal.stop:,.4f}")
    if eligible:
        st.success("Sinyal kapısı geçildi")
    else:
        st.caption("Skor veya 6/8 teknik koşul eşiği henüz geçilmedi.")


st.markdown(
    """
    <div class="hero">
      <span class="status-chip">● BINANCE USDⓈ-M FUTURES</span>
      <h1>⚡ Scalping Command Center</h1>
      <p>1m giriş · 5m trend · mikro yapı · istatistiksel sapma · korumalı emir yönetimi</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.caption("🤖 BOT CONTROL")
    st.header("Ayarlar")
    try:
        all_symbols, market_source = futures_catalog()
    except Exception as exc:
        st.warning(f"Parite kataloğu alınamadı; temel liste kullanılıyor: {exc}")
        all_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
        market_source = "Temel liste"
    if "Spot fallback" in market_source:
        st.warning("Streamlit Cloud Binance Futures'a HTTP 451 döndürüyor. Panel resmî Binance Spot market verisine geçti; OI ve Cloud'dan gerçek Futures emirleri kullanılamaz.")
    else:
        st.success(f"Veri kaynağı: {market_source}")
    symbol = st.selectbox("Detay paritesi", all_symbols, index=0)
    scan_all_market = st.toggle("Tüm piyasayı sürekli tara", True)
    scan_batch_size = st.slider("Her turda analiz edilen coin", 5, 20, 10, 5, disabled=not scan_all_market)
    default_radar = all_symbols[: min(5, len(all_symbols))]
    selected_radar_symbols = st.multiselect(
        f"Radar pariteleri · {len(all_symbols)} aktif USDT perpetual",
        all_symbols,
        default=default_radar,
        help="Liste 24 saatlik hacme göre sıralanır. Tüm aktif pariteler seçilebilir.",
        disabled=scan_all_market,
    )
    if len(selected_radar_symbols) > 20:
        st.warning("API yükünü sınırlamak için ilk 20 seçili parite taranacak.")
    manual_radar_symbols = selected_radar_symbols[:20]
    refresh_seconds = st.slider("Yenileme (saniye)", 5, 60, 15, 5)
    live = st.toggle("Canlı yenileme", True)
    min_checks = st.slider("Minimum teknik koşul", 1, 8, 6)
    min_confidence = st.slider("Minimum skor", 0, 100, 70, 5)
    crash_threshold_pct = st.slider("3 günlük düşüş alarmı (%)", 10, 95, 90, 5)
    min_quality_checks = st.slider("Minimum sapma/kalite filtresi", 0, 4, 3)
    min_total_features = st.slider("Minimum toplam özellik", 0, 20, 14)
    max_spread = st.number_input("Maksimum spread (bps)", 0.1, 20.0, 2.0, 0.1)
    volume_multiplier = st.number_input("Hacim çarpanı", 1.0, 5.0, 1.3, 0.1)
    with st.expander("Sapma ve volatilite sınırları"):
        max_vwap_deviation = st.number_input("Maksimum VWAP sapması (bps)", 1.0, 500.0, 35.0, 1.0)
        max_zscore = st.number_input("Maksimum mutlak Z-score", 0.5, 10.0, 2.5, 0.1)
        max_ema_distance = st.number_input("Maksimum EMA mesafesi (ATR)", 0.1, 10.0, 2.0, 0.1)
        min_atr_bps = st.number_input("Minimum ATR (bps)", 0.0, 100.0, 1.0, 0.5)
        max_atr_bps = st.number_input("Maksimum ATR (bps)", 1.0, 1000.0, 60.0, 1.0)
    st.divider()
    telegram_token = st.text_input("Telegram bot token", value=secret("TELEGRAM_BOT_TOKEN"), type="password")
    telegram_chat_id = st.text_input("Telegram chat ID", value=secret("TELEGRAM_CHAT_ID"))
    auto_send = st.toggle("Geçerli sinyali otomatik gönder", False)
    st.divider()
    st.subheader("Binance emir bağlantısı")
    futures_region_blocked = "Spot fallback" in market_source
    trading_enabled = st.toggle("Emir modunu etkinleştir", False, disabled=futures_region_blocked)
    environment = st.radio("Ortam", ["TESTNET", "LIVE"], horizontal=True)
    binance_key = st.text_input("Binance API key", value=secret("BINANCE_API_KEY"), type="password")
    binance_secret = st.text_input("Binance API secret", value=secret("BINANCE_API_SECRET"), type="password")
    notional_usdt = st.number_input("Pozisyon büyüklüğü (USDT nominal)", 5.0, 1_000_000.0, 25.0, 5.0)
    leverage = st.slider("Kaldıraç", 1, 20, 2)
    isolated_margin = st.toggle("Isolated margin", True)
    max_entry_slippage = st.number_input("Maksimum giriş sapması/slippage (bps)", 0.1, 100.0, 5.0, 0.5)
    auto_trade = st.toggle("Geçerli sinyalde otomatik emir", False, disabled=not trading_enabled)
    live_phrase = st.text_input(f"Canlı onay: LIVE {symbol}", type="password", disabled=environment != "LIVE")
    live_unlocked = environment == "TESTNET" or live_phrase == f"LIVE {symbol}"
    credentials_ready = bool(binance_key and binance_secret)
    if st.button("API bağlantısını ve bakiyeyi test et", disabled=not credentials_ready):
        try:
            client = FuturesClient(binance_key, binance_secret, testnet=environment == "TESTNET")
            balances = client.account_balance()
            st.success(f"Bağlandı · Kullanılabilir USDT: {balances.get('USDT', 0):,.2f}")
        except Exception as exc:
            st.error(f"Bağlantı başarısız: {exc}")
    if environment == "LIVE":
        st.error("LIVE gerçek para kullanır. IP kısıtlı, yalnız Futures yetkili ve para çekme yetkisi kapalı bir API key kullanın.")
    else:
        st.info("TESTNET varsayılandır; test fonlarıyla emir açar.")

cfg = Settings(
    symbols=(symbol,), telegram_token=telegram_token, telegram_chat_id=telegram_chat_id,
    telegram_enabled=bool(telegram_token and telegram_chat_id), min_base_checks=min_checks,
    min_confidence=min_confidence, cooldown_minutes=15, max_spread_bps=max_spread,
    volume_multiplier=volume_multiplier, breakout_lookback=20, imbalance_threshold=.08,
    taker_ratio_threshold=.54, oi_change_threshold_pct=.02, log_level="INFO",
    min_quality_checks=min_quality_checks, max_vwap_deviation_bps=max_vwap_deviation,
    max_zscore=max_zscore, max_ema_distance_atr=max_ema_distance,
    min_atr_bps=min_atr_bps, max_atr_bps=max_atr_bps,
    max_entry_slippage_bps=max_entry_slippage,
    min_total_features=min_total_features, min_trend_strength_atr=.15,
    min_bollinger_width_bps=4.0, max_bollinger_width_bps=150.0,
    min_candle_body_ratio=.45,
)

if "oi" not in st.session_state:
    st.session_state.oi = {}
if "sent_candles" not in st.session_state:
    st.session_state.sent_candles = set()
if "traded_candles" not in st.session_state:
    st.session_state.traded_candles = set()
if "scan_offset" not in st.session_state:
    st.session_state.scan_offset = 0
if "radar_history" not in st.session_state:
    st.session_state.radar_history = {}


def execute_trade(signal: Signal):
    if futures_region_blocked:
        raise BinanceAPIError("Bu Streamlit Cloud bölgesinde Binance Futures HTTP 451 ile engelli; emri yerel/VPS kurulumundan gönderin")
    if not trading_enabled or not credentials_ready:
        raise BinanceAPIError("Emir modu ve API bilgileri gerekli")
    if not live_unlocked:
        raise BinanceAPIError(f"Canlı işlem için tam olarak LIVE {symbol} yazın")
    client = FuturesClient(binance_key, binance_secret, testnet=environment == "TESTNET")
    client.sync_time()
    return client.open_protected(signal, notional_usdt, leverage, isolated=isolated_margin, max_slippage_bps=cfg.max_entry_slippage_bps)

run_every = refresh_seconds if live else None


@st.fragment(run_every=run_every)
def dashboard() -> None:
    if scan_all_market and all_symbols:
        offset = int(st.session_state.scan_offset) % len(all_symbols)
        radar_symbols = [all_symbols[(offset + index) % len(all_symbols)] for index in range(min(scan_batch_size, len(all_symbols)))]
    else:
        offset = 0
        radar_symbols = manual_radar_symbols
    symbols_to_scan = list(dict.fromkeys([symbol, *radar_symbols]))
    packets = {}
    errors = {}
    try:
        with ThreadPoolExecutor(max_workers=min(6, len(symbols_to_scan))) as pool:
            future_map = {pool.submit(scan_symbol, item, cfg, st.session_state.oi.get(item)): item for item in symbols_to_scan}
            for future in as_completed(future_map):
                item = future_map[future]
                try:
                    packets[item] = future.result()
                except Exception as exc:
                    errors[item] = str(exc)
        if symbol not in packets:
            raise RuntimeError(errors.get(symbol, "seçili sembol verisi yok"))
        one, five, micro, current_oi, results, selected_drawdown, selected_reversal = packets[symbol]
        for item, packet in packets.items():
            st.session_state.oi[item] = packet[3]
    except Exception as exc:
        st.error(f"Binance verisi alınamadı: {exc}")
        return

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Son kapanış", f"{one[-1].close:,.4f}")
    top2.metric("Spread", f"{micro.spread_bps:.2f} bps")
    top3.metric("OI değişimi", "Isınıyor" if micro.oi_change_pct is None else f"{micro.oi_change_pct:+.4f}%")
    top4.metric("Güncelleme", datetime.now().strftime("%H:%M:%S"))
    chart = pd.DataFrame({"Fiyat": [c.close for c in one[-100:]]}, index=pd.to_datetime([c.open_time for c in one[-100:]], unit="ms"))
    st.line_chart(chart, height=260)

    st.subheader("🛰️ Çoklu Coin Fırsat Radarı")
    if scan_all_market:
        end_position = min(offset + len(radar_symbols), len(all_symbols))
        st.caption(
            f"Dönüşümlü tarama: {offset + 1}–{end_position} / {len(all_symbols)} · "
            f"Bu tur: {', '.join(radar_symbols)}"
        )
    radar_rows = []
    eligible_candidates = []
    for item in radar_symbols:
        packet = packets.get(item)
        if packet is None:
            radar_rows.append({"Parite": item, "Durum": "Veri hatası", "Hata": errors.get(item, "-")})
            continue
        item_one, _, item_micro, _, item_results, drawdown_pct, three_candle_reversal = packet
        best = max(item_results.values(), key=lambda candidate: candidate.confidence, default=None)
        if best is None:
            continue
        eligible = (
            best.base_passed >= cfg.min_base_checks
            and best.quality_passed >= cfg.min_quality_checks
            and best.total_passed >= cfg.min_total_features
            and best.confidence >= cfg.min_confidence
        )
        if eligible:
            eligible_candidates.append(best)
        radar_rows.append({
            "Parite": item,
            "Fiyat": item_one[-1].close,
            "Yön": best.side,
            "Skor": best.confidence,
            "Özellik": f"{best.total_passed}/20",
            "Sinyal": "UYGUN" if eligible else "BEKLE",
            "Spread bps": round(item_micro.spread_bps, 2),
            "Order Book": round(item_micro.imbalance, 3),
            "OI %": None if item_micro.oi_change_pct is None else round(item_micro.oi_change_pct, 4),
            "VWAP Δ bps": round(best.vwap_deviation_bps, 2),
            "Z-score": round(best.price_zscore, 2),
            "ATR bps": round(best.atr_bps, 2),
            "3g zirveden düşüş %": round(drawdown_pct, 2),
            "3 yeşil mum": "EVET" if three_candle_reversal else "HAYIR",
            "Güncellendi": datetime.now().strftime("%H:%M:%S"),
        })
    for row in radar_rows:
        st.session_state.radar_history[row["Parite"]] = row
    visible_rows = list(st.session_state.radar_history.values()) if scan_all_market else radar_rows
    if visible_rows:
        radar_frame = pd.DataFrame(visible_rows)
        if "Skor" in radar_frame.columns:
            radar_frame = radar_frame.sort_values("Skor", ascending=False, na_position="last")
        st.dataframe(radar_frame, hide_index=True, use_container_width=True, height=min(390, 42 + len(radar_frame) * 36))
    if eligible_candidates:
        recommendation = max(eligible_candidates, key=lambda candidate: (candidate.confidence, candidate.total_passed, -candidate.spread_bps))
        st.success(
            f"Algoritmik olarak en güçlü aday: {recommendation.symbol} · {recommendation.side} · "
            f"{recommendation.confidence}/100 · {recommendation.total_passed}/20 özellik. "
            "Bu bir yatırım tavsiyesi değil; emirden önce risk büyüklüğünü ve piyasa koşullarını kontrol edin."
        )
    else:
        st.info("Şu anda tüm eşikleri geçen bir parite yok: işlem açmak yerine bekle.")
    rebound_candidates = []
    for item in radar_symbols:
        packet = packets.get(item)
        if packet is None:
            continue
        _, _, _, _, item_results, drawdown_pct, three_candle_reversal = packet
        if drawdown_pct <= -float(crash_threshold_pct) and three_candle_reversal:
            best = max(item_results.values(), key=lambda candidate: candidate.confidence, default=None)
            if best is not None:
                rebound_candidates.append((item, drawdown_pct, best))
    if rebound_candidates:
        rebound_candidates.sort(key=lambda item: (item[1], -item[2].confidence))
        coin, drawdown, rebound_signal = rebound_candidates[0]
        st.warning(
            f"Kapitülasyon dönüş adayı: {coin} · 3 günlük zirveden {drawdown:.2f}% · "
            f"son 3 mum yeşil/yükselen · algoritma yönü {rebound_signal.side} · skor {rebound_signal.confidence}/100. "
            "%90+ düşüş olağanüstü yüksek risk, delist ve likidite problemi gösterebilir."
        )
    else:
        st.caption(f"3 günlük zirveden en az %{crash_threshold_pct} düşüp son üç 1m mumu yükselen coin bulunmadı.")
    if errors:
        with st.expander("Radar veri hataları"):
            st.json(errors)
    if scan_all_market and all_symbols:
        st.session_state.scan_offset = (offset + len(radar_symbols)) % len(all_symbols)

    long_tab, short_tab = st.tabs(["LONG", "SHORT"])
    eligible_signals = []
    for tab, side in ((long_tab, "LONG"), (short_tab, "SHORT")):
        with tab:
            signal = results.get(side)
            if signal is None:
                st.warning("Gösterge hesabı için yeterli veri yok.")
                continue
            eligible = signal.base_passed >= cfg.min_base_checks and signal.quality_passed >= cfg.min_quality_checks and signal.total_passed >= cfg.min_total_features and signal.confidence >= cfg.min_confidence
            render_signal(signal, eligible)
            if eligible:
                eligible_signals.append(signal)
            if st.button(f"{side} sinyalini Telegram'a gönder", key=f"send_{side}", disabled=not (telegram_token and telegram_chat_id)):
                try:
                    send_telegram(telegram_token, telegram_chat_id, format_signal(signal))
                    st.toast("Telegram mesajı gönderildi", icon="✅")
                except Exception as exc:
                    st.error(f"Telegram gönderilemedi: {exc}")
            manual_trade_key = (environment, symbol, signal.side, one[-1].open_time)
            already_traded = manual_trade_key in st.session_state.traded_candles
            order_ready = eligible and trading_enabled and credentials_ready and live_unlocked and not already_traded
            if st.button(f"{side} korumalı piyasa emri aç", key=f"trade_{side}", type="primary", disabled=not order_ready):
                # HTTP timeout sonrası emir durumu belirsiz olabilir; aynı mumda otomatik tekrar gönderme.
                st.session_state.traded_candles.add(manual_trade_key)
                try:
                    result = execute_trade(signal)
                    st.success(f"{result.environment} emir açıldı · Order {result.entry_order_id} · Qty {result.quantity} · Slippage {result.slippage_bps:+.2f} bps · SL {result.stop_algo_id} · TP1 {result.tp1_algo_id} · TP2 {result.tp2_algo_id}")
                except Exception as exc:
                    st.error(f"Emir başarısız: {exc}")
            elif already_traded:
                st.caption("Bu yön için aynı kapanmış mumda daha önce emir denendi.")

    if auto_send and eligible_signals and telegram_token and telegram_chat_id:
        best = max(eligible_signals, key=lambda s: s.confidence)
        candle_key = (symbol, best.side, one[-1].open_time)
        if candle_key not in st.session_state.sent_candles:
            try:
                send_telegram(telegram_token, telegram_chat_id, format_signal(best))
                st.session_state.sent_candles.add(candle_key)
                st.toast(f"{best.side} sinyali otomatik gönderildi", icon="📨")
            except Exception as exc:
                st.error(f"Otomatik Telegram gönderimi başarısız: {exc}")

    if auto_trade and trading_enabled and credentials_ready and live_unlocked and eligible_signals:
        best = max(eligible_signals, key=lambda s: s.confidence)
        trade_key = (environment, symbol, best.side, one[-1].open_time)
        if trade_key not in st.session_state.traded_candles:
            # Tekrar denemeyle mükerrer piyasa emrini engellemek için giriş denemesinden önce işaretlenir.
            st.session_state.traded_candles.add(trade_key)
            try:
                result = execute_trade(best)
                st.success(f"Otomatik {result.environment} emir açıldı · Order {result.entry_order_id} · Qty {result.quantity}")
            except Exception as exc:
                st.error(f"Otomatik emir başarısız: {exc}")


dashboard()
st.caption("Yatırım tavsiyesi değildir. Komisyon, funding, slippage ve gecikmeyi backtest/paper trading sürecine dahil edin.")
