# -*- coding: utf-8 -*-
"""
個股相對強度分析器 v2 — Streamlit
===================================
左圖 (可切換三種專業配置):
  A. 雙動能 (Antonacci):  X=超額報酬百分位, Y=絕對報酬百分位-50
  B. 領導股 (O'Neil/Minervini): X=股價52週位置, Y=RS線52週位置
  C. 動能品質 (Gray/Vogel): X=60日超額報酬%, Y=上漲天數比-50%
右圖 (固定): Mansfield 階段: X=RS偏離200MA%, Y=RS 20日回歸斜率(標準化)

功能: 智慧搜尋 (公司名/Yahoo代碼/Bloomberg格式) / 尾巴可調 / hover日期 / 拖曳放大
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re, time

st.set_page_config(page_title="個股 RS 分析器", layout="wide")

# ============ 智慧搜尋 ============
BB_SUFFIX = {  # Bloomberg 交易所碼 → Yahoo 後綴
    "TT": ".TW", "TWO": ".TWO", "JP": ".T", "JT": ".T", "HK": ".HK",
    "KS": ".KS", "KQ": ".KQ", "CH": ".SS", "C1": ".SZ", "SP": ".SI",
    "TB": ".BK", "IJ": ".JK", "PM": ".PS", "MK": ".KL", "AU": ".AX",
    "LN": ".L", "GY": ".DE", "FP": ".PA", "IN": ".NS", "US": "",
}
DEFAULT_BENCH = {  # Yahoo 後綴 → 預設基準指數
    ".TW": "^TWII", ".TWO": "^TWII", ".T": "^N225", ".HK": "^HSI",
    ".KS": "^KS11", ".KQ": "^KS11", ".SS": "000001.SS", ".SZ": "399001.SZ",
    ".SI": "^STI", ".BK": "^SET.BK", ".JK": "^JKSE", ".PS": "PSEI.PS",
    ".KL": "^KLSE", ".AX": "^AXJO", ".L": "^FTSE", ".DE": "^GDAXI",
    ".PA": "^FCHI", ".NS": "^NSEI", "": "^GSPC",
}

def bb_to_yahoo(q):
    m = re.fullmatch(r"([0-9A-Za-z\.]+)\s+([A-Z0-9]{1,3})", q.strip())
    if m and m.group(2).upper() in BB_SUFFIX:
        return m.group(1).upper() + BB_SUFFIX[m.group(2).upper()]
    return None

@st.cache_data(ttl=86400, show_spinner=False)
def yahoo_search(query):
    try:
        res = yf.Search(query, max_results=8)
        return [(q.get("symbol",""), q.get("shortname") or q.get("longname") or "",
                 q.get("exchDisp",""), q.get("quoteType",""))
                for q in res.quotes if q.get("symbol")]
    except Exception:
        return []

st.sidebar.header("標的")
query = st.sidebar.text_input("搜尋個股", "2330.TW",
    help="可輸入: 公司名稱 (台積電 / Apple) 、Yahoo 代碼 (2330.TW / NVDA) 、"
         "Bloomberg 格式 (2330 TT / AAPL US)")

candidates = []
bb = bb_to_yahoo(query)
if bb:
    candidates.append((bb, f"(Bloomberg 格式轉換)", "", ""))
for c in yahoo_search(query):
    if c[0] != (bb or ""):
        candidates.append(c)
if not candidates:
    candidates = [(query.strip(), "(直接使用輸入)", "", "")]

labels = [f"{s}  —  {n} {('['+e+']') if e else ''}" for s, n, e, _ in candidates]
sel = st.sidebar.selectbox("選擇標的", labels, index=0)
stock = candidates[labels.index(sel)][0]

suffix = ""
m = re.search(r"(\.[A-Z]+)$", stock)
if m: suffix = m.group(1)
bench_default = DEFAULT_BENCH.get(suffix, "^GSPC")
benchmark = st.sidebar.text_input("基準指數", bench_default, key=f"bench_{stock}",
    help="依標的交易所自動建議, 可自行修改")

# ============ 其他設定 ============
st.sidebar.header("設定")
mode_left = st.sidebar.selectbox("左圖配置",
    ["A. 雙動能 (Antonacci)", "B. 領導股 (O'Neil)", "C. 動能品質 (Gray/Vogel)"])
end_date = st.sidebar.date_input("As-of 日期", pd.Timestamp.today())
tail_L = st.sidebar.slider("左圖尾巴 (日)", 5, 60, 15)
tail_R = st.sidebar.slider("右圖尾巴 (日)", 5, 60, 15)

with st.sidebar.expander("進階參數"):
    PCTL_WINDOW  = st.number_input("百分位/52週回看窗 (日)", 60, 500, 252)
    EXCESS_WIN   = st.number_input("超額/絕對報酬窗口 (日)", 5, 60, 20)
    QUAL_WIN     = st.number_input("動能品質窗口 (日)", 20, 120, 60)
    MANSFIELD_MA = st.number_input("RS 長期均線 (日)", 50, 300, 200)
    SLOPE_WIN    = st.number_input("回歸斜率窗口 (日)", 5, 60, 20)

# ============ 抓資料 ============
@st.cache_data(ttl=3600, show_spinner="下載價格資料中...")
def load(stock, benchmark, end_str, need_days):
    end = pd.to_datetime(end_str)
    start = end - pd.Timedelta(days=int(need_days * 1.7) + 60)
    result, diag = {}, {}
    for tkr in [stock, benchmark]:
        s = pd.Series(dtype=float)
        for attempt in range(3):
            try:
                df = yf.Ticker(tkr).history(
                    start=start.strftime("%Y-%m-%d"),
                    end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                    auto_adjust=True)
                if len(df) > 0:
                    s = df["Close"]; s.index = s.index.tz_localize(None); break
            except Exception as e:
                diag[tkr] = f"錯誤: {type(e).__name__}"
            time.sleep(2 * (attempt + 1))
        result[tkr] = s
        diag[tkr] = f"{len(s)} 筆" if len(s) > 0 else diag.get(tkr, "0 筆")
    return pd.DataFrame(result).ffill().dropna(), diag

need = PCTL_WINDOW + MANSFIELD_MA + 60
raw, diag = load(stock, benchmark, str(end_date), need)

if raw.empty or stock not in raw.columns or benchmark not in raw.columns:
    st.error(f"資料下載失敗。診斷：{stock} → {diag.get(stock,'?')}  |  "
             f"{benchmark} → {diag.get(benchmark,'?')}")
    st.warning("若代碼正確但 0 筆, 多為 Yahoo 暫時限流 — 等 1~2 分鐘按 R 重跑。")
    st.stop()
min_days = max(PCTL_WINDOW + EXCESS_WIN, MANSFIELD_MA + SLOPE_WIN) + 20
if len(raw) < min_days:
    st.error(f"資料不足 ({len(raw)} 天, 需約 {min_days} 天)。新股不適用, 或縮短回看窗。")
    st.stop()

price, bench = raw[stock], raw[benchmark]

# ============ 指標計算 ============
def rolling_percentile(series, window):
    def pctl(arr): return (arr[:-1] < arr[-1]).mean() * 100
    return series.rolling(window + 1).apply(pctl, raw=True)

# --- 配置 A: 雙動能 ---
excess = (price.pct_change(EXCESS_WIN) - bench.pct_change(EXCESS_WIN)) * 100
absret = price.pct_change(EXCESS_WIN) * 100
modeA = pd.DataFrame({
    "x": rolling_percentile(excess, PCTL_WINDOW),
    "y": rolling_percentile(absret, PCTL_WINDOW) - 50,
}).dropna()

# --- 配置 B: 領導股 ---
lo = price.rolling(PCTL_WINDOW).min(); hi = price.rolling(PCTL_WINDOW).max()
price_pos = (price - lo) / (hi - lo) * 100
rs_line = price / bench * 100
rlo = rs_line.rolling(PCTL_WINDOW).min(); rhi = rs_line.rolling(PCTL_WINDOW).max()
rs_pos = (rs_line - rlo) / (rhi - rlo) * 100
modeB = pd.DataFrame({"x": price_pos, "y": rs_pos}).dropna()

# --- 配置 C: 動能品質 ---
excess_q = (price.pct_change(QUAL_WIN) - bench.pct_change(QUAL_WIN)) * 100
up_ratio = (price.pct_change() > 0).rolling(QUAL_WIN).mean() * 100 - 50
modeC = pd.DataFrame({"x": excess_q, "y": up_ratio}).dropna()

# --- 右圖: Mansfield ---
mans_x = (rs_line / rs_line.rolling(MANSFIELD_MA).mean() - 1) * 100
def rolling_slope_pct(series, window):
    xs = np.arange(window)
    def fn(arr):
        b = np.polyfit(xs, arr, 1)[0]
        return b / arr.mean() * 100 * window
    return series.rolling(window).apply(fn, raw=True)
modeM = pd.DataFrame({"x": mans_x, "y": rolling_slope_pct(rs_line, SLOPE_WIN)}).dropna()

# ============ 左圖模式定義 ============
LEFT = {
 "A. 雙動能 (Antonacci)": dict(
    df=modeA, cx=50, cy=0,
    x_t=f"X: {EXCESS_WIN}日超額報酬的{PCTL_WINDOW}日百分位",
    y_t=f"Y: {EXCESS_WIN}日絕對報酬的{PCTL_WINDOW}日百分位-50",
    quads=["進攻強勢", "防禦強勢(抗跌)", "真弱勢", "補漲候選"],
    note="右上=相對+絕對雙動能齊備 (Antonacci買進區) | 右下=跌市抗跌 | 左上=漲但輸大盤"),
 "B. 領導股 (O'Neil)": dict(
    df=modeB, cx=50, cy=50,
    x_t="X: 股價52週區間位置 (100=新高)",
    y_t="Y: RS線52週區間位置 (100=RS新高)",
    quads=["雙新高領導股", "價強RS弱(隨盤)", "雙弱", "RS領先價格(吸籌)"],
    note="O'Neil 訊號: Y≈100 而 X 在 70~80 = RS線先創新高, 常領先股價突破"),
 "C. 動能品質 (Gray/Vogel)": dict(
    df=modeC, cx=0, cy=0,
    x_t=f"X: {QUAL_WIN}日超額報酬 (%)",
    y_t=f"Y: {QUAL_WIN}日上漲天數比-50 (%)",
    quads=["強且平滑", "強但暴衝", "弱且潰散", "弱但盤堅"],
    note="右上=平滑爬升, 動能易延續 (frog-in-the-pan) | 右下=事件驅動暴漲, 慎追"),
}
cfgL = LEFT[mode_left]

# ============ 繪圖 ============
def make_panel(df, tail_n, title, x_t, y_t, cx, cy, quads, color):
    tail = df.tail(tail_n)
    view = df.tail(max(tail_n * 4, 120))
    xp = max((view["x"].max()-view["x"].min())*0.1, 1)
    yp = max((view["y"].max()-view["y"].min())*0.1, 1)
    xr = [min(view["x"].min()-xp, cx-xp), max(view["x"].max()+xp, cx+xp)]
    yr = [min(view["y"].min()-yp, cy-yp), max(view["y"].max()+yp, cy+yp)]

    fig = go.Figure()
    for x0,y0,x1,y1,c in [(cx,cy,xr[1],yr[1],"#c8f0c8"), (cx,yr[0],xr[1],cy,"#fff4b3"),
                          (xr[0],yr[0],cx,cy,"#f5c8c8"), (xr[0],cy,cx,yr[1],"#c8dcf0")]:
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      fillcolor=c, opacity=0.35, line_width=0, layer="below")
    fig.add_hline(y=cy, line_color="gray", line_width=1)
    fig.add_vline(x=cx, line_color="gray", line_width=1)
    for (sx,sy,c), label in zip([(1,1,"#227722"),(1,-1,"#997700"),
                                  (-1,-1,"#992222"),(-1,1,"#224477")], quads):
        fig.add_annotation(x=xr[1] if sx>0 else xr[0], y=yr[1] if sy>0 else yr[0],
                           text=label, showarrow=False,
                           xanchor="right" if sx>0 else "left",
                           yanchor="top" if sy>0 else "bottom",
                           font=dict(size=12, color=c))
    dates = tail.index.strftime("%m/%d")
    fig.add_trace(go.Scatter(x=tail["x"], y=tail["y"], mode="lines+markers",
        line=dict(color=color, width=2.5), marker=dict(color=color, size=6),
        opacity=0.75, customdata=dates,
        hovertemplate="%{customdata}<br>X: %{x:.1f}<br>Y: %{y:+.1f}<extra></extra>",
        showlegend=False))
    fig.add_trace(go.Scatter(x=[tail["x"].iloc[-1]], y=[tail["y"].iloc[-1]],
        mode="markers", marker=dict(color=color, size=18,
        line=dict(color="black", width=1.5)),
        customdata=[tail.index[-1].strftime("%Y/%m/%d")],
        hovertemplate="<b>最新 %{customdata}</b><br>X: %{x:.1f}<br>Y: %{y:+.1f}<extra></extra>",
        showlegend=False))
    fig.add_trace(go.Scatter(x=[tail["x"].iloc[0]], y=[tail["y"].iloc[0]],
        mode="markers", marker=dict(color=color, size=8, symbol="square"),
        opacity=0.5, customdata=[tail.index[0].strftime("%Y/%m/%d")],
        hovertemplate="起點 %{customdata}<extra></extra>", showlegend=False))
    fig.update_layout(
        title=dict(text=f"<b>{title}</b><br><sup>{x_t}  |  {y_t}  |  尾巴 {tail_n} 日</sup>",
                   font=dict(size=15)),
        xaxis=dict(title=x_t, range=xr), yaxis=dict(title=y_t, range=yr),
        height=560, margin=dict(l=50, r=20, t=80, b=50),
        hovermode="closest", dragmode="zoom")
    return fig

name_disp = sel.split("—")[1].strip() if "—" in sel else stock
st.title(f"{stock} vs {benchmark}")
st.caption(f"{name_disp}  |  as of {raw.index[-1].date()}  |  "
           f"hover 看日期, 拖曳放大, 雙擊還原")

c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(make_panel(cfgL["df"], tail_L, f"左圖：{mode_left}",
        cfgL["x_t"], cfgL["y_t"], cfgL["cx"], cfgL["cy"], cfgL["quads"],
        "#c0392b"), use_container_width=True)
    st.caption(cfgL["note"])
with c2:
    st.plotly_chart(make_panel(modeM, tail_R, "右圖：Mansfield 階段",
        f"X: RS偏離{MANSFIELD_MA}日均線 (%)",
        f"Y: RS {SLOPE_WIN}日回歸斜率 (期化%, 標準化)",
        0, 0, ["階段二 主升", "階段三 見頂", "階段四 主跌", "階段一→二 翻轉"],
        "#2c5f8a"), use_container_width=True)
    st.caption("X=長期位置, Y=短期方向 | 左上=低位翻揚 (Weinstein 階段一轉二)")

# ============ 摘要 ============
def q_label(x, y, cx, cy, labels):
    if x >= cx and y >= cy: return labels[0]
    if x >= cx and y <  cy: return labels[1]
    if x <  cx and y <  cy: return labels[2]
    return labels[3]

lastL, lastM = cfgL["df"].iloc[-1], modeM.iloc[-1]
lblL = q_label(lastL["x"], lastL["y"], cfgL["cx"], cfgL["cy"], cfgL["quads"])
lblM = q_label(lastM["x"], lastM["y"], 0, 0,
               ["階段二 主升", "階段三 見頂", "階段四 主跌", "階段一→二 翻轉"])

s1, s2, s3, s4 = st.columns(4)
s1.metric(f"{EXCESS_WIN}日超額報酬", f"{excess.iloc[-1]:+.2f}%")
s2.metric("左圖 X / Y", f"{lastL['x']:.0f}", f"{lastL['y']:+.0f}")
s3.metric("RS 偏離長期均線", f"{lastM['x']:+.2f}%")
s4.metric("RS 斜率 (期化)", f"{lastM['y']:+.2f}%")

st.info(f"左圖判定：**{lblL}**  |  Mansfield 判定：**{lblM}**  \n"
        f"提示: 三種左圖配置各管一件事 — A 該不該持有 / B 是不是領導股 / C 漲勢品質。"
        f"切換配置多角度確認, 判定一致時訊號可信度最高。")
