"""Trend/Reversal Engine v2 for NordicSignal.

Produces a separate reversal-evidence score (0-100) and regime label. It does
not alter the aggregate stock score. The goal is to detect bottoming and early
trend reversals before slower trend-following signals confirm.
"""

from __future__ import annotations
from math import isnan


def _num(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if isnan(value) else value


def _ema(values, period):
    values = [float(v) for v in values if _num(v) is not None]
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = alpha * value + (1.0 - alpha) * ema
    return ema


def _ema_series(values, period):
    """Return EMA values aligned to input in O(n), seeded like _ema()."""
    values = [float(v) for v in values]
    out = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1.0)
    ema = sum(values[:period]) / period
    out[period - 1] = ema
    for i in range(period, len(values)):
        ema = alpha * values[i] + (1.0 - alpha) * ema
        out[i] = ema
    return out


def _rsi(values, period=14):
    values = [float(v) for v in values if _num(v) is not None]
    if len(values) <= period:
        return None
    sample = values[-(period + 1):]
    gains = []
    losses = []
    for prev, cur in zip(sample[:-1], sample[1:]):
        delta = cur - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _macd_hist(values):
    values = [float(v) for v in values if _num(v) is not None]
    if len(values) < 35:
        return None, None
    fast_series = _ema_series(values, 12)
    slow_series = _ema_series(values, 26)
    macd_series = [
        fast_series[i] - slow_series[i]
        for i in range(len(values))
        if fast_series[i] is not None and slow_series[i] is not None
    ]
    if len(macd_series) < 10:
        return None, None
    signal = _ema(macd_series, 9)
    prev_signal = _ema(macd_series[:-1], 9)
    if signal is None:
        return None, None
    current = macd_series[-1] - signal
    previous = macd_series[-2] - prev_signal if prev_signal is not None else None
    return current, previous


def _swing_structure(closes):
    if len(closes) < 15:
        return {"higher_low": False, "higher_high": False}
    recent = closes[-15:]
    first_low = min(recent[:7])
    second_low = min(recent[7:12])
    first_high = max(recent[:10])
    second_high = max(recent[10:])
    return {
        "higher_low": second_low > first_low * 1.003,
        "higher_high": second_high > first_high * 1.003,
    }


def calculate_reversal(history):
    rows = [x for x in history or [] if isinstance(x, dict) and _num(x.get("close")) is not None]
    closes = [float(x["close"]) for x in rows]
    volumes = [_num(x.get("volume")) for x in rows]
    if len(closes) < 35:
        return {"score": None, "regime": "INSUFFICIENT_DATA", "confidence": "low", "reasons": [], "metrics": {}, "version": "2026-08-29-v2"}

    score = 0.0
    reasons = []

    ema8 = _ema(closes, 8)
    ema21 = _ema(closes, 21)
    ema8_prev = _ema(closes[:-1], 8)
    ema21_prev = _ema(closes[:-1], 21)
    if ema8 is not None and ema21 is not None:
        if ema8 > ema21:
            score += 16
            reasons.append("EMA8 over EMA21")
        if ema8_prev is not None and ema21_prev is not None and ema8_prev <= ema21_prev and ema8 > ema21:
            score += 10
            reasons.append("Fresh bullish EMA cross")

    rsi_now = _rsi(closes, 14)
    rsi_prev = _rsi(closes[:-3], 14) if len(closes) >= 18 else None
    if rsi_now is not None:
        if 42 <= rsi_now <= 65:
            score += 10
            reasons.append("RSI in recovery zone")
        elif rsi_now > 65:
            score += 5
        if rsi_prev is not None and rsi_prev < 40 and rsi_now >= 42:
            score += 10
            reasons.append("RSI recovered from weak area")

    hist_now, hist_prev = _macd_hist(closes)
    if hist_now is not None:
        if hist_now > 0:
            score += 12
            reasons.append("MACD histogram positive")
        if hist_prev is not None and hist_prev <= 0 < hist_now:
            score += 10
            reasons.append("Fresh bullish MACD turn")
        elif hist_prev is not None and hist_now > hist_prev:
            score += 5
            reasons.append("MACD momentum improving")

    structure = _swing_structure(closes)
    if structure["higher_low"]:
        score += 10
        reasons.append("Higher low")
    if structure["higher_high"]:
        score += 10
        reasons.append("Higher high")

    valid_volumes = [v for v in volumes[-21:-1] if v is not None and v > 0]
    latest_volume = volumes[-1] if volumes else None
    volume_ratio = None
    if latest_volume is not None and valid_volumes:
        avg_volume = sum(valid_volumes) / len(valid_volumes)
        if avg_volume > 0:
            volume_ratio = latest_volume / avg_volume
            if volume_ratio >= 2.0 and closes[-1] > closes[-2]:
                score += 10
                reasons.append("Strong bullish volume expansion")
            elif volume_ratio >= 1.5 and closes[-1] > closes[-2]:
                score += 6
                reasons.append("Bullish volume expansion")

    trailing_high = max(closes[-120:])
    drawdown_pct = ((closes[-1] / trailing_high) - 1.0) * 100.0 if trailing_high else 0.0
    if drawdown_pct <= -20 and (structure["higher_low"] or (hist_now is not None and hist_prev is not None and hist_now > hist_prev)):
        score += 6
        reasons.append("Reversal developing after deep drawdown")

    score = max(0.0, min(100.0, score))
    if score >= 75:
        regime = "CONFIRMED_UPTREND" if structure["higher_high"] and ema8 is not None and ema21 is not None and ema8 > ema21 else "EARLY_REVERSAL"
    elif score >= 55:
        regime = "EARLY_REVERSAL"
    elif score >= 35:
        regime = "BOTTOMING"
    else:
        regime = "FALLING_OR_WEAK"

    return {
        "score": round(score, 1),
        "regime": regime,
        "confidence": "high" if score >= 75 else "medium" if score >= 50 else "low",
        "reasons": reasons,
        "metrics": {
            "ema8": round(ema8, 4) if ema8 is not None else None,
            "ema21": round(ema21, 4) if ema21 is not None else None,
            "rsi14": round(rsi_now, 2) if rsi_now is not None else None,
            "macd_histogram": round(hist_now, 5) if hist_now is not None else None,
            "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
            "drawdown_pct": round(drawdown_pct, 2),
            "higher_low": structure["higher_low"],
            "higher_high": structure["higher_high"],
        },
        "version": "2026-08-29-v2",
    }


def install():
    return None


install()
