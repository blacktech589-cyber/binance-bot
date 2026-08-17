# -*- coding: utf-8 -*-
from __future__ import annotations

import os, json, math, html
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pandas as pd
import streamlit as st


# ---------- utils ----------
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

REST = os.getenv("BINANCE_FUTURES_REST", "https://fapi.binance.com")
SPOT = os.getenv("BINANCE_SPOT_REST", "https://data-api.binance.vision")


def get_json(path: str, params: dict, base: str = REST, timeout: float = 12.0):
    req = Request(f"{base}{path}?{urlencode(params)}", headers={"User-Agent": "signal-radar/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def is_451(e: Exception) -> bool:
    return isinstance(e, HTTPError) and e.code == 451


# ---------- indicators ----------
def ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    a = 2.0 / (period + 1)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(a * float(v) + (1 - a) * out[-1])
    return out


def rsi(values: Sequence[float], period: int = 7) -> list[float]:
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
        out.append(100.0 if l == 0 and g > 0 else 50.0 if l == 0 else 100.0 - 100.0 / (1 + g / l))
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
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    return ema(tr, period)[-1]


# ---------- models ----------
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


# ---------- rest ----------
def klines(symbol: str, interval: str, limit: int = 250) -> list[Candle]:
    p = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        rows = get_json("/fapi/v1/klines", p)
    except HTTPError as e:
        if not is_451(e):
            raise
        rows = get_json("/api/v3/klines", p, base=SPOT)
    return [Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9])) for r in rows[:-1]]


def snapshot(symbol: str, prev_oi: float | None):
    try:
        d = get_json("/fapi/v1/depth", {"symbol": symbol, "limit": 20})
        t = get_json("/fapi/v1/ticker/bookTicker", {"symbol": symbol})
        oi = float(get_json("/fapi/v1/openInterest", {"symbol": symbol})["openInterest"])
    except HTTPError as e:
        if not is_451(e):
            raise
        d = get_json("/api/v3/depth", {"symbol": symbol, "limit": 20}, base=SPOT)
        t = get_json("/api/v3/ticker/bookTicker", {"symbol": symbol}, base=SPOT)
        oi = None

    bid_qty = sum(float(x[1]) for x in d["bids"])
    ask_qty = sum(float(x[1]) for x in d["asks"])
    total = bid_qty + ask_qty
    imb = (bid_qty - ask_qty) / total if total else 0.0
    oi_chg = ((oi / prev_oi) - 1.0) * 100.0 if oi and prev_oi else None
    return Micro(float(t["bidPrice"]), float(t["askPrice"]), imb, oi_chg), oi


@st.cache_data(ttl=1800, show_spinner=False)
def symbols_catalog() -> tuple[list[str], str]:
    try:
        ex = get_json("/fapi/v1/exchangeInfo", {})
        active = {
            s["symbol"] for s in ex.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT"
        }
        ticks = get_json("/fapi/v1/ticker/24hr", {})
        src = "Futures"
    except HTTPError as e:
        if not is_451(e):
            raise
        ex = get_json("/api/v3/exchangeInfo", {}, base=SPOT)
        active = {
            s["symbol"] for s in ex.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT" and s.get("isSpotTradingAllowed", True)
        }
        ticks = get_json("/api/v3/ticker/24hr", {}, base=SPOT)
        src = "Spot fallback (451)"
    vols = {x["symbol"]: float(x.get("quoteVolume", 0)) for x in ticks if x.get("symbol") in active}
    return sorted(active, key=lambda s: vols.get(s, 0.0), reverse=True), src


