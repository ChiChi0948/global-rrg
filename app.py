# -*- coding: utf-8 -*-
"""
Global Equity RRG v3 — Streamlit 網頁版
========================================
X 軸 = 該期限超額報酬 % (vs ACWI)
Y 軸 = 該期限超額報酬排名 較 N 週前升降名次 (爬升為正)

功能:
- 三張互動 RRG (Plotly): 滑鼠 hover 顯示市場名/數值, 點圖例隱藏/顯示
- 「聚焦市場」選單: 選中的市場線條加粗置頂, 其他變淡
- 多期限排名矩陣表
- 側欄可調 as-of 日期與尾巴長度

部署: GitHub repo 放 app.py + requirements.txt → share.streamlit.io 連結
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Global RRG v3", layout="wide")

# ============ 固定參數 ============
BENCHMARK = "ACWI"
TICKERS = {
    "US":"SPY", "Japan":"EWJ", "Europe":"VGK", "UK":"EWU",
    "Germany":"EWG", "China":"MCHI", "Taiwan":"EWT", "Korea":"EWY",
    "India":"INDA", "Brazil":"EWZ", "Mexico":"EWW", "Australia":"EWA",
    "Singapore":"EWS", "Thailand":"THD", "Indonesia":"EIDO",
    "Philippines":"EPHE", "Malaysia":"EWM",
}
FRAMES = {
    "long":  dict(x_win=60, d_days=20, label="長期",
                  x_title="X: 60日超額報酬 (%)", y_title="Y: 排名較4週前升降 (名)"),
    "mid":   dict(x_win=20, d_days=10, label="中期",
                  x_title="X: 20日超額報酬 (%)", y_title="Y: 排名較2週前升降 (名)"),
    "short": dict(x_win=5,  d_days=5,  label="短期",
                  x_title="X: 5日超額報酬 (%)",  y_title="Y: 排名較1週前升降 (名)"),
}
PALETTE = ["#e6194B","#3cb44b","#4363d8","#f58231","#911eb4","#42d4f4",
           "#f032e6","#bfef45","#fabed4","#469990","#dcbeff","#9A6324",
           "#800000","#aaffc3","#808000","#000075","#a9a9a9"]

# ============ 側欄 ============
st.sidebar.header("設定")
end_date = st.sidebar.date_input("As-of 日期", pd.Timestamp.today())
tail_long  = st.sidebar.slider("長期尾巴 (日)", 5, 30, 12)
tail_mid   = st.sidebar.slider("中期尾巴 (日)", 5, 30, 10)
tail_short = st.sidebar.slider("短期尾巴 (日)", 3, 20, 8)
TAILS = {"long": tail_long, "mid": tail_mid, "short": tail_short}
highlight = st.sidebar.selectbox("聚焦市場 (線條置頂加粗)",
                                 ["(無)"] + list(TICKERS.keys()))

# ============ 抓資料 (快取) ============
@st.cache_data(ttl=3600, show_spinner="下載價格資料中...")
def load_data(end_str):
    end = pd.to_datetime(end_str)
    start = end - pd.Timedelta(days=500)
    tickers = [BENCHMARK] + list(TICKERS.values())
    raw = yf.download(tickers, start=start.strftime("%Y-%m-%d"),
                      end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                      auto_adjust=True, progress=False)["Close"]
    return raw.ffill().dropna(how="all").loc[:end_str]

raw = load_data(str(end_date))
if raw.empty or BENCHMARK not in raw.columns:
    st.error("資料下載失敗, 請稍後重試或檢查日期。")
    st.stop()
bench = raw[BENCHMARK]

# ============ 計算 ============
@st.cache_data(ttl=3600)
def compute(end_str):
    excess_df, rank_df, series = {}, {}, {}
    for key, cfg in FRAMES.items():
        cols = {}
        for name, tkr in TICKERS.items():
            if tkr not in raw.columns: continue
            cols[name] = (raw[tkr].pct_change(cfg["x_win"])
                          - bench.pct_change(cfg["x_win"])) * 100
        ex = pd.DataFrame(cols).dropna()
        rk = ex.rank(axis=1, ascending=False)
        d = cfg["d_days"]
        ser = {}
        for name in ex.columns:
            y = rk[name].shift(d) - rk[name]
            ser[name] = pd.DataFrame({"x": ex[name], "y": y}).dropna()
        excess_df[key], rank_df[key], series[key] = ex, rk, ser
    return excess_df, rank_df, series

excess_df, rank_df, series = compute(str(end_date))

# ============ RRG 繪圖 ============
QUAD_NOTES = [("領先且超車", 1, 1, "#227722"), ("領先被追上", 1, -1, "#997700"),
              ("落後被超車", -1, -1, "#992222"), ("落後但超車", -1, 1, "#224477")]

def make_rrg(key):
    cfg, tail_n = FRAMES[key], TAILS[key]
    data = series[key]
    fig = go.Figure()

    all_pts = pd.concat([d.tail(tail_n) for d in data.values()])
    x_rng = [all_pts["x"].min() - 1, all_pts["x"].max() + 1]
    y_rng = [all_pts["y"].min() - 1.5, all_pts["y"].max() + 1.5]

    # 象限背景
    fig.add_shape(type="rect", x0=0, y0=0, x1=x_rng[1], y1=y_rng[1],
                  fillcolor="#c8f0c8", opacity=0.3, line_width=0, layer="below")
    fig.add_shape(type="rect", x0=0, y0=y_rng[0], x1=x_rng[1], y1=0,
                  fillcolor="#fff4b3", opacity=0.3, line_width=0, layer="below")
    fig.add_shape(type="rect", x0=x_rng[0], y0=y_rng[0], x1=0, y1=0,
                  fillcolor="#f5c8c8", opacity=0.3, line_width=0, layer="below")
    fig.add_shape(type="rect", x0=x_rng[0], y0=0, x1=0, y1=y_rng[1],
                  fillcolor="#c8dcf0", opacity=0.3, line_width=0, layer="below")
    fig.add_hline(y=0, line_color="gray", line_width=1)
    fig.add_vline(x=0, line_color="gray", line_width=1)
    for label, sx, sy, c in QUAD_NOTES:
        fig.add_annotation(x=x_rng[1] if sx>0 else x_rng[0],
                           y=y_rng[1] if sy>0 else y_rng[0],
                           text=label, showarrow=False,
                           xanchor="right" if sx>0 else "left",
                           yanchor="top" if sy>0 else "bottom",
                           font=dict(size=11, color=c))

    # 先畫非聚焦, 再畫聚焦 (置頂)
    names_sorted = [n for n in data if n != highlight] + \
                   ([highlight] if highlight in data else [])
    for name in names_sorted:
        d = data[name].tail(tail_n)
        i = list(TICKERS.keys()).index(name)
        color = PALETTE[i % len(PALETTE)]
        focused = (name == highlight)
        dim = (highlight != "(無)") and not focused
        lw = 4.5 if focused else 1.8
        op = 0.15 if dim else (1.0 if focused else 0.65)

        fig.add_trace(go.Scatter(
            x=d["x"], y=d["y"], mode="lines", name=name,
            line=dict(color=color, width=lw), opacity=op,
            legendgroup=name, showlegend=False,
            hovertemplate=f"<b>{name}</b><br>超額: %{{x:.2f}}%<br>排名Δ: %{{y:+.0f}}名<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=[d["x"].iloc[-1]], y=[d["y"].iloc[-1]],
            mode="markers+text", name=name,
            text=[name], textposition="top right",
            textfont=dict(size=12 if focused else 10,
                          color="black" if not dim else "#bbbbbb"),
            marker=dict(color=color, size=16 if focused else 11,
                        line=dict(color="black", width=1.2)),
            opacity=0.25 if dim else 1.0, legendgroup=name,
            hovertemplate=f"<b>{name}</b> (最新)<br>超額: %{{x:.2f}}%<br>排名Δ: %{{y:+.0f}}名<extra></extra>"))

    fig.update_layout(
        title=dict(text=f"<b>{cfg['label']}</b>  |  {cfg['x_title']}  |  {cfg['y_title']}"
                        f"<br><sup>尾巴 {tail_n} 日, 大點=最新位置</sup>", font=dict(size=14)),
        xaxis=dict(title=cfg["x_title"], range=x_rng),
        yaxis=dict(title=cfg["y_title"], range=y_rng, dtick=2),
        height=520, margin=dict(l=50, r=20, t=70, b=50),
        hovermode="closest", showlegend=False, dragmode="zoom")
    return fig

# ============ 頁面 ============
st.title("Global Equity RRG v3")
st.caption(f"X 軸 = 各期限超額報酬 % (vs {BENCHMARK})  |  "
           f"Y 軸 = 該期限超額報酬「排名」較 N 週前升降名次 (爬升為正)  |  "
           f"as of {raw.index[-1].date()}  |  {len(TICKERS)} 個市場  |  "
           f"拖曳框選可放大, 雙擊還原")

c1, c2, c3 = st.columns(3)
with c1: st.plotly_chart(make_rrg("long"), use_container_width=True)
with c2: st.plotly_chart(make_rrg("mid"), use_container_width=True)
with c3: st.plotly_chart(make_rrg("short"), use_container_width=True)

# ============ 排名矩陣表 ============
rows = []
n_mkt = len(TICKERS)
for name in TICKERS:
    if name not in excess_df["long"].columns: continue
    row = {"Market": name}; score = 0
    for key, cfg in FRAMES.items():
        rk_now = rank_df[key][name].iloc[-1]
        rk_old = rank_df[key][name].shift(cfg["d_days"]).iloc[-1]
        delta = int(rk_old - rk_now)
        row[f"{cfg['label']}排名"] = int(rk_now)
        row[f"{cfg['label']}Δ"] = delta
        row[f"{cfg['label']}超額%"] = round(excess_df[key][name].iloc[-1], 2)
        score += (n_mkt + 1 - 2*rk_now) / (n_mkt - 1) + np.clip(delta/4, -1, 1)
    row["綜合分"] = round(score, 2)
    rows.append(row)

table = pd.DataFrame(rows).set_index("Market").sort_values("綜合分", ascending=False)

def scenario(r):
    hi, lo = n_mkt*0.33, n_mkt*0.67
    L = r["長期排名"]; dM, dS = r["中期Δ"], r["短期Δ"]
    M, S = r["中期排名"], r["短期排名"]
    if L <= hi and M <= hi and S <= hi:
        return "三期共識強勢" if (dM >= 0 and dS >= 0) else "強勢但短期被追"
    if L >= lo and dM >= 3 and dS >= 3:  return "★弱者急速爬升"
    if L >= lo and (dM >= 3 or dS >= 3): return "弱者初步翻揚"
    if L <= hi and dM <= -3 and dS <= -3: return "⚠強者急速滑落"
    if L <= hi and (dM <= -3 or dS <= -3): return "強者初步鬆動"
    if L >= lo and M >= lo and S >= lo:  return "三期共識弱勢"
    return "中性/過渡"

table["情境"] = table.apply(scenario, axis=1)
order = ["綜合分","長期排名","長期Δ","長期超額%","中期排名","中期Δ","中期超額%",
         "短期排名","短期Δ","短期超額%","情境"]
table = table[order]

st.subheader("多期限排名矩陣")
st.caption("排名 1=最強 | Δ=較 N 週前升降名次 (升為正) | 點欄位標題可排序")

def bg(v):
    if v >= 2:   return "background-color:#b8e6b8"
    if v >= 0.5: return "background-color:#d5edd5"
    if v >= -0.5:return "background-color:#f5f5dc"
    if v >= -2:  return "background-color:#f5d0d0"
    return "background-color:#e69090"

st.dataframe(table.style.map(bg, subset=["綜合分"]), use_container_width=True,
             height=640)

with st.expander("判讀指紋速查"):
    st.markdown("""
- **長期排名低 + 中短Δ大正** → 弱者轉強初期 (U型底右側)
- **長期排名高 + 中短Δ大負** → 強者崩落警訊
- **三期排名都高 + Δ平穩** → 穩定領跑, 續抱
- **短Δ與中Δ方向相反** → 單週雜訊 vs 趨勢分歧, 再等一週確認
- RRG 圖: 滑鼠移到線上看數值, 側欄「聚焦市場」讓該線置頂加粗, 拖曳框選放大
""")
