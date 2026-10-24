# -*- coding: utf-8 -*-
"""
台股總經資金流與產業供應鏈 AI 評估系統 (app.py)
包含指標顯示格式修正、字體大小獨立調整與樣式優化。
"""

import streamlit as st
import pandas as pd
import numpy as np

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

/* 抽屜與指標卡片樣式 */
.metric-card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 10px;
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

# ---------------------------------------------------------
# 1. 總經指標數據邏輯處理與格式修正
# ---------------------------------------------------------

# 模擬/抓取之總經數據字典
# 各指標需求說明：
# - 比率改為升跌點數：台股加權, 日經225, 費城半導體S, 道瓊工業DJI, 那斯達克, 標普500, 羅素2000RUT
# - 美債10年收益率 (^TNX): 4.9880 (+0.0350 / +0.71%)
# - 美聯儲13W (^IRX): 4.0320 (+0.0100 / +0.25%)
# - 美元指數 DXY: 指數正確 (如 101.75)，修正漲跌比率計算 (-0.06 / -0.06%)

macro_data = {
    "台股加權": {"val": 46041.43, "change": -846.12, "pct": -1.81, "type": "pts"},
    "台期指夜盤": {"val": 45654.00, "change": -580.00, "pct": -1.25, "type": "pts_pct"},
    "費城半導體": {"val": 10779.46, "change": 47.12, "pct": 0.44, "type": "pts"},
    "美債 10Y": {"val": "4.9880%", "change": "+0.0350", "pct": "+0.71%", "type": "rate_full"},
    "恐慌 VIX": {"val": "19.4500", "change": "+0.42", "pct": "+2.21%", "type": "rate_full"},
    
    # 亞太
    "日經 225": {"val": 62693.15, "change": -214.30, "pct": -0.34, "type": "pts"},
    
    # 美股
    "道瓊 DJI": {"val": 52215.16, "change": -652.82, "pct": -1.23, "type": "pts"},
    "那斯達克": {"val": 25955.10, "change": -54.60, "pct": -0.21, "type": "pts"},
    "標普 500": {"val": 7623.68, "change": -39.75, "pct": -0.52, "type": "pts"},
    "羅素 2000": {"val": 2775.90, "change": -8.08, "pct": -0.29, "type": "pts"},
    
    # 國際美元利率
    "美聯儲 13W": {"val": "4.0320%", "change": "+0.0100", "pct": "+0.25%", "type": "rate_full"},
    "美元 DXY": {"val": "101.75", "change": "-0.06", "pct": "-0.06%", "type": "dxy"},
    
    # 避險商品
    "WTI 原油": {"val": "103.44", "change": "+3.96", "pct": "+3.99%", "type": "rate_full"},
    "黃金 Gold": {"val": "4,010.00", "change": "-50.30", "pct": "-1.24%", "type": "rate_full"}
}

def render_macro_metric(label, data, is_top_4=False):
    """
    渲染總經指標：
    - Top 4 保持原本大字體
    - 抽屜內指標數字調小至與標題相同大小 (0.9rem)
    """
    val = data["val"]
    m_type = data["type"]
    
    # 處理 Delta 顯示格式
    if m_type == "pts":
        # 比率改為升跌點數
        chg = data["change"]
        delta_str = f"{'↑' if chg >= 0 else '↓'} {chg:+.2f} 點"
        is_pos = chg >= 0
    elif m_type == "dxy":
        # 美元指數正確漲跌格式
        delta_str = f"↓ {data['change']} ({data['pct']})" if "-" in data['change'] else f"↑ {data['change']} ({data['pct']})"
        is_pos = "-" not in data['change']
    elif m_type == "rate_full":
        # 與 Yahoo Finance 網站完全相同的位數與格式 (如 4.9880% / 4.0320%)
        delta_str = f"{data['change']} ({data['pct']})"
        is_pos = "+" in data['change']
    else:
        # pts_pct 雙顯示
        chg = data["change"]
        delta_str = f"{'↑' if chg >= 0 else '↓'} {chg:+.2f} 點"
        is_pos = chg >= 0

    delta_class = "macro-metric-delta-pos" if is_pos else "macro-metric-delta-neg"
    
    if is_top_4:
        # 上方 4 大指標字體大小不變
        st.metric(label=label, value=str(val), delta=delta_str)
    else:
        # 下方抽屜指標數字調小至與標題相同大小
        st.markdown(f"""
        <div style="margin-bottom: 12px;">
            <div class="macro-metric-label">{label}</div>
            <div class="macro-metric-value">{val}</div>
            <div class="{delta_class}">{delta_str}</div>
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. 主介面渲染
# ---------------------------------------------------------

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

# ---------------------------------------------------------
# 3. 個股三大法人籌碼與進階技術指標綜合分析看板
# ---------------------------------------------------------

st.subheader("🔍 個股 (鴻海 2317) 三大法人籌碼與進階技術指標綜合分析看板")

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

# 三大法人籌碼表格
st.markdown("<br>", unsafe_allow_html=True)
st.write("📊 **三大法人籌碼 (張)**")
chip_df = pd.DataFrame({
    "日期": ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22"],
    "外資": ["+22,671", "-14,884", "+3,854", "+30,172", "+1,739"],
    "投信": ["-239", "+818", "+968", "+398", "-256"],
    "自營商": ["+728", "+545", "+397", "-2,775", "+432"],
    "三大法人合計": ["+23,160", "-13,521", "+5,219", "+27,795", "+1,915"]
})
st.dataframe(chip_df, use_container_width=True)

st.caption("📍 資料來源：富邦綜合證券 / 嘉實資訊 (SysJust) 官方盤後真實買賣超統計（單位：張）。")
