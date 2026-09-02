"""把指標列渲染成 index.html。純字串組裝，不依賴外部模板套件。"""
from __future__ import annotations

import html
from typing import Any

import config
from metrics import GROUPS, NA, fmt

GROUP_STYLE = {
    "顯著高估": "g-high2",
    "高估~均值": "g-high1",
    "均值~低估": "g-low1",
    "顯著低估": "g-low2",
    "無法判讀": "g-na",
}

COLUMNS: list[tuple[str, str]] = [
    ("代碼", "symbol"),
    ("名稱", "name"),
    ("股價", "price"),
    ("PE", "pe_now"),
    ("PE均值", "pe_mean"),
    ("PE中位數", "pe_median"),
    ("PE標準差", "pe_std"),
    ("偏離(σ)", "pe_sigma"),
    ("低估價", "price_low"),
    ("合理價", "price_fair"),
    ("高估價", "price_high"),
    ("Forward PE", "forward_pe"),
    ("PB", "pb"),
    ("PCF", "pcf"),
    ("PEG", "peg"),
    ("殖利率", "dividend_yield"),
    ("EV/EBITDA", "ev_ebitda"),
    ("52週低", "wk52_low"),
    ("52週高", "wk52_high"),
    ("52週位置", "wk52_pos"),
    ("IV Rank", "ivr_display"),
]

IV_TEXT_STATES = (NA, "無選擇權市場", "逾時")


def _e(s: Any) -> str:
    return html.escape(str(s))


def _cell(row: dict[str, Any], key: str) -> str:
    v = row.get(key)
    if key == "symbol":
        sym = _e(v)
        return (
            f'<td class="sym"><a href="https://finance.yahoo.com/quote/{sym}" '
            f'target="_blank" rel="noopener">{sym}</a></td>'
        )
    if key == "name":
        return f'<td class="name">{_e(v)}</td>'
    if key == "ivr_display":
        cls = "na" if (v in IV_TEXT_STATES or str(v).startswith("資料累積中")) else ""
        return f'<td class="{cls}">{_e(v)}</td>'
    if key == "dividend_yield":
        if v is None:
            return '<td class="na">無股息</td>'
        return f"<td>{fmt(v, 2, '%')}</td>"
    if key == "wk52_pos":
        if v is None:
            return f'<td class="na">{NA}</td>'
        return f"<td>{fmt(v, 0, '%')}</td>"
    if key == "pe_sigma":
        if v is None:
            return f'<td class="na">{NA}</td>'
        sign = "+" if v > 0 else ""
        return f"<td>{sign}{v:.2f}</td>"
    text = fmt(v, 2)
    cls = ' class="na"' if text == NA else ""
    return f"<td{cls}>{text}</td>"


def _group_table(group: str, rows: list[dict[str, Any]]) -> str:
    head = "".join(f"<th>{_e(label)}</th>" for label, _ in COLUMNS)
    if rows:
        body = "".join(
            "<tr>" + "".join(_cell(r, key) for _, key in COLUMNS) + "</tr>"
            for r in rows
        )
    else:
        body = f'<tr><td colspan="{len(COLUMNS)}" class="empty">此分組目前沒有股票</td></tr>'
    return f"""
<section class="group {GROUP_STYLE[group]}">
  <h2><span class="dot"></span>{_e(group)} <span class="count">{len(rows)} 檔</span></h2>
  <div class="scroll">
    <table>
      <thead><tr>{head}</tr></thead>
      <tbody>{body}</tbody>
    </table>
  </div>
</section>"""