# ---------- signal engine ----------
def evaluate(symbol: str, one: list[Candle], five: list[Candle], micro: Micro):
    if len(one) < 60 or len(five) < 60:
        return {}

    c = [x.close for x in one]
    h = [x.high for x in one]
    l = [x.low for x in one]
    v = [x.volume for x in one]
    c5 = [x.close for x in five]

    entry = c[-1]
    e20 = ema(c, 20)[-1]
    e20_5 = ema(c5, 20)[-1]
    e50_5 = ema(c5, 50)[-1]
    r = rsi(c, 7)[-1]
    m = macd_hist(c)
    a = atr(h, l, c, 14)
    z = zscore(c, 20)
    atr_bps = (a / entry) * 10000 if entry > 0 else 999

    mean_vol = sum(v[-21:-1]) / 20.0
    prev_high = max(h[-21:-1])
    prev_low = min(l[-21:-1])
    spread_ok = micro.spread_bps <= 2.5
    taker = one[-1].taker_buy_volume / one[-1].volume if one[-1].volume > 0 else 0.5

    quality = {
        "Spread": spread_ok,
        "ZScore": abs(z) <= 2.8,
        "ATR": 1.0 <= atr_bps <= 90.0,
        "MomentumClean": abs(m[-1]) >= abs(m[-2]) * 0.7 if len(m) > 2 else True,
    }
    q_pass = sum(quality.values())

    out = {}
    for side in ("LONG", "SHORT"):
        if side == "LONG":
            checks = {
                "Trend": e20_5 > e50_5,
                "EMA20": entry > e20,
                "RSI": 50 <= r <= 72,
                "MACD": m[-1] > 0 and m[-1] > m[-2],
                "Volume": v[-1] > mean_vol * 1.25,
                "Breakout": entry > prev_high,
                "Orderbook": micro.imbalance >= 0.05,
                "Taker": taker >= 0.53,
            }
            early = checks["Trend"] and checks["MACD"] and checks["Volume"] and (c[-1] > c[-2] > c[-3])
            sl, tp1, tp2 = entry - 0.8*a, entry + 0.8*a, entry + 1.2*a
        else:
            checks = {
                "Trend": e20_5 < e50_5,
                "EMA20": entry < e20,
                "RSI": 28 <= r <= 50,
                "MACD": m[-1] < 0 and m[-1] < m[-2],
                "Volume": v[-1] > mean_vol * 1.25,
                "Breakout": entry < prev_low,
                "Orderbook": micro.imbalance <= -0.05,
                "Taker": taker <= 0.47,
            }
            early = checks["Trend"] and checks["MACD"] and checks["Volume"] and (c[-1] < c[-2] < c[-3])
            sl, tp1, tp2 = entry + 0.8*a, entry - 0.8*a, entry - 1.2*a

        votes = {
            "trend": 1.0 if checks["Trend"] else 0.0,
            "breakout": 1.0 if checks["Breakout"] and checks["Volume"] else 0.0,
            "mean_reversion": 1.0 if ((side == "LONG" and z < -1.3) or (side == "SHORT" and z > 1.3)) else 0.0,
            "micro": (float(checks["Orderbook"]) + float(checks["Taker"])) / 2.0,
            "quality": q_pass / 4.0,
            "early_uptrend": 1.0 if early else 0.0,
        }
        w = {"trend": .22, "breakout": .20, "mean_reversion": .12, "micro": .20, "quality": .16, "early_uptrend": .10}
        vote_score = sum(votes[k] * w[k] for k in w)

        base = sum(checks.values())
        total = base + q_pass
        score = round(base*5 + q_pass*7 + vote_score*20)
        score = max(0, min(score, 100))

        out[side] = Signal(
            symbol=symbol, side=side, score=score, early_uptrend=early,
            entry=entry, tp1=tp1, tp2=tp2, sl=sl,
            base_passed=base, quality_passed=q_pass, total_passed=total,
            checks=checks, quality=quality, votes=votes, spread_bps=micro.spread_bps
        )
    return out


# ---------- telegram ----------
def send_telegram(token: str, chat_id: str, text: str) -> None:
    data = urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urlopen(req, timeout=10):
        pass


def format_signal(sig: Signal) -> str:
    checks = "\n".join(f"{html.escape(k):12} {'✅' if v else '❌'}" for k, v in sig.checks.items())
    early = "🚀 EARLY UPTREND" if sig.early_uptrend and sig.side == "LONG" else "⚠️ MOMENTUM"
    return (
        f"<b>{early}</b>\n"
        f"<b>{sig.symbol} — {sig.side}</b>\n"
        f"Skor: <b>{sig.score}/100</b>\n"
        f"Base: {sig.base_passed}/8 | Kalite: {sig.quality_passed}/4\n"
        f"Spread: {sig.spread_bps:.2f} bps\n"
        f"Entry: <code>{sig.entry:.6f}</code>\nTP1: <code>{sig.tp1:.6f}</code>\nTP2: <code>{sig.tp2:.6f}</code>\nSL: <code>{sig.sl:.6f}</code>\n\n"
        f"<pre>{checks}</pre>\n"
        f"<i>Yatırım tavsiyesi değildir.</i>"
    )


# ---------- UI ----------
st.set_page_config(page_title="Signal Radar", page_icon="📡", layout="wide")
st.title("📡 Binance Signal Radar (Trade Yok)")
st.caption("Sadece sinyal + Telegram. Otomatik alım/satım yok.")

