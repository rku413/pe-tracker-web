"""入口：讀 tickers.txt → 抓資料 → 算指標 → 追加 history.csv → 產生 index.html。

用法：
    python main.py              # 正常執行
    python main.py --no-iv      # 跳過選擇權 IV（本機快速測試用）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config
import fetch_data
import metrics
import render_html


def load_history(path: str) -> pd.DataFrame:
    """讀舊的 history.csv；不存在或壞掉就回傳空表。"""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            return pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            print(f"讀取舊的 {path} 失敗，將重新建立：{exc}")
    return pd.DataFrame(columns=metrics.HISTORY_COLUMNS)


def past_ivs_by_symbol(history: pd.DataFrame, today: str) -> dict[str, list[float]]:
    """從歷史取出每檔股票過去各日（不含今天）的 IV，依日期排序。"""
    if history.empty or "iv" not in history.columns:
        return {}
    df = history[history["date"] != today].copy()
    df["iv"] = pd.to_numeric(df["iv"], errors="coerce")
    df = df.dropna(subset=["iv"]).sort_values("date")
    return {sym: g["iv"].tolist() for sym, g in df.groupby("symbol")}


def load_iv_seeds(path: str) -> tuple[dict[str, dict], date | None]:
    """讀 iv_seeds.json。回傳 ({代碼: 種子}, _as_of 日期)。檔案不存在或壞掉 → 空。"""
    if not os.path.exists(path):
        return {}, None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        print(f"讀取 {path} 失敗，忽略種子：{exc}")
        return {}, None
    as_of = None
    raw_as_of = data.get("_as_of")
    if raw_as_of:
        try:
            as_of = datetime.strptime(str(raw_as_of), "%Y-%m-%d").date()
        except ValueError:
            print(f"{path} 的 _as_of 格式錯誤（應為 YYYY-MM-DD），無日期的種子將不會過期")
    seeds = {k.upper(): v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}
    if seeds:
        print(f"IV 種子：{', '.join(sorted(seeds))}")
    return seeds, as_of


def append_history(df_new: pd.DataFrame, path: str, old: pd.DataFrame) -> None:
    """把今天的資料追加進 CSV；同一天同一代碼若已存在則以新資料覆蓋。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    old = old.copy()

    # 舊檔缺少的新欄位補上，避免日後新增指標時炸掉
    for c in metrics.HISTORY_COLUMNS:
        if c not in old.columns:
            old[c] = None
    old = old[metrics.HISTORY_COLUMNS]

    combined = pd.concat([old, df_new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "symbol"], keep="last")
    combined = combined.sort_values(["date", "symbol"]).reset_index(drop=True)
    combined.to_csv(path, index=False, encoding="utf-8")
    print(f"歷史資料已寫入 {path}（共 {len(combined)} 列）")


def main(argv: list[str]) -> int:
    # Windows 主控台預設 cp950，中文 log 會亂碼；統一用 UTF-8 輸出
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    skip_iv = "--no-iv" in argv
    if skip_iv:
        # 本機測試用：把 IV 抓取換成固定回傳「missing」
        fetch_data.fetch_iv = lambda symbol, price: {"status": "missing"}  # type: ignore[assignment]

    tz = ZoneInfo(config.TIMEZONE)
    now = datetime.now(tz)
    updated_at = now.strftime("%Y-%m-%d %H:%M")
    today = now.strftime("%Y-%m-%d")

    tickers = fetch_data.load_tickers(config.TICKERS_FILE)
    if not tickers:
        print(f"{config.TICKERS_FILE} 是空的，沒有東西可抓。")
        return 1
    print(f"追蹤清單（{len(tickers)} 檔）：{', '.join(tickers)}")

    history = load_history(config.HISTORY_CSV)
    past_ivs = past_ivs_by_symbol(history, today)
    seeds, seed_as_of = load_iv_seeds(config.IV_SEEDS_FILE)
    today_date = now.date()

    raws, failures = fetch_data.fetch_all(tickers)

    rows = []
    for raw in raws:
        try:
            rows.append(metrics.build_row(
                raw,
                past_ivs.get(raw["symbol"], []),
                seeds.get(raw["symbol"]),
                today_date,
                seed_as_of,
            ))
        except Exception as exc:  # noqa: BLE001
            print(f"  [{raw['symbol']}] 指標計算失敗：{exc}")
            failures.append((raw["symbol"], f"指標計算失敗：{exc}"))

    if not rows:
        print("所有股票都失敗，保留舊的 index.html 與 history.csv 不覆寫。")
        for sym, msg in failures:
            print(f"  {sym}: {msg}")
        return 1

    append_history(metrics.rows_to_history_frame(rows, today), config.HISTORY_CSV, history)

    html_text = render_html.render(rows, failures, updated_at)
    with open(config.OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"網頁已寫入 {config.OUTPUT_HTML}")

    print("\n===== 摘要 =====")
    for r in rows:
        sigma = f"{r['pe_sigma']:+.2f}σ" if r["pe_sigma"] is not None else "N/A"
        iv_txt = f"{r['iv'] * 100:.1f}%" if r["iv"] is not None else r["iv_status"]
        print(f"{r['symbol']:<8} {r['group']:<8} PE={metrics.fmt(r['pe_now'])} ({sigma})  IV={iv_txt}  IVR={r['ivr_display']}")
    if failures:
        print(f"失敗 {len(failures)} 檔：" + ", ".join(s for s, _ in failures))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
