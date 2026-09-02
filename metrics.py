"""純計算：把 fetch_data 抓到的原始資料轉成一列指標。沒有任何網路存取。"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

import config

GROUPS = ["顯著高估", "高估~均值", "均值~低估", "顯著低估", "無法判讀"]

NA = "N/A"


# ---------------------------------------------------------------- 小工具
def _valid(x: Any) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def fmt(x: Any, digits: int = 2, suffix: str = "") -> str:
    """數字格式化；None → N/A。"""
    if not _valid(x):
        return NA
    return f"{x:,.{digits}f}{suffix}"


# ---------------------------------------------------------------- PE
def compute_pe_stats(closes: pd.Series, eps: float | None) -> dict[str, Any]:
    """90 天 PE 序列的統計量與估值價。EPS 缺失或 <= 0 → 全部 None。"""
    empty = {"pe_now": None, "pe_mean": None, "pe_median": None, "pe_std": None,
             "pe_sigma": None, "price_low": None, "price_fair": None, "price_high": None,
             "pe_days": 0}
    if not _valid(eps) or eps <= 0 or closes is None or closes.empty:
        return empty

    pe = (closes / eps).dropna()
    if len(pe) < 5:
        return empty

    mean = float(pe.mean())
    median = float(pe.median())
    std = float(pe.std(ddof=1))
    pe_now = float(pe.iloc[-1])
    sigma = (pe_now - mean) / std if std > 0 else None

    return {
        "pe_now": pe_now,
        "pe_mean": mean,
        "pe_median": median,
        "pe_std": std,
        "pe_sigma": sigma,
        "price_low": (mean - std) * eps,
        "price_fair": mean * eps,
        "price_high": (mean + std) * eps,
        "pe_days": int(len(pe)),
    }


def classify(sigma: float | None) -> str:
    if not _valid(sigma):
        return "無法判讀"
    k = config.SIGMA_THRESHOLD
    if sigma > k:
        return "顯著高估"
    if sigma > 0:
        return "高估~均值"
    if sigma > -k:
        return "均值~低估"
    return "顯著低估"


# ---------------------------------------------------------------- 其他指標
def compute_pcf(price: float, ocf: float | None, shares: float | None) -> float | None:
    if not (_valid(ocf) and _valid(shares)) or shares <= 0 or ocf <= 0:
        return None
    return price / (ocf / shares)


def compute_peg(peg: float | None, forward_pe: float | None, growth: float | None) -> float | None:
    if _valid(peg):
        return peg
    if _valid(forward_pe) and _valid(growth) and growth > 0:
        return forward_pe / (growth * 100)
    return None


def normalize_dividend_yield(dy: float | None, div_rate: float | None, price: float) -> float | None:
    """統一成百分比。回傳 None 代表無股息。

    yfinance 不同版本的 dividendYield 有時是 0.0052（小數）、有時是 0.52（百分比），
    這裡用 dividendRate / price 交叉比對，挑最接近的解釋。
    """
    if not _valid(dy) or dy <= 0:
        return None
    if _valid(div_rate) and div_rate > 0 and price > 0:
        ref = div_rate / price * 100
        return min((dy, dy * 100), key=lambda c: abs(c - ref))
    # 沒有參考值：近期 yfinance 已改為百分比，直接採用
    return dy


def compute_52w_position(price: float, low: float | None, high: float | None) -> float | None:
    if not (_valid(low) and _valid(high)) or high <= low:
        return None
    return (price - low) / (high - low) * 100


def _seed_value(seed: dict[str, Any], key: str, today: date, as_of: date | None) -> float | None:
    """讀種子的 high / low，並判斷是否過期。回傳小數形式的 IV，過期或缺失回 None。"""
    v = seed.get(key)
    if not _valid(v) or v <= 0:
        return None
    v = float(v)
    if v > 3:            # 54.93 這種百分比寫法 → 0.5493
        v /= 100
    raw_date = seed.get(f"{key}_date") or (as_of.isoformat() if as_of else None)
    if raw_date:
        try:
            d = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except ValueError:
            d = None
        if d is not None and (today - d).days > config.IV_SEED_MAX_AGE_DAYS:
            return None
    return v


def compute_iv_rank(
    iv_today: float | None,
    past_ivs: list[float],
    seed: dict[str, Any] | None = None,
    today: date | None = None,
    as_of: date | None = None,
) -> tuple[float | None, int, bool]:
    """IV Rank = (今日 IV - 區間最低 IV) / (區間最高 IV - 區間最低 IV) × 100。

    past_ivs：history.csv 裡該股票過去各日的 IV（不含今天），只取最近 IVR_LOOKBACK_DAYS - 1 筆。
    seed：iv_seeds.json 裡手動填的 52 週高低點；未過期的種子會和累積資料一起取極值，
          有種子時不受 IVR_MIN_DAYS 限制，馬上就能算。
    回傳 (IVR 百分比或 None, 累積資料天數含今天, 是否用到種子)。
    """
    if not _valid(iv_today):
        return None, 0, False
    today = today or date.today()
    window = [v for v in past_ivs if _valid(v) and v > 0][-(config.IVR_LOOKBACK_DAYS - 1):]
    window.append(iv_today)
    n = len(window)

    seed_hi = seed_lo = None
    if seed:
        seed_hi = _seed_value(seed, "high", today, as_of)
        seed_lo = _seed_value(seed, "low", today, as_of)
    seeded = seed_hi is not None or seed_lo is not None

    if not seeded and n < config.IVR_MIN_DAYS:
        return None, n, False

    lo = min(window + ([seed_lo] if seed_lo is not None else []))
    hi = max(window + ([seed_hi] if seed_hi is not None else []))
    if hi <= lo:
        return None, n, seeded
    ivr = (iv_today - lo) / (hi - lo) * 100
    return max(0.0, min(100.0, ivr)), n, seeded


def format_ivr(iv: dict[str, Any] | None, ivr: float | None, n_days: int, seeded: bool = False) -> str:
    """IV Rank 欄位的顯示字串。"""
    if not iv:
        return NA
    status = iv.get("status")
    if status == "no_market":
        return "無選擇權市場"
    if status == "timeout":
        return "逾時"
    if status != "ok":
        return NA
    if ivr is None:
        if not seeded and n_days < config.IVR_MIN_DAYS:
            return f"資料累積中 ({n_days}/{config.IVR_MIN_DAYS} 天)"
        return NA
    text = f"{ivr:.0f}%"
    notes = []
    if seeded:
        notes.append("種子")
    elif n_days < config.IVR_LOOKBACK_DAYS:
        notes.append(f"{n_days} 天資料")
    if iv.get("out_of_range"):
        notes.append(f"到期 {iv['days']} 天")
    return f"{text} ({'，'.join(notes)})" if notes else text


# ---------------------------------------------------------------- 組合成一列
def build_row(
    raw: dict[str, Any],
    past_ivs: list[float] | None = None,
    seed: dict[str, Any] | None = None,
    today: date | None = None,
    seed_as_of: date | None = None,
) -> dict[str, Any]:
    price = raw["price"]
    pe = compute_pe_stats(raw["closes"], raw["eps"])
    iv = raw.get("iv") or {}
    iv_today = iv.get("iv") if iv.get("status") == "ok" else None
    ivr, ivr_days, seeded = compute_iv_rank(iv_today, past_ivs or [], seed, today, seed_as_of)

    row: dict[str, Any] = {
        "symbol": raw["symbol"],
        "name": raw["name"],
        "currency": raw["currency"],
        "price": price,
        "eps": raw["eps"],
        **pe,
        "group": classify(pe["pe_sigma"]),
        "forward_pe": raw["forward_pe"],
        "pb": raw["pb"],
        "pcf": compute_pcf(price, raw["operating_cashflow"], raw["shares_outstanding"]),
        "peg": compute_peg(raw["peg"], raw["forward_pe"], raw["earnings_growth"]),
        "dividend_yield": normalize_dividend_yield(raw["dividend_yield"], raw["dividend_rate"], price),
        "ev_ebitda": raw["ev_ebitda"],
        "wk52_high": raw["wk52_high"],
        "wk52_low": raw["wk52_low"],
        "wk52_pos": compute_52w_position(price, raw["wk52_low"], raw["wk52_high"]),
        "iv": iv_today,
        "iv_days": iv.get("days") if iv.get("status") == "ok" else None,
        "iv_expiry": iv.get("expiry") if iv.get("status") == "ok" else None,
        "iv_status": iv.get("status") or "missing",
        "iv_rank": ivr,
        "ivr_days": ivr_days,
        "ivr_seeded": seeded,
        "ivr_display": format_ivr(iv, ivr, ivr_days, seeded),
    }
    return row


# 寫入 history.csv 的欄位順序
HISTORY_COLUMNS = [
    "date", "symbol", "name", "currency", "price", "eps",
    "pe_now", "pe_mean", "pe_median", "pe_std", "pe_sigma",
    "price_low", "price_fair", "price_high", "group",
    "forward_pe", "pb", "pcf", "peg", "dividend_yield", "ev_ebitda",
    "wk52_low", "wk52_high", "wk52_pos",
    "iv", "iv_days", "iv_expiry", "iv_status", "iv_rank", "ivr_days",
]


def rows_to_history_frame(rows: list[dict[str, Any]], today: str) -> pd.DataFrame:
    records = []
    for r in rows:
        rec = {c: r.get(c) for c in HISTORY_COLUMNS if c != "date"}
        rec["date"] = today
        records.append(rec)
    df = pd.DataFrame.from_records(records, columns=HISTORY_COLUMNS)
    num_cols = [c for c in HISTORY_COLUMNS if c not in ("date", "symbol", "name", "currency", "group", "iv_expiry", "iv_status")]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").round(4)
    return df.replace({np.nan: None})