with st.sidebar:
    all_symbols, source = symbols_catalog()
    if "fallback" in source.lower():
        st.warning(f"Veri kaynağı: {source}")
    else:
        st.success(f"Veri kaynağı: {source}")

    symbol = st.selectbox("Detay paritesi", all_symbols, index=0)
    scan_all = st.toggle("Tüm piyasayı tara", True)
    batch = st.slider("Tur başına coin", 5, 20, 10, 1)
    refresh = st.slider("Yenileme (sn)", 5, 60, 15, 1)
    live = st.toggle("Canlı yenileme", True)

    tg_token = st.text_input("Telegram bot token", os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
    tg_chat = st.text_input("Telegram chat ID", os.getenv("TELEGRAM_CHAT_ID", ""))
    auto_send = st.toggle("Uygun sinyali otomatik gönder", False)

if "oi" not in st.session_state:
    st.session_state.oi = {}
if "sent" not in st.session_state:
    st.session_state.sent = set()
if "offset" not in st.session_state:
    st.session_state.offset = 0


def scan_symbol(sym: str):
    one = klines(sym, "1m")
    five = klines(sym, "5m")
    micro, cur_oi = snapshot(sym, st.session_state.oi.get(sym))
    sigs = evaluate(sym, one, five, micro)
    return one, five, micro, cur_oi, sigs


run_every = refresh if live else None


@st.fragment(run_every=run_every)
def dashboard():
    if scan_all:
        off = st.session_state.offset % len(all_symbols)
        radar = [all_symbols[(off + i) % len(all_symbols)] for i in range(min(batch, len(all_symbols)))]
    else:
        off = 0
        radar = [symbol]

    targets = list(dict.fromkeys([symbol, *radar]))
    packets, errors = {}, {}

    with ThreadPoolExecutor(max_workers=min(6, len(targets))) as ex:
        future_map = {ex.submit(scan_symbol, s): s for s in targets}
        for f in as_completed(future_map):
            s = future_map[f]
            try:
                packets[s] = f.result()
            except Exception as e:
                errors[s] = str(e)

    if symbol not in packets:
        st.error(f"Seçili sembol verisi yok: {errors.get(symbol, 'hata')}")
        return

    one, _, micro, _, sigs = packets[symbol]
    for s, p in packets.items():
        st.session_state.oi[s] = p[3]

    a, b, c = st.columns(3)
    a.metric("Son fiyat", f"{one[-1].close:,.4f}")
    b.metric("Spread", f"{micro.spread_bps:.2f} bps")
    c.metric("Güncelleme", datetime.now().strftime("%H:%M:%S"))

    chart = pd.DataFrame({"Fiyat": [x.close for x in one[-120:]]}, index=pd.to_datetime([x.open_time for x in one[-120:]], unit="ms"))
    st.line_chart(chart, height=260)

    rows = []
    eligible = []
    for s in radar:
        if s not in packets:
            continue
        _, _, m, _, r = packets[s]
        best = max(r.values(), key=lambda x: x.score, default=None)
        if not best:
            continue
        ok = best.score >= 70 and best.base_passed >= 5 and best.quality_passed >= 2
        if ok:
            eligible.append(best)
        rows.append({
            "Parite": s,
            "Yön": best.side,
            "Skor": best.score,
            "Erken Yükseliş": "EVET" if best.early_uptrend else "HAYIR",
            "Base": best.base_passed,
            "Kalite": best.quality_passed,
            "Spread": round(m.spread_bps, 2),
            "Sinyal": "UYGUN" if ok else "BEKLE",
        })

    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values("Skor", ascending=False), hide_index=True, use_container_width=True)

    long_tab, short_tab = st.tabs(["LONG", "SHORT"])
    for tab, side in [(long_tab, "LONG"), (short_tab, "SHORT")]:
        with tab:
            sig = sigs.get(side)
            if not sig:
                st.warning("Yeterli veri yok.")
                continue
            st.metric(f"{side} Skor", f"{sig.score}/100")
            st.write("Entry / TP / SL", {"entry": sig.entry, "tp1": sig.tp1, "tp2": sig.tp2, "sl": sig.sl})
            st.write("Algoritma oyları", sig.votes)

            if st.button(f"{side} Telegram gönder", key=f"send_{side}", disabled=not (tg_token and tg_chat)):
                try:
                    send_telegram(tg_token, tg_chat, format_signal(sig))
                    st.success("Telegram gönderildi.")
                except Exception as e:
                    st.error(f"Gönderim hatası: {e}")

    if auto_send and eligible and tg_token and tg_chat:
        best = max(eligible, key=lambda x: (x.early_uptrend, x.score))
        key = (best.symbol, best.side, one[-1].open_time)
        if key not in st.session_state.sent:
            try:
                send_telegram(tg_token, tg_chat, format_signal(best))
                st.session_state.sent.add(key)
                st.toast(f"Otomatik sinyal gönderildi: {best.symbol} {best.side}", icon="📨")
            except Exception as e:
                st.error(f"Otomatik gönderim hatası: {e}")

    if scan_all and all_symbols:
        st.session_state.offset = (off + len(radar)) % len(all_symbols)

    if errors:
        with st.expander("Hatalar"):
            st.json(errors)


dashboard()
st.caption("Yatırım tavsiyesi değildir. Risk yönetimi olmadan işlem yapmayın.")
