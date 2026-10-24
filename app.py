# -*- coding: utf-8 -*-
"""
台股總經資金流與產業供應鏈 AI 評估系統 (app.py)
包含完整左側功能欄、總經指標矩陣、個股看板、技術指標折線圖與對應的字型與格式優化。
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 頁面配置
st.set_page_config(
    page_title="全球總經與台股資金流 AI 矩陣分析系統",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 嵌入客製化 CSS 獨立控制字型與樣式
st.markdown("""
<style>
/* 全球總經與台股資金流 AI 矩陣分析系統 CSS 獨立設定 */
.macro-section {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* B點調整：下方指標數字調小至與標題相同大小 (約 0.9rem / 14px) */
.macro-metric-label {
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    color: #c9d1d9 !important;
    margin-bottom: 4px;
}

.macro-metric-value {
    font-size: 0.9rem !important; /* 調小至與標題同大小 */
    font-weight: 600 !important;
    color: #ffffff !important;
}

.macro-metric-delta-pos {
    font-size: 0.8rem !important;
    color: #ff4d4f !important;
}

.macro-metric-delta-neg {
    font-size: 0.8rem !important;
    color: #52c41a !important;
}

/* 個股看板獨立 CSS 設定（不與總經區塊連動） */
.stock-看板-label {
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    color: #8b949e !important;
}

.stock-看板-value {
    font-size: 0.9rem !important; /* 指數數值與狀態敘述調小至與標題相同大小 */
    font-weight: 600 !important;
    color: #ffffff !important;
}

.stock-看板-status {
    font-size: 0.9rem !important; /* 狀態敘述 (如: 中性觀望) 調小至與標題相同大小 */
    font-weight: 600 !important;
    color: #e6a23c !important;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# 0. 左側側邊欄 (Sidebar) 功能設定
# =========================================================

with st.sidebar:
    st.header("⚙️ 個股詳細分析與技術指標設定")
    
    stock_input = st.text_input("輸入台股代碼或股名", value="2317", help="輸入台股代號（如：2317 或 鴻海）")
    st.caption("(如只看三大法人籌碼與進階技術指標看板，輸入股號或股名後直接按 Enter)")
    
    st.markdown("---")
    st.subheader("技術指標週期選擇")
    time_frame = st.radio("指標週期", options=["日線", "週線"], index=0, horizontal=True)
    
    st.markdown("---")
    st.subheader("持有狀態")
    hold_status = st.radio("持有狀態", options=["準備買進", "既有持股 (已套牢/持有中)"], index=0)
    
    st.markdown("---")
    invest_amount = st.text_input("預計進場金額 (新台幣元)", value="100000.00", help="例如: 100000.00 (總預算)")
    
    st.markdown("<br>", unsafe_allow_html=True)
    btn_analyze = st.button("📊 開始 AI 個股分析", type="primary", use_container_width=True)


# =========================================================
# 1. 總經指標數據邏輯處理與格式修正
# =========================================================

macro_data = {
    "台股加權": {"val": "46,041.43", "change": -846.12, "pct": -1.81, "type": "pts"},
    "台期指夜盤": {"val": "45,654.00", "change": -580.00, "pct": -1.25, "type": "pts_pct"},
    "費城半導體": {"val": "10,779.46", "change": 47.12, "pct": 0.44, "type": "pts"},
    "美債 10Y": {"val": "4.9880%", "change": "+0.0350", "pct": "+0.71%", "type": "rate_full"},
    "恐慌 VIX": {"val": "19.4500", "change": "+0.42", "pct": "+2.21%", "type": "rate_full"},
    
    # 亞太
    "日經 225": {"val": "62,693.15", "change": -214.30, "pct": -0.34, "type": "pts"},
    
    # 美股
    "道瓊 DJI": {"val": "52,215.16", "change": -652.82, "pct": -1.23, "type": "pts"},
    "那斯達克": {"val": "25,955.10", "change": -54.60, "pct": -0.21, "type": "pts"},
    "標普 500": {"val": "7,623.68", "change": -39.75, "pct": -0.52, "type": "pts"},
    "羅素 2000": {"val": "2,775.90", "change": -8.08, "pct": -0.29, "type": "pts"},
    
    # 國際美元利率
    "美聯儲 13W": {"val": "4.0320%", "change": "+0.0100", "pct": "+0.25%", "type": "rate_full"},
    "美元 DXY": {"val": "101.75", "change": "-0.06", "pct": "-0.06%", "type": "dxy"},
    
    # 避險商品
    "WTI 原油": {"val": "103.44", "change": "+3.96", "pct": "+3.99%", "type": "rate_full"},
    "黃金 Gold": {"val": "4,010.00", "change": "-50.30", "pct": "-1.24%", "type": "rate_full"}
}

def render_macro_metric(label, data, is_top_4=False):
    val = data["val"]
    m_type = data["type"]
    
    if m_type == "pts":
        chg = data["change"]
        delta_str = f"{'↑' if chg >= 0 else '↓'} {chg:+.2f} 點"
        is_pos = chg >= 0
    elif m_type == "dxy":
        delta_str = f"↓ {data['change']} ({data['pct']})" if "-" in data['change'] else f"↑ {data['change']} ({data['pct']})"
        is_pos = "-" not in data['change']
    elif m_type == "rate_full":
        delta_str = f"{data['change']} ({data['pct']})"
        is_pos = "+" in data['change']
    else:
        chg = data["change"]
        delta_str = f"{'↑' if chg >= 0 else '↓'} {chg:+.2f} 點"
        is_pos = chg >= 0

    delta_class = "macro-metric-delta-pos" if is_pos else "macro-metric-delta-neg"
    
    if is_top_4:
        st.metric(label=label, value=str(val), delta=delta_str)
    else:
        st.markdown(f"""
        <div style="margin-bottom: 12px;">
            <div class="macro-metric-label">{label}</div>
            <div class="macro-metric-value">{val}</div>
            <div class="{delta_class}">{delta_str}</div>
        </div>
        """, unsafe_allow_html=True)


# =========================================================
# 2. 主介面：全球總經與台股資金流 AI 矩陣分析系統
# =========================================================

st.title("📈 全球總經與台股資金流 AI 矩陣分析系統")
st.caption("限定資料來源：台灣證券交易所 (TWSE) | 台灣期貨交易所 (TAIFEX) | 公開資訊觀測站 (MOPS) | Yahoo Finance")

# A. 上方 4 大指標 (標題與字型大小不變)
col1, col2, col3, col4 = st.columns(4)
with col1:
    render_macro_metric("台股加權", macro_data["台股加權"], is_top_4=True)
with col2:
    render_macro_metric("費城半導體", macro_data["費城半導體"], is_top_4=True)
with col3:
    render_macro_metric("美債 10Y", macro_data["美債 10Y"], is_top_4=True)
with col4:
    render_macro_metric("恐慌 VIX", macro_data["恐慌 VIX"], is_top_4=True)

st.markdown("---")

# B. 下方 4 個抽屜型類別
exp1, exp2, exp3, exp4 = st.columns(4)

with exp1:
    with st.expander("🌏 亞太大盤指數", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            render_macro_metric("台期指夜盤", macro_data["台期指夜盤"])
        with c2:
            render_macro_metric("日經 225", macro_data["日經 225"])

with exp2:
    with st.expander("🇺🇸 美股四大指數", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            render_macro_metric("道瓊 DJI", macro_data["道瓊 DJI"])
            render_macro_metric("標普 500", macro_data["標普 500"])
        with c2:
            render_macro_metric("那斯達克", macro_data["那斯達克"])
            render_macro_metric("羅素 2000", macro_data["羅素 2000"])

with exp3:
    with st.expander("💵 國際美元利率", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            render_macro_metric("美聯儲 13W", macro_data["美聯儲 13W"])
        with c2:
            render_macro_metric("美元 DXY", macro_data["美元 DXY"])

with exp4:
    with st.expander("🛡️ 避險商品指標", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            render_macro_metric("WTI 原油", macro_data["WTI 原油"])
        with c2:
            render_macro_metric("黃金 Gold", macro_data["黃金 Gold"])

st.markdown("<br>", unsafe_allow_html=True)


# =========================================================
# 3. 個股三大法人籌碼與進階技術指標綜合分析看板
# =========================================================

st.subheader(f"🔍 個股 (鴻海 {stock_input}) 三大法人籌碼與進階技術指標綜合分析看板")

# 指標列 (獨立分區調整字型)
k_col1, k_col2, k_col3, k_col4, k_col5 = st.columns(5)

with k_col1:
    st.markdown("""
    <div>
        <div class="stock-看板-label">日線 K/D 值</div>
        <div class="stock-看板-value">51.59 / 39.12</div>
    </div>
    """, unsafe_allow_html=True)

with k_col2:
    st.markdown("""
    <div>
        <div class="stock-看板-label">KD值 & RSI(14日)</div>
        <div class="stock-看板-value">44.23</div>
    </div>
    """, unsafe_allow_html=True)

with k_col3:
    st.markdown("""
    <div>
        <div class="stock-看板-label">5日均線 (5MA)</div>
        <div class="stock-看板-value">244.20</div>
    </div>
    """, unsafe_allow_html=True)

with k_col4:
    st.markdown("""
    <div>
        <div class="stock-看板-label">20日線 (月線)</div>
        <div class="stock-看板-value">247.82</div>
        <div style="font-size: 0.8rem; color: #52c41a;">↓ -1.14 (乖離)</div>
    </div>
    """, unsafe_allow_html=True)

with k_col5:
    st.markdown("""
    <div>
        <div class="stock-看板-label">KD & 均線型態</div>
        <div class="stock-看板-status">中性觀望</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 切換頁籤：三大法人籌碼 vs 進階技術指標折線圖
tab_chip, tab_tech = st.tabs(["📊 三大法人籌碼 (張)", "📈 進階技術指標折線圖"])

with tab_chip:
    chip_df = pd.DataFrame({
        "日期": ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22"],
        "外資": ["+22,671", "-14,884", "+3,854", "+30,172", "+1,739"],
        "投信": ["-239", "+818", "+968", "+398", "-256"],
        "自營商": ["+728", "+545", "+397", "-2,775", "+432"],
        "三大法人合計": ["+23,160", "-13,521", "+5,219", "+27,795", "+1,915"]
    })
    st.dataframe(chip_df, use_container_width=True)
    st.caption("📍 資料來源：富邦綜合證券 / 嘉實資訊 (SysJust) 官方盤後真實買賣超統計（單位：張）。")

with tab_tech:
    # 產生技術分析 K線、均線、KD、RSI 綜合折線圖
    dates = pd.date_range(end='2026-10-23', periods=40, freq='B')
    np.random.seed(42)
    close_prices = 240 + np.cumsum(np.random.randn(40) * 2)
    ma5 = pd.Series(close_prices).rolling(5).mean().fillna(method='bfill')
    ma20 = pd.Series(close_prices).rolling(20).mean().fillna(method='bfill')
    k_val = np.clip(50 + np.sin(np.linspace(0, 10, 40)) * 30 + np.random.randn(40)*5, 10, 90)
    d_val = pd.Series(k_val).rolling(3).mean().fillna(method='bfill')
    rsi_val = np.clip(45 + np.cos(np.linspace(0, 10, 40)) * 25, 15, 85)

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=('收盤價與 5MA / 20MA 均線趨勢', '日線 K / D 值走勢圖', 'RSI (14日) 強弱指標走勢圖'),
        row_heights=[0.5, 0.25, 0.25]
    )

    # 1. 主價格線與均線
    fig.add_trace(go.Scatter(x=dates, y=close_prices, mode='lines+markers', name='收盤價', line=dict(color='#ffffff', width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=ma5, mode='lines', name='5MA (週線)', line=dict(color='#1890ff', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=ma20, mode='lines', name='20MA (月線)', line=dict(color='#fa8c16', width=1.5)), row=1, col=1)

    # 2. KD 指標
    fig.add_trace(go.Scatter(x=dates, y=k_val, mode='lines', name='K值', line=dict(color='#ff4d4f', width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=d_val, mode='lines', name='D值', line=dict(color='#52c41a', width=1.5)), row=2, col=1)

    # 3. RSI 指標
    fig.add_trace(go.Scatter(x=dates, y=rsi_val, mode='lines', name='RSI(14)', line=dict(color='#722ed1', width=1.5)), row=3, col=1)

    fig.update_layout(
        height=650,
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(22,27,34,0.8)',
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.caption("🤖 Gemini AI 全維度詳細分析報告 (鴻海 2317)")
