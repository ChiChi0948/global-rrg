# -*- coding: utf-8 -*-
"""
個股相對強度雙模式分析器 — Streamlit 網頁版
=============================================
模式一 (百分位): X=20日超額報酬的252日歷史百分位, Y=百分位的10日變化
模式二 (Mansfield): X=RS偏離200日均線%, Y=RS的20日回歸斜率(標準化, 月化%)

功能: 任意個股+基準輸入 / 尾巴長度可調 / hover 顯示日期與數值 / 拖曳放大
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="個股 RS 雙模式", layout="wide")

# ============ 側欄 ============
st.sidebar.header("設定")
stock = st.sidebar.text_input("個股代碼", "2330.TW",
    help="台股 2330.TW / 美股 NVDA / 港股 0700.HK / 日股 7203.T")
benchmark = st.sidebar.text_input("基準指數", "^TWII",
    help="台股 ^TWII / 美股 ^GSPC / 港股 ^HSI / 日股 ^N225")
end_date = st.sidebar.date_input("As-of 日期", pd.Timestamp.today())
tail_1 = st.sidebar.slider("模式一尾巴 (日)", 5, 60, 15)
tail_2 = st.sidebar.slider("模式二尾巴 (日)", 5, 60, 15)

with st.sidebar.expander("進階參數"):
    PCTL_WINDOW  = st.number_input("百分位回看窗 (日)", 60, 500, 252)
    EXCESS_WIN   = st.number_input("超額報酬窗口 (日)", 5, 60, 20)
    PCTL_DELTA   = st.number_input("百分位變化天數", 3, 30, 10)
    MANSFIELD_MA = st.number_input("RS 長期均線 (日)", 50, 300, 200)
    SLOPE_WIN    = st.number_input("回歸斜率窗口 (日)", 5, 60, 20)

# ============ 抓資料 ============
@st.cache_data(ttl=3600, show_spinner="下載價格資料中...")
def load(stock, benchmark, end_str, need_days):
    end = pd.to_datetime(end_str)
    start = end - pd.Timedelta(days=int(need_days * 1.7) + 60)
    raw = yf.download([stock, benchmark], start=start.strftime("%Y-%m-%d"),
                      end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                      auto_adjust=True, progress=False)["Close"]
    return raw.ffill().dropna()

need = PCTL_WINDOW + MANSFIELD_MA + 60
raw = load(stock, benchmark, str(end_date), need)

if raw.empty or stock not in raw.columns or benchmark not in raw.columns:
    st.error("資料下載失敗 — 請檢查代碼格式 (台股要加 .TW, 指數要加 ^)")
    st.stop()
min_days = max(PCTL_WINDOW + EXCESS_WIN, MANSFIELD_MA + SLOPE_WIN) + 20
if len(raw) < min_days:
    st.error(f"資料不足 ({len(raw)} 天, 需約 {min_days} 天)。新上市股票不適用, "
             f"或到進階參數縮短回看窗。")
    st.stop()

price, bench = raw[stock], raw[benchmark]

# ============ 模式一: 歷史百分位 ============
excess = (price.pct_change(EXCESS_WIN) - bench.pct_change(EXCESS_WIN)) * 100

def rolling_percentile(series, window):
    def pctl(arr): return (arr[:-1] < arr[-1]).mean() * 100
    return series.rolling(window + 1).apply(pctl, raw=True)

pctl = rolling_percentile(excess, PCTL_WINDOW)
mode1 = pd.DataFrame({"x": pctl, "y": pctl - pctl.shift(PCTL_DELTA)}).dropna()

# ============ 模式二: Mansfield + 標準化斜率 ============
rs = price / bench * 100
mans_x = (rs / rs.rolling(MANSFIELD_MA).mean() - 1) * 100

def rolling_slope_pct(series, window):
    x = np.arange(window)
    def fn(arr):
        b = np.polyfit(x, arr, 1)[0]
        return b / arr.mean() * 100 * window   # 標準化: ÷均值 →每日%, ×窗口 →期化%
    return series.rolling(window).apply(fn, raw=True)

mode2 = pd.DataFrame({"x": mans_x, "y": rolling_slope_pct(rs, SLOPE_WIN)}).dropna()

# ============ 畫圖 ============
def make_panel(df, tail_n, title, x_title, y_title, cx, cy, quads, color):
    tail = df.tail(tail_n)
    view = df.tail(max(tail_n * 4, 120))
    x_pad = max((view["x"].max() - view["x"].min()) * 0.1, 1)
    y_pad = max((view["y"].max() - view["y"].min()) * 0.1, 1)
    xr = [min(view["x"].min() - x_pad, cx - x_pad), max(view["x"].max() + x_pad, cx + x_pad)]
    yr = [min(view["y"].min() - y_pad, cy - y_pad), max(view["y"].max() + y_pad, cy + y_pad)]

    fig = go.Figure()
    fig.add_shape(type="rect", x0=cx, y0=cy, x1=xr[1], y1=yr[1],
                  fillcolor="#c8f0c8", opacity=0.35, line_width=0, layer="below")
    fig.add_shape(type="rect", x0=cx, y0=yr[0], x1=xr[1], y1=cy,
                  fillcolor="#fff4b3", opacity=0.35, line_width=0, layer="below")
    fig.add_shape(type="rect", x0=xr[0], y0=yr[0], x1=cx, y1=cy,
                  fillcolor="#f5c8c8", opacity=0.35, line_width=0, layer="below")
    fig.add_shape(type="rect", x0=xr[0], y0=cy, x1=cx, y1=yr[1],
                  fillcolor="#c8dcf0", opacity=0.35, line_width=0, layer="below")
    fig.add_hline(y=cy, line_color="gray", line_width=1)
    fig.add_vline(x=cx, line_color="gray", line_width=1)
    anchors = [(1,1,"#227722"), (1,-1,"#997700"), (-1,-1,"#992222"), (-1,1,"#224477")]
    for (sx, sy, c), label in zip(anchors, quads):
        fig.add_annotation(x=xr[1] if sx>0 else xr[0], y=yr[1] if sy>0 else yr[0],
                           text=label, showarrow=False,
                           xanchor="right" if sx>0 else "left",
                           yanchor="top" if sy>0 else "bottom",
                           font=dict(size=12, color=c))

    dates = tail.index.strftime("%m/%d")
    fig.add_trace(go.Scatter(
        x=tail["x"], y=tail["y"], mode="lines+markers",
        line=dict(color=color, width=2.5),
        marker=dict(color=color, size=6),
        opacity=0.75, customdata=dates,
        hovertemplate="%{customdata}<br>X: %{x:.1f}<br>Y: %{y:+.1f}<extra></extra>",
        showlegend=False))
    fig.add_trace(go.Scatter(
        x=[tail["x"].iloc[-1]], y=[tail["y"].iloc[-1]], mode="markers",
        marker=dict(color=color, size=18, line=dict(color="black", width=1.5)),
        customdata=[tail.index[-1].strftime("%Y/%m/%d")],
        hovertemplate="<b>最新 %{customdata}</b><br>X: %{x:.1f}<br>Y: %{y:+.1f}<extra></extra>",
        showlegend=False))
    fig.add_trace(go.Scatter(
        x=[tail["x"].iloc[0]], y=[tail["y"].iloc[0]], mode="markers",
        marker=dict(color=color, size=8, symbol="square"), opacity=0.5,
        customdata=[tail.index[0].strftime("%Y/%m/%d")],
        hovertemplate="起點 %{customdata}<br>X: %{x:.1f}<br>Y: %{y:+.1f}<extra></extra>",
        showlegend=False))

    fig.update_layout(
        title=dict(text=f"<b>{title}</b><br><sup>{x_title}  |  {y_title}  |  "
                        f"尾巴 {tail_n} 日, 方塊=起點, 大點=最新</sup>", font=dict(size=15)),
        xaxis=dict(title=x_title, range=xr),
        yaxis=dict(title=y_title, range=yr),
        height=560, margin=dict(l=50, r=20, t=80, b=50),
        hovermode="closest", dragmode="zoom")
    return fig

QUADS_1 = ["強且更強", "強但轉弱", "弱且更弱", "弱但轉強"]
QUADS_2 = ["階段二 主升", "階段三 見頂", "階段四 主跌", "階段一→二 翻轉"]

st.title(f"個股相對強度雙模式：{stock} vs {benchmark}")
st.caption(f"as of {raw.index[-1].date()}  |  滑鼠 hover 看日期與數值, 拖曳框選放大, 雙擊還原")

c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(make_panel(
        mode1, tail_1, "模式一：歷史百分位",
        f"X: {EXCESS_WIN}日超額報酬的{PCTL_WINDOW}日百分位 (0~100)",
        f"Y: 百分位{PCTL_DELTA}日變化",
        50, 0, QUADS_1, "#c0392b"), use_container_width=True)
with c2:
    st.plotly_chart(make_panel(
        mode2, tail_2, "模式二：Mansfield 階段",
        f"X: RS偏離{MANSFIELD_MA}日均線 (%)",
        f"Y: RS {SLOPE_WIN}日回歸斜率 (期化%, 標準化)",
        0, 0, QUADS_2, "#2c5f8a"), use_container_width=True)

# ============ 數值摘要 ============
m1, m2 = mode1.iloc[-1], mode2.iloc[-1]

def q_label(x, y, cx, cy, labels):
    if x >= cx and y >= cy: return labels[0]
    if x >= cx and y <  cy: return labels[1]
    if x <  cx and y <  cy: return labels[2]
    return labels[3]

l1 = q_label(m1["x"], m1["y"], 50, 0, QUADS_1)
l2 = q_label(m2["x"], m2["y"], 0, 0, QUADS_2)

s1, s2, s3, s4 = st.columns(4)
s1.metric(f"{EXCESS_WIN}日超額報酬", f"{excess.iloc[-1]:+.2f}%")
s2.metric("歷史百分位 / Δ", f"{m1['x']:.0f}", f"{m1['y']:+.0f} ({PCTL_DELTA}日)")
s3.metric("RS 偏離長期均線", f"{m2['x']:+.2f}%")
s4.metric("RS 斜率 (期化)", f"{m2['y']:+.2f}%", None)

if l1.startswith(("強且", "階段二")) or l2.startswith("階段二"):
    icon = "🟢"
elif "轉強" in l1 or "翻轉" in l2:
    icon = "🔵"
elif "轉弱" in l1 or "見頂" in l2:
    icon = "🟡"
else:
    icon = "🔴"
st.info(f"{icon} 模式一判定：**{l1}**  |  模式二判定：**{l2}**  \n"
        f"兩模式一致 → 訊號可信度高；分歧 → 百分位版(快)先動、Mansfield版(慢)未跟上, "
        f"通常代表轉折初期, 再觀察數日。")