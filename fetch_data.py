"""從 yfinance 抓取單一股票的原始資料。

設計原則：任何一檔股票、任何一個欄位失敗，都只影響該格 / 該列，
不會讓整批執行中斷。
"""
from __future__ import annotations

import math
import threading
import time
from datetime import date, datetime
from typing import Any

import pandas as pd
import yfinance as yf

import config


# ---------------------------------------------------------------- 工具
def load_tickers(path: str = config.TICKERS_FILE) -> list[str]:
    """讀 tickers.txt：一行一個代碼，忽略空行與 # 註解，去重並保持順序。"""
    seen: set[str] = set()
    tickers: list[str] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip().upper()
            if line and line not in seen:
                seen.add(line)
                tickers.append(line)
    return tickers


def _num(value: Any) -> float | None:
    """把 yfinance 給的值轉成 float；None / NaN / 非數字 → None。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


# ---------------------------------------------------------------- 基本資料
def fetch_basic(symbol: str) -> dict[str, Any]:
    """抓股價序列與 info 欄位。回傳 dict；若連股價都抓不到會 raise。"""
    t = yf.Ticker(symbol)

    hist = t.history(period=config.PRICE_HISTORY_PERIOD, auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist:
        raise RuntimeError("抓不到歷史股價（可能代碼錯誤或已下市）")
    closes: pd.Series = hist["Close"].dropna()
    if closes.empty:
        raise RuntimeError("歷史股價全為空值")
    closes = closes.tail(config.PE_WINDOW_DAYS)

    # info 有時會整包失敗，失敗就用空 dict，之後各欄位自然變 N/A
    try:
        info = t.info or {}
    except Exception as exc:  # noqa: BLE001
        print(f"  [{symbol}] info 抓取失敗，指標將顯示 N/A：{exc}")
        info = {}

    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    if price is None:
        price = float(closes.iloc[-1])

    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "currency": info.get("currency") or "",
        "price": price,
        "closes": closes,
        "eps": _num(info.get("trailingEps")),
        "forward_pe": _num(info.get("forwardPE")),
        "pb": _num(info.get("priceToBook")),
        "operating_cashflow": _num(info.get("operatingCashflow")),
        "shares_outstanding": _num(info.get("sharesOutstanding")),
        "peg": _num(info.get("pegRatio")),
        "earnings_growth": _num(info.get("earningsGrowth")),
        "dividend_yield": _num(info.get("dividendYield")),
        "dividend_rate": _num(info.get("dividendRate")),
        "ev_ebitda": _num(info.get("enterpriseToEbitda")),
        "wk52_high": _num(info.get("fiftyTwoWeekHigh")),
        "wk52_low": _num(info.get("fiftyTwoWeekLow")),
    }


# ---------------------------------------------------------------- 隱含波動率
def _fetch_iv_blocking(symbol: str, price: float) -> dict[str, Any]:
    """真正去抓選擇權鏈的函式，可能很慢，由 fetch_iv() 包 timeout 呼叫。"""
    t = yf.Ticker(symbol)
    expiries = list(t.options or [])
    if not expiries:
        return {"status": "no_market"}

    today = date.today()
    candidates: list[tuple[int, str]] = []
    for exp in expiries:
        try:
            d = datetime.strptime(exp, "%Y-%m-%d").date()
        except ValueError:
            continue
        days = (d - today).days
        if days >= 0:
            candidates.append((days, exp))
    if not candidates:
        return {"status": "no_market"}

    # 到期日最接近目標天數（30 天）
    days, expiry = min(candidates, key=lambda c: abs(c[0] - config.IV_TARGET_DAYS))

    chain = t.option_chain(expiry)
    calls = getattr(chain, "calls", None)
    if calls is None or calls.empty or "strike" not in calls or "impliedVolatility" not in calls:
        return {"status": "no_market"}

    calls = calls.copy()
    calls["_dist"] = (calls["strike"] - price).abs()
    calls = calls.sort_values("_dist")

    # 最接近平價的 call；若它的 IV 是 0 / NaN，往外找最多 3 檔履約價
    iv = None
    strike = None
    for _, row in calls.head(4).iterrows():
        v = _num(row["impliedVolatility"])
        if v is not None and v > 0:
            iv, strike = v, float(row["strike"])
            break
    if iv is None:
        return {"status": "no_market"}

    out_of_range = days < config.IV_MIN_DAYS or days > config.IV_MAX_DAYS
    return {
        "status": "ok",
        "iv": iv,                 # 小數，例如 0.42 = 42%
        "days": days,
        "expiry": expiry,
        "strike": strike,
        "out_of_range": out_of_range,
    }


def fetch_iv(symbol: str, price: float) -> dict[str, Any]:
    """帶 timeout 的 IV 抓取。逾時或任何錯誤都回傳 status，不會 raise。

    用 daemon 執行緒而不是 ThreadPoolExecutor：若網路真的卡死，
    daemon 執行緒不會阻止程式結束，主流程與後續 commit 步驟都能照常進行。
    """
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = _fetch_iv_blocking(symbol, price)
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    th = threading.Thread(target=worker, name=f"iv-{symbol}", daemon=True)
    th.start()
    th.join(timeout=config.IV_TIMEOUT_SEC)

    if th.is_alive():
        print(f"  [{symbol}] 選擇權抓取逾時（>{config.IV_TIMEOUT_SEC}s），跳過 IV")
        return {"status": "timeout"}
    if "error" in box:
        print(f"  [{symbol}] 選擇權抓取失敗，視為無選擇權市場：{box['error']}")
        return {"status": "no_market"}
    return box.get("result") or {"status": "no_market"}


# ---------------------------------------------------------------- 整合
def fetch_all(tickers: list[str]) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """逐檔抓取。回傳 (成功的原始資料列表, [(代碼, 失敗原因), ...])。"""
    results: list[dict[str, Any]] = []
    failures: list[tuple[str, str]] = []

    for i, symbol in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {symbol} 抓取基本資料…")
        try:
            raw = fetch_basic(symbol)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{symbol}] 失敗：{exc}")
            failures.append((symbol, str(exc)))
            time.sleep(config.REQUEST_DELAY_SEC)
            continue

        time.sleep(config.REQUEST_DELAY_SEC)
        print(f"  [{symbol}] 抓取選擇權隱含波動率…")
        raw["iv"] = fetch_iv(symbol, raw["price"])
        results.append(raw)
        time.sleep(config.IV_REQUEST_DELAY_SEC)

    return results, failures