CSS = """
  :root {
    --bg: #f7f8fa; --card: #ffffff; --text: #1f2328; --muted: #656d76; --border: #d0d7de;
    --link: #0969da; --head: #f0f2f5; --hover: #f3f6fa;
    --high2: #cf222e; --high1: #e8853a; --low1: #2da44e; --low2: #1a7f37; --na: #8c959f;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0d1117; --card: #161b22; --text: #e6edf3; --muted: #8b949e; --border: #30363d;
      --link: #58a6ff; --head: #1c2129; --hover: #1f262e;
      --high2: #ff7b72; --high1: #f0a35e; --low1: #56d364; --low2: #3fb950; --na: #6e7681;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.5 -apple-system, "Segoe UI", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif; }
  a { color: var(--link); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .wrap { max-width: 1400px; margin: 0 auto; padding: 16px; }
  header { margin-bottom: 12px; }
  header h1 { font-size: 22px; margin: 0 0 6px; }
  .meta { color: var(--muted); font-size: 13px; display: flex; flex-wrap: wrap; gap: 6px 18px; }
  .edit-link { display: inline-block; margin: 10px 0 4px; padding: 6px 12px; border: 1px solid var(--border);
               border-radius: 6px; background: var(--card); font-size: 13px; }
  .edit-link:hover { background: var(--hover); text-decoration: none; }
  .legend { font-size: 12px; color: var(--muted); margin: 8px 0 16px; }
  section.group { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
                  margin-bottom: 16px; overflow: hidden; }
  section.group h2 { font-size: 15px; margin: 0; padding: 10px 14px; border-bottom: 1px solid var(--border);
                     display: flex; align-items: center; gap: 8px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .g-high2 .dot { background: var(--high2); } .g-high1 .dot { background: var(--high1); }
  .g-low1 .dot { background: var(--low1); }   .g-low2 .dot { background: var(--low2); }
  .g-na .dot { background: var(--na); }
  .count { color: var(--muted); font-weight: normal; font-size: 13px; }
  .scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  table { border-collapse: collapse; width: 100%; min-width: 1500px; font-variant-numeric: tabular-nums; }
  th, td { padding: 7px 10px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
  th { background: var(--head); font-weight: 600; font-size: 12px; color: var(--muted); position: sticky; top: 0; }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: var(--hover); }
  td.sym, th:first-child { text-align: left; position: sticky; left: 0; background: var(--card);
                           font-weight: 600; z-index: 1; }
  th:first-child { background: var(--head); z-index: 2; }
  tbody tr:hover td.sym { background: var(--hover); }
  td.name { text-align: left; max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
  td.na { color: var(--na); }
  td.empty { text-align: center; color: var(--muted); padding: 14px; }
  section.failures { border: 1px solid var(--high2); border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; }
  section.failures h2 { font-size: 14px; margin: 0 0 6px; color: var(--high2); }
  section.failures ul { margin: 0; padding-left: 20px; font-size: 13px; }
  footer { color: var(--muted); font-size: 12px; margin-top: 20px; line-height: 1.7; }
  @media (max-width: 600px) {
    .wrap { padding: 10px; }
    header h1 { font-size: 19px; }
    th, td { padding: 6px 8px; font-size: 13px; }
  }
"""


def render(rows: list[dict[str, Any]], failures: list[tuple[str, str]], updated_at: str) -> str:
    tickers_url = (
        f"https://github.com/{config.GITHUB_USER}/{config.GITHUB_REPO}"
        f"/blob/{config.GITHUB_BRANCH}/{config.TICKERS_FILE}"
    )
    repo_url = f"https://github.com/{config.GITHUB_USER}/{config.GITHUB_REPO}"

    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUPS}
    for r in rows:
        by_group.setdefault(r["group"], []).append(r)
    for g in by_group:
        # 各組內依偏離度由高到低排序，無法判讀的依代碼
        by_group[g].sort(
            key=lambda r: (-(r["pe_sigma"] if r["pe_sigma"] is not None else -999), r["symbol"])
        )

    sections = "".join(_group_table(g, by_group[g]) for g in GROUPS)

    failure_html = ""
    if failures:
        items = "".join(f"<li><strong>{_e(s)}</strong>：{_e(msg)}</li>" for s, msg in failures)
        failure_html = f"""
<section class="failures">
  <h2>本次抓取失敗的股票（{len(failures)} 檔）</h2>
  <ul>{items}</ul>
</section>"""

    k = config.SIGMA_THRESHOLD
    total = len(rows) + len(failures)

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PE Tracker</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>PE Tracker 估值追蹤</h1>
  <div class="meta">
    <span>更新時間：<strong>{_e(updated_at)}</strong>（台灣時間）</span>
    <span>追蹤 {total} 檔，成功 {len(rows)} 檔</span>
  </div>
  <a class="edit-link" href="{_e(tickers_url)}" target="_blank" rel="noopener">✏️ 編輯追蹤清單（tickers.txt on GitHub）</a>
  <div class="legend">
    分組依據：目前 PE 相對近 {config.PE_WINDOW_DAYS} 個交易日 PE 均值的偏離（以標準差 σ 為單位），
    ±{k:g}σ 以外為「顯著」。低估價 / 合理價 / 高估價 = (均值 ∓ 1σ) × EPS。
    IV Rank = (今日 IV − 近 {config.IVR_LOOKBACK_DAYS} 個交易日最低 IV) ÷ (最高 IV − 最低 IV)，0% 為一年最低、100% 為一年最高；
    IV 取最接近平價、到期最接近 {config.IV_TARGET_DAYS} 天的 call，由本站每日累積；標「種子」代表區間含手動填入的 52 週高低點（iv_seeds.json），
    純累積且不足 {config.IVR_LOOKBACK_DAYS} 天時標註實際天數。
  </div>
</header>
{failure_html}
{sections}
<footer>
  資料來源：Yahoo Finance（透過 yfinance），每日由 GitHub Actions 自動更新。僅供參考，不構成投資建議。<br>
  原始碼與歷史資料：<a href="{_e(repo_url)}" target="_blank" rel="noopener">{_e(repo_url)}</a>
</footer>
</div>
</body>
</html>
"""
