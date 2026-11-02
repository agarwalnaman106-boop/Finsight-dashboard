"""Formatting helpers shared across the app."""
import math
import numpy as np

CURRENCY = {"symbol": "₹", "unit": "Cr", "indian": True}


def set_currency(symbol="₹", unit="Cr", indian=True):
    CURRENCY.update(symbol=symbol, unit=unit, indian=indian)


def _indian_group(n: int) -> str:
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        out = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + out


def num(x, d=0) -> str:
    """Plain number with thousands grouping (Indian or international)."""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "–"
    if CURRENCY["indian"] and d == 0:
        return _indian_group(int(round(x)))
    if CURRENCY["indian"]:
        whole = int(math.trunc(x))
        frac = f"{abs(x) - abs(whole):.{d}f}"[1:]
        sign = "-" if x < 0 and whole == 0 else ""
        return sign + _indian_group(whole) + frac
    return f"{x:,.{d}f}"


def money(x, d=0, unit=True) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "–"
    s = f"{'-' if x < 0 else ''}{CURRENCY['symbol']}{num(abs(x), d)}"
    return s + (f" {CURRENCY['unit']}" if unit else "")


def pct(x, d=1, sign=False) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "–"
    return f"{x:+.{d}f}%" if sign else f"{x:.{d}f}%"


def mult(x, d=1) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "–"
    return f"{x:.{d}f}x"


def safe_div(a, b):
    try:
        if b is None or a is None:
            return np.nan
        if isinstance(b, (int, float, np.floating)) and (b == 0 or math.isnan(b)):
            return np.nan
        return a / b
    except Exception:
        return np.nan


def is_nan(x) -> bool:
    return x is None or (isinstance(x, (float, np.floating)) and (math.isnan(x) or math.isinf(x)))
