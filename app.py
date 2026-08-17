# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import math
import hmac
import html
import hashlib
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import pandas as pd
import streamlit as st


# ---------------- ENV ----------------
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

FAPI = os.getenv("BINANCE_FUTURES_REST", "https://fapi.binance.com")
SPOT = os.getenv("BINANCE_SPOT_REST", "https://api.binance.com")
FORCE_SPOT = os.getenv("FORCE_SPOT", "1") == "1"


# ---------------- HTTP ----------------
def req_json(base: str, path: str, params: dict | None = None, timeout: float = 15.0):
    q = urlencode(params or {})
    url = f"{base}{path}" + (f"?{q}" if q else "")
    req = Request(url, headers={"User-Agent": "enterprise-signal-panel/2.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def is_451(exc: Exception) -> bool:
    if isinstance(exc, HTTPError) and exc.code == 451:
        return True
    s = str(exc).lower()
    return ("restricted location" in s) or ("eligibility" in s) or ("http 451" in s)


def parse_http_error(e: HTTPError) -> str:
    try:
        body = e.read().decode("utf-8", errors="ignore")
        j = json.loads(body) if body else {}
        code = j.get("code")
        msg = j.get("msg")
        if code is not None or msg:
            return f"HTTP {e.code} | Binance code={code} msg={msg}"
    except Exception:
        pass
    return f"HTTP {e.code} {e.reason}"


# ---------------- SIGNED TEST (optional) ----------------
def signed_futures_probe(api_key: str, api_secret: str, base: str = FAPI) -> tuple[bool, str]:
    try:
        t = req_json(base, "/fapi/v1/time")
        server_time = int(t["serverTime"])

        params = {"timestamp": server_time, "recvWindow": 5000}
        query = urlencode(params)
        sig = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{base}/fapi/v2/account?{query}&signature={sig}"
        req = Request(url, headers={"X-MBX-APIKEY": api_key, "User-Agent": "enterprise-signal-panel/2.0"})
        with urlopen(req, timeout=10) as r:
            if r.status >= 400:
                return False, f"HTTP {r.status}"
            json.load(r)
        return True, "Futures API signed erişim OK"
    except HTTPError as e:
        if is_451(e):
            return False, "HTTP 451 restricted location / eligibility"
        return False, parse_http_error(e)
    except URLError as e:
        return False, f"Ağ hatası: {e}"
    except Exception as e:
        return False, f"Hata: {e}"


# ---------------- Indicators ----------------
def ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    a = 2.0 / (period + 1)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(a * float(v) + (1 - a) * out[-1])
    return out


def sma(values: Sequence[float], period: int) -> list[float]:
    out = []
    s = 0.0
    q = []
    for v in values:
        q.append(float(v))
        s += float(v)
        if len(q) > period:
            s -= q.pop(0)
        out.append(s / len(q))
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[float]:
    if len(values) < 2:
        return [50.0] * len(values)
    gains, losses = [0.0], [0.0]
    for p, c in zip(values, values[1:]):
        d = c - p
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag, al = ema(gains, period), ema(losses, period)
    out = []
    for g, l in zip(ag, al):
        if l == 0:
            out.append(100.0 if g > 0 else 50.0)
        else:
            out.append(100.0 - 100.0 / (1.0 + g / l))
    return out


def macd_hist(values: Sequence[float]) -> list[float]:
    f, s = ema(values, 12), ema(values, 26)
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


def vwap_last(highs, lows, closes, volumes, period=20) -> float:
    s = max(0, len(closes) - period)
    pv = 0.0
    vv = 0.0
    for h, l, c, v in zip(highs[s:], lows[s:], closes[s:], volumes[s:]):
        p = (h + l + c) / 3.0
        pv += p * v
        vv += v
    return (pv / vv) if vv > 0 else closes[-1]


def pct_change(a: float, b: float) -> float:
    return ((a / b) - 1.0) if b else 0.0


# ---------------- Domain ----------------
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
class Micro:
    bid: float
    ask: float
    imbalance: float
    oi_change_pct: float | None

    @property
    def spread_bps(self) -> float:
        mid = (self.bid + self.ask) / 2.0
        return ((self.ask - self.bid) / mid * 10000.0) if mid > 0 else 9999.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str
    score: int
    early_uptrend: bool
    entry: float
    tp1: float
    tp2: float
    sl: float
    base_passed: int
    quality_passed: int
    total_passed: int
    checks: dict[str, bool]
    quality: dict[str, bool]
    votes: dict[str, float]
    spread_bps: float
    dl_bonus: float
    dl_prob: float
    features_count: int


# ---------------- Klines pagination (up to 10k) ----------------
def fetch_klines_paged(base: str, path: str, symbol: str, interval: str, total_limit: int = 10000) -> list[list]:
    out = []
    end_time = None
    remaining = total_limit
    step = 1500  # Binance max
    while remaining > 0:
        lim = min(step, remaining)
        p = {"symbol": symbol, "interval": interval, "limit": lim}
        if end_time is not None:
            p["endTime"] = end_time
        rows = req_json(base, path, p)
        if not rows:
            break
        out = rows + out
        first_open = int(rows[0][0])
        end_time = first_open - 1
        remaining -= len(rows)
        if len(rows) < lim:
            break
    # dedupe by open time
    uniq = {}
    for r in out:
        uniq[int(r[0])] = r
    return [uniq[k] for k in sorted(uniq.keys())]


# ---------------- Data fetch ----------------
def fetch_klines(symbol: str, interval: str, limit: int = 10000) -> list[Candle]:
    if FORCE_SPOT:
        rows = fetch_klines_paged(SPOT, "/api/v3/klines", symbol, interval, total_limit=limit)
    else:
        try:
            rows = fetch_klines_paged(FAPI, "/fapi/v1/klines", symbol, interval, total_limit=limit)
        except HTTPError as e:
            if not is_451(e):
                raise
            rows = fetch_klines_paged(SPOT, "/api/v3/klines", symbol, interval, total_limit=limit)

    if len(rows) > 1:
        rows = rows[:-1]  # last incomplete candle

    return [
        Candle(
            open_time=int(r[0]),
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=float(r[5]),
            taker_buy_volume=float(r[9]) if len(r) > 9 else float(r[5]) * 0.5,
        )
        for r in rows
    ]


def fetch_micro(symbol: str, prev_oi: float | None) -> tuple[Micro, float | None]:
    if FORCE_SPOT:
        d = req_json(SPOT, "/api/v3/depth", {"symbol": symbol, "limit": 20})
        t = req_json(SPOT, "/api/v3/ticker/bookTicker", {"symbol": symbol})
        oi_now = None
    else:
        try:
            d = req_json(FAPI, "/fapi/v1/depth", {"symbol": symbol, "limit": 20})
            t = req_json(FAPI, "/fapi/v1/ticker/bookTicker", {"symbol": symbol})
            oi_now = float(req_json(FAPI, "/fapi/v1/openInterest", {"symbol": symbol})["openInterest"])
        except HTTPError as e:
            if not is_451(e):
                raise
            d = req_json(SPOT, "/api/v3/depth", {"symbol": symbol, "limit": 20})
            t = req_json(SPOT, "/api/v3/ticker/bookTicker", {"symbol": symbol})
            oi_now = None

    bid_qty = sum(float(x[1]) for x in d["bids"])
    ask_qty = sum(float(x[1]) for x in d["asks"])
    tot = bid_qty + ask_qty
    imb = (bid_qty - ask_qty) / tot if tot else 0.0
    oi_chg = ((oi_now / prev_oi) - 1.0) * 100.0 if (oi_now and prev_oi) else None
    return Micro(float(t["bidPrice"]), float(t["askPrice"]), imb, oi_chg), oi_now


@st.cache_data(ttl=1800, show_spinner=False)
def load_symbols() -> tuple[list[str], str]:
    if FORCE_SPOT:
        ex = req_json(SPOT, "/api/v3/exchangeInfo", {})
        active = {
            s["symbol"]
            for s in ex.get("symbols", [])
            if s.get("status") == "TRADING"
            and s.get("quoteAsset") == "USDT"
            and s.get("isSpotTradingAllowed", True)
        }
        tk = req_json(SPOT, "/api/v3/ticker/24hr", {})
        source = "Spot (forced)"
    else:
        try:
            ex = req_json(FAPI, "/fapi/v1/exchangeInfo", {})
            active = {
                s["symbol"]
                for s in ex.get("symbols", [])
                if s.get("status") == "TRADING"
                and s.get("contractType") == "PERPETUAL"
                and s.get("quoteAsset") == "USDT"
            }
            tk = req_json(FAPI, "/fapi/v1/ticker/24hr", {})
            source = "Futures"
        except HTTPError as e:
            if not is_451(e):
                raise
            ex = req_json(SPOT, "/api/v3/exchangeInfo", {})
            active = {
                s["symbol"]
                for s in ex.get("symbols", [])
                if s.get("status") == "TRADING"
                and s.get("quoteAsset") == "USDT"
                and s.get("isSpotTradingAllowed", True)
            }
            tk = req_json(SPOT, "/api/v3/ticker/24hr", {})
            source = "Spot fallback (Futures 451)"

    vol = {x["symbol"]: float(x.get("quoteVolume", 0)) for x in tk if x.get("symbol") in active}
    ordered = sorted(active, key=lambda s: vol.get(s, 0.0), reverse=True)
    return ordered, source


# ---------------- 50 Features ----------------
def build_50_features(one: list[Candle], five: list[Candle], micro: Micro) -> dict[str, float]:
    c = [x.close for x in one]
    o = [x.open for x in one]
    h = [x.high for x in one]
    l = [x.low for x in one]
    v = [x.volume for x in one]
    tb = [x.taker_buy_volume for x in one]
    c5 = [x.close for x in five]
    h5 = [x.high for x in five]
    l5 = [x.low for x in five]
    v5 = [x.volume for x in five]

    # base indicators
    ema9 = ema(c, 9)
    ema20 = ema(c, 20)
    ema50 = ema(c, 50)
    ema100 = ema(c, 100)
    rsi7 = rsi(c, 7)
    rsi14 = rsi(c, 14)
    macdh = macd_hist(c)
    atr14 = atr(h, l, c, 14)
    z20 = zscore(c, 20)
    vw20 = vwap_last(h, l, c, v, 20)
    mean_v20 = sum(v[-20:]) / 20 if len(v) >= 20 else (sum(v) / max(1, len(v)))
    mean_v50 = sum(v[-50:]) / 50 if len(v) >= 50 else (sum(v) / max(1, len(v)))

    feats: dict[str, float] = {}

    # 1-10 returns
    horizons = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
    for i, n in enumerate(horizons, start=1):
        feats[f"ret_{n}"] = pct_change(c[-1], c[-1 - n]) if len(c) > n else 0.0

    # 11-15 candle structure
    last_range = (h[-1] - l[-1]) if h[-1] != l[-1] else 1e-9
    feats["body_ratio"] = abs(c[-1] - o[-1]) / last_range
    feats["upper_wick_ratio"] = (h[-1] - max(c[-1], o[-1])) / last_range
    feats["lower_wick_ratio"] = (min(c[-1], o[-1]) - l[-1]) / last_range
    feats["close_pos_in_range"] = (c[-1] - l[-1]) / last_range
    feats["hl_spread_pct"] = pct_change(h[-1], l[-1])

    # 16-22 MA distances/slopes
    feats["dist_ema9"] = pct_change(c[-1], ema9[-1])
    feats["dist_ema20"] = pct_change(c[-1], ema20[-1])
    feats["dist_ema50"] = pct_change(c[-1], ema50[-1])
    feats["dist_ema100"] = pct_change(c[-1], ema100[-1])
    feats["slope_ema20_5"] = pct_change(ema20[-1], ema20[-6]) if len(ema20) > 6 else 0.0
    feats["slope_ema50_5"] = pct_change(ema50[-1], ema50[-6]) if len(ema50) > 6 else 0.0
    feats["ema20_over_50"] = pct_change(ema20[-1], ema50[-1])

    # 23-28 oscillators
    feats["rsi7"] = rsi7[-1] / 100.0
    feats["rsi14"] = rsi14[-1] / 100.0
    feats["rsi_delta"] = (rsi14[-1] - rsi14[-4]) / 100.0 if len(rsi14) > 4 else 0.0
    feats["macdh"] = macdh[-1]
    feats["macdh_delta"] = (macdh[-1] - macdh[-2]) if len(macdh) > 1 else 0.0
    feats["z20"] = z20

    # 29-34 volatility/range
    feats["atr14_pct"] = atr14 / c[-1] if c[-1] else 0.0
    feats["range20_pct"] = pct_change(max(h[-20:]), min(l[-20:])) if len(h) >= 20 else 0.0
    feats["std20_ret"] = float(pd.Series(c).pct_change().tail(20).std() or 0.0)
    feats["std50_ret"] = float(pd.Series(c).pct_change().tail(50).std() or 0.0)
    feats["bb_width_proxy"] = (2 * (float(pd.Series(c).tail(20).std() or 0.0))) / (float(pd.Series(c).tail(20).mean() or 1e-9))
    feats["atr_ratio_5_20"] = (
        (sum([abs(c[-i] - c[-i - 1]) for i in range(1, 6)]) / 5) /
        (sum([abs(c[-i] - c[-i - 1]) for i in range(1, 21)]) / 20 + 1e-9)
        if len(c) > 21 else 1.0
    )

    # 35-40 volume/taker
    feats["vol_ratio_20"] = v[-1] / (mean_v20 + 1e-9)
    feats["vol_ratio_50"] = v[-1] / (mean_v50 + 1e-9)
    feats["vol_trend_5"] = (sum(v[-5:]) / 5) / ((sum(v[-20:]) / 20) + 1e-9) if len(v) >= 20 else 1.0
    feats["taker_ratio"] = (tb[-1] / v[-1]) if v[-1] > 0 else 0.5
    feats["taker_trend_5"] = (
        (sum([(tb[-i] / v[-i]) if v[-i] > 0 else 0.5 for i in range(1, 6)]) / 5)
        if len(v) >= 6 else 0.5
    )
    feats["vwap_dev_bps"] = ((c[-1] / vw20) - 1.0) * 10000.0 if vw20 > 0 else 0.0

    # 41-45 microstructure
    feats["spread_bps"] = micro.spread_bps
    feats["imbalance"] = micro.imbalance
    feats["oi_change_pct"] = micro.oi_change_pct if micro.oi_change_pct is not None else 0.0
    feats["mid_move_1"] = pct_change((micro.bid + micro.ask) / 2.0, c[-2]) if len(c) > 2 else 0.0
    feats["book_pressure"] = micro.imbalance / (micro.spread_bps + 1e-9)

    # 46-50 multi-timeframe coherence
    ema20_5 = ema(c5, 20)
    ema50_5 = ema(c5, 50)
    rsi5 = rsi(c5, 14)
    feats["mtf_trend"] = pct_change(ema20_5[-1], ema50_5[-1]) if len(ema50_5) > 0 else 0.0
    feats["mtf_rsi"] = rsi5[-1] / 100.0
    feats["mtf_ret_5"] = pct_change(c5[-1], c5[-6]) if len(c5) > 6 else 0.0
    feats["mtf_range_20"] = pct_change(max(h5[-20:]), min(l5[-20:])) if len(h5) >= 20 else 0.0
    feats["mtf_vol_ratio"] = (v5[-1] / ((sum(v5[-20:]) / 20) + 1e-9)) if len(v5) >= 20 else 1.0

    return feats


# ---------------- DL bonus from 50 features ----------------
def dl_bonus_from_features(features: dict[str, float], side: str, enabled: bool) -> tuple[float, float, str]:
    if not enabled:
        return 0.0, 0.5, "DL kapalı"

    # feature normalization helpers
    def clip(x, lo, hi):
        return max(lo, min(hi, x))

    # pseudo-model (lightweight logistic score from 50 features)
    x = features
    score_raw = 0.0
    score_raw += clip(x["ret_3"] * 120, -3, 3) * 0.10
    score_raw += clip(x["ret_8"] * 80, -3, 3) * 0.08
    score_raw += clip(x["dist_ema20"] * 200, -3, 3) * 0.10
    score_raw += clip((x["rsi14"] - 0.5) * 6, -3, 3) * 0.08
    score_raw += clip(x["macdh"] * 400, -3, 3) * 0.08
    score_raw += clip(x["macdh_delta"] * 500, -3, 3) * 0.07
    score_raw += clip(x["vol_ratio_20"] - 1.0, -2, 3) * 0.10
    score_raw += clip(x["taker_ratio"] - 0.5, -1, 1) * 0.20
    score_raw += clip(x["imbalance"] * 5, -3, 3) * 0.12
    score_raw += clip(x["mtf_trend"] * 150, -3, 3) * 0.07

    p_long = 1.0 / (1.0 + math.exp(-score_raw))
    p = p_long if side == "LONG" else (1.0 - p_long)
    bonus = clip((p - 0.5) * 20.0, 0.0, 10.0)  # 0..10
    return bonus, p, f"DL aktif (p={p:.3f}, bonus={bonus:.2f})"


# ---------------- Signal engine ----------------
def evaluate_symbol(symbol: str, one: list[Candle], five: list[Candle], micro: Micro, use_dl: bool) -> dict[str, Signal]:
    if len(one) < 120 or len(five) < 120:
        return {}

    c = [x.close for x in one]
    h = [x.high for x in one]
    l = [x.low for x in one]
    v = [x.volume for x in one]
    c5 = [x.close for x in five]

    e20 = ema(c, 20)[-1]
    e20_5 = ema(c5, 20)[-1]
    e50_5 = ema(c5, 50)[-1]
    r = rsi(c, 7)[-1]
    mh = macd_hist(c)
    a = atr(h, l, c, 14)
    z = zscore(c, 20)
    vw = vwap_last(h, l, c, v, 20)
    entry = c[-1]
    atr_bps = (a / entry) * 10000 if entry > 0 else 9999
    vwap_dev = ((entry / vw) - 1.0) * 10000 if vw > 0 else 0.0
    mean_vol = sum(v[-21:-1]) / 20.0

    prev_high = max(h[-21:-1])
    prev_low = min(l[-21:-1])
    taker_ratio = one[-1].taker_buy_volume / one[-1].volume if one[-1].volume > 0 else 0.5
    spread_ok = micro.spread_bps <= 6.0  # spot için biraz gevşek

    quality = {
        "Spread": spread_ok,
        "VWAPDev": abs(vwap_dev) <= 60.0,
        "ZScore": abs(z) <= 3.2,
        "ATRRegime": 1.0 <= atr_bps <= 120.0,
    }
    q_pass = sum(quality.values())

    features = build_50_features(one, five, micro)

    out: dict[str, Signal] = {}
    for side in ("LONG", "SHORT"):
        if side == "LONG":
            checks = {
                "Trend": e20_5 > e50_5,
                "EMA20": entry > e20,
                "RSI": 48 <= r <= 75,
                "MACD": mh[-1] > 0 and mh[-1] > mh[-2],
                "Volume": v[-1] > mean_vol * 1.20,
                "Breakout": entry > prev_high,
                "Orderbook": micro.imbalance >= 0.03,
                "Taker": taker_ratio >= 0.52,
            }
            early = checks["Trend"] and checks["MACD"] and checks["Volume"] and (c[-1] > c[-2] > c[-3])
            sl, tp1, tp2 = entry - 0.9 * a, entry + 0.9 * a, entry + 1.4 * a
        else:
            checks = {
                "Trend": e20_5 < e50_5,
                "EMA20": entry < e20,
                "RSI": 25 <= r <= 52,
                "MACD": mh[-1] < 0 and mh[-1] < mh[-2],
                "Volume": v[-1] > mean_vol * 1.20,
                "Breakout": entry < prev_low,
                "Orderbook": micro.imbalance <= -0.03,
                "Taker": taker_ratio <= 0.48,
            }
            early = checks["Trend"] and checks["MACD"] and checks["Volume"] and (c[-1] < c[-2] < c[-3])
            sl, tp1, tp2 = entry + 0.9 * a, entry - 0.9 * a, entry - 1.4 * a

        votes = {
            "trend": 1.0 if checks["Trend"] else 0.0,
            "breakout": 1.0 if checks["Breakout"] and checks["Volume"] else 0.0,
            "reversion": 1.0 if ((side == "LONG" and z < -1.3) or (side == "SHORT" and z > 1.3)) else 0.0,
            "micro": (float(checks["Orderbook"]) + float(checks["Taker"])) / 2.0,
            "quality": q_pass / 4.0,
            "early": 1.0 if early else 0.0,
        }
        w = {"trend": 0.22, "breakout": 0.20, "reversion": 0.10, "micro": 0.18, "quality": 0.15, "early": 0.10}
        vote_score = sum(votes[k] * w[k] for k in w)

        base_passed = sum(checks.values())
        total_passed = base_passed + q_pass

        bonus, p, _dl_state = dl_bonus_from_features(features, side, use_dl)
        score = round(base_passed * 5 + q_pass * 7 + vote_score * 22 + bonus * 2.2)
        score = max(0, min(score, 100))

        out[side] = Signal(
            symbol=symbol,
            side=side,
            score=score,
            early_uptrend=early if side == "LONG" else False,
            entry=entry,
            tp1=tp1,
            tp2=tp2,
            sl=sl,
            base_passed=base_passed,
            quality_passed=q_pass,
            total_passed=total_passed,
            checks=checks,
            quality=quality,
            votes=votes,
            spread_bps=micro.spread_bps,
            dl_bonus=bonus,
            dl_prob=p,
            features_count=len(features),
        )
    return out


# ---------------- Telegram ----------------
def send_telegram(token: str, chat_id: str, text: str) -> None:
    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
    with urlopen(req, timeout=10):
        pass


def signal_text(sig: Signal) -> str:
    checks = "\n".join(f"{html.escape(k):12} {'✅' if v else '❌'}" for k, v in sig.checks.items())
    header = "🚀 EARLY UPTREND" if sig.early_uptrend else "⚠️ SIGNAL"
    return (
        f"<b>{header}</b>\n"
        f"<b>{sig.symbol} — {sig.side}</b>\n"
        f"Skor: <b>{sig.score}/100</b> (DL bonus {sig.dl_bonus:.2f}, p={sig.dl_prob:.3f})\n"
        f"Base: {sig.base_passed}/8 | Kalite: {sig.quality_passed}/4 | Toplam: {sig.total_passed}\n"
        f"Spread: {sig.spread_bps:.2f} bps | Feature: {sig.features_count}\n"
        f"Entry: <code>{sig.entry:.6f}</code>\nTP1: <code>{sig.tp1:.6f}</code>\nTP2: <code>{sig.tp2:.6f}</code>\nSL: <code>{sig.sl:.6f}</code>\n\n"
        f"<pre>{checks}</pre>\n"
        f"<i>Yatırım tavsiyesi değildir.</i>"
    )


# ---------------- UI ----------------
st.set_page_config(page_title="Enterprise Signal Radar", page_icon="📡", layout="wide")
st.title("📡 Enterprise Signal Radar")
st.caption("Sinyal sistemi: Spot/Futures + 50 feature + DL proxy + 10k mum analiz")

with st.sidebar:
    st.header("API & Güvenlik")
    api_key = st.text_input("Binance API Key", os.getenv("BINANCE_API_KEY", ""), type="password")
    api_secret = st.text_input("Binance API Secret", os.getenv("BINANCE_API_SECRET", ""), type="password")

    st.info(f"Mode: {'SPOT (FORCED)' if FORCE_SPOT else 'FUTURES/Auto-fallback'}")

    if st.button("Futures API Test (Signed)", disabled=FORCE_SPOT):
        if not api_key or not api_secret:
            st.error("API key ve secret gir.")
        else:
            ok, msg = signed_futures_probe(api_key, api_secret, FAPI)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    st.header("Tarama")
    symbols, source = load_symbols()
    st.caption(f"Veri kaynağı: {source}")
    symbol = st.selectbox("Detay paritesi", symbols, index=0 if symbols else None)
    scan_all = st.toggle("Hareketli coin tara", True)
    batch = st.slider("Tur başına coin", 3, 15, 6, 1)
    refresh = st.slider("Yenileme (sn)", 10, 120, 30, 5)
    live = st.toggle("Canlı yenileme", True)

    st.header("Analiz")
    one_limit = st.slider("1m mum sayısı", 500, 10000, 10000, 500)
    five_limit = st.slider("5m mum sayısı", 500, 10000, 5000, 500)

    st.header("AI")
    use_dl = st.toggle("Derin öğrenme skor katkısı", True)

    st.header("Telegram")
    tg_token = st.text_input("Telegram Bot Token", os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
    tg_chat = st.text_input("Telegram Chat ID", os.getenv("TELEGRAM_CHAT_ID", ""))
    auto_send = st.toggle("Uygun sinyali otomatik gönder", False)

if "oi" not in st.session_state:
    st.session_state.oi = {}
if "offset" not in st.session_state:
    st.session_state.offset = 0
if "sent_keys" not in st.session_state:
    st.session_state.sent_keys = set()


def scan_one(sym: str):
    one = fetch_klines(sym, "1m", limit=one_limit)
    five = fetch_klines(sym, "5m", limit=five_limit)
    micro, oi = fetch_micro(sym, st.session_state.oi.get(sym))
    sigs = evaluate_symbol(sym, one, five, micro, use_dl=use_dl)
    return one, five, micro, oi, sigs


run_every = refresh if live else None


@st.fragment(run_every=run_every)
def dashboard():
    if not symbols:
        st.error("Sembol listesi boş.")
        return

    if scan_all:
        off = st.session_state.offset % len(symbols)
        radar = [symbols[(off + i) % len(symbols)] for i in range(min(batch, len(symbols)))]
    else:
        off = 0
        radar = [symbol]

    targets = list(dict.fromkeys([symbol, *radar]))
    packets, errors = {}, {}

    with ThreadPoolExecutor(max_workers=min(6, len(targets))) as ex:
        fmap = {ex.submit(scan_one, s): s for s in targets}
        for f in as_completed(fmap):
            s = fmap[f]
            try:
                packets[s] = f.result()
            except Exception as e:
                errors[s] = str(e)

    if symbol not in packets:
        st.error(f"Seçili coin verisi alınamadı: {errors.get(symbol, 'bilinmeyen hata')}")
        return

    one, _, micro, _, sigs = packets[symbol]
    for s, p in packets.items():
        st.session_state.oi[s] = p[3]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Son fiyat", f"{one[-1].close:,.6f}")
    c2.metric("Spread", f"{micro.spread_bps:.2f} bps")
    c3.metric("Güncelleme", datetime.now().strftime("%H:%M:%S"))
    c4.metric("1m mum", f"{len(one)}")

    df_price = pd.DataFrame(
        {"Fiyat": [x.close for x in one[-500:]]},
        index=pd.to_datetime([x.open_time for x in one[-500:]], unit="ms"),
    )
    st.line_chart(df_price, height=280)

    rows = []
    eligible: list[Signal] = []
    for s in radar:
        if s not in packets:
            continue
        _, _, m, _, res = packets[s]
        best = max(res.values(), key=lambda x: x.score, default=None)
        if not best:
            continue
        ok = best.score >= 70 and best.base_passed >= 5 and best.quality_passed >= 2
        if ok:
            eligible.append(best)
        rows.append(
            {
                "Parite": s,
                "Yön": best.side,
                "Skor": best.score,
                "DL p": round(best.dl_prob, 3),
                "Feature": best.features_count,
                "EarlyUptrend": "EVET" if best.early_uptrend else "HAYIR",
                "Base": best.base_passed,
                "Kalite": best.quality_passed,
                "Spread(bps)": round(m.spread_bps, 2),
                "Durum": "UYGUN" if ok else "BEKLE",
            }
        )

    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values("Skor", ascending=False), hide_index=True, use_container_width=True)

    t1, t2 = st.tabs(["LONG", "SHORT"])
    for tab, side in [(t1, "LONG"), (t2, "SHORT")]:
        with tab:
            sig = sigs.get(side)
            if not sig:
                st.warning("Yeterli veri yok.")
                continue
            st.metric(f"{side} Skor", f"{sig.score}/100")
            st.write("Entry / TP / SL", {"entry": sig.entry, "tp1": sig.tp1, "tp2": sig.tp2, "sl": sig.sl})
            st.write("Algoritma Oyları", sig.votes)
            st.write("DL", {"prob": sig.dl_prob, "bonus": sig.dl_bonus, "features": sig.features_count})

            if st.button(f"{side} Telegram Gönder", key=f"tg_{side}", disabled=not (tg_token and tg_chat)):
                try:
                    send_telegram(tg_token, tg_chat, signal_text(sig))
                    st.success("Telegram gönderildi.")
                except Exception as e:
                    st.error(f"Gönderim hatası: {e}")

    if auto_send and eligible and tg_token and tg_chat:
        best = max(eligible, key=lambda x: (x.early_uptrend, x.score))
        candle_key = (best.symbol, best.side, one[-1].open_time)
        if candle_key not in st.session_state.sent_keys:
            try:
                send_telegram(tg_token, tg_chat, signal_text(best))
                st.session_state.sent_keys.add(candle_key)
                st.toast(f"Otomatik sinyal: {best.symbol} {best.side}", icon="📨")
            except Exception as e:
                st.error(f"Otomatik Telegram hatası: {e}")

    if scan_all and symbols:
        st.session_state.offset = (off + len(radar)) % len(symbols)

    if errors:
        with st.expander("Hata Detayları"):
            st.json(errors)


dashboard()
st.caption("Yatırım tavsiyesi değildir. Bu uygulama sinyal amaçlıdır, otomatik emir açmaz.")
