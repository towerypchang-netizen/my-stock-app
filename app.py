import os
import time
import json
import re
from datetime import datetime, timedelta
import streamlit as st
import yfinance as yf
import requests
import pandas as pd

# 設定網頁標題與寬版佈局
st.set_page_config(page_title="AI 全球宏觀與台股 Top-Down 策略分析系統", layout="wide")

# 自訂 CSS：大標題縮小、台股漲跌色、側邊欄日期緊湊同行
st.markdown(
    """
    <style>
    /* 大標題縮小至與 ### / subheader 相同大小 */
    h1 { font-size: 1.5rem !important; margin-bottom: 1rem !important; }
    
    /* 強制側邊欄日期選擇器 Label 與 Input 在同一行緊密排列 */
    [data-testid="stSidebar"] [data-testid="stDateInput"] {
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: flex-start !important;
    }
    [data-testid="stSidebar"] [data-testid="stDateInput"] label {
        margin-right: 8px !important;
        margin-bottom: 0px !important;
        white-space: nowrap !important;
        font-weight: bold !important;
        font-size: 0.9rem !important;
        min-width: 210px !important;
    }
    [data-testid="stSidebar"] [data-testid="stDateInput"] > div {
        flex-grow: 1 !important;
    }

    /* 1. 針對所有向上箭頭 (Up) 與相關容器：強制紅字、紅箭頭、淡紅背景 */
    [data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Up"] {
        fill: #ff4d4f !important;
    }
    [data-testid="stMetricDelta"]:has(svg[data-testid="stMetricDeltaIcon-Up"]) {
        color: #ff4d4f !important;
        background-color: rgba(255, 77, 79, 0.15) !important;
    }
    [data-testid="stMetricDelta"]:has(svg[data-testid="stMetricDeltaIcon-Up"]) * {
        color: #ff4d4f !important;
    }

    /* 2. 針對所有向下箭頭 (Down) 與相關容器：強制綠字、綠箭頭、淡綠背景 */
    [data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Down"] {
        fill: #52c41a !important;
    }
    [data-testid="stMetricDelta"]:has(svg[data-testid="stMetricDeltaIcon-Down"]) {
        color: #52c41a !important;
        background-color: rgba(82, 196, 26, 0.15) !important;
    }
    [data-testid="stMetricDelta"]:has(svg[data-testid="stMetricDeltaIcon-Down"]) * {
        color: #52c41a !important;
    }

    /* 看板數字與標籤字型調整 */
    [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.95rem !important; }
    html, body, [class*="css"] { font-size: 16px; }
    @media (max-width: 768px) {
        html, body, [class*="css"] { font-size: 13.5px !important; }
        [data-testid="stSidebar"] { width: 100% !important; }
        [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 金鑰安全讀取
FINMIND_TOKEN = st.secrets.get("FINMIND_TOKEN", os.getenv("FINMIND_TOKEN", ""))
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

# 初始化 Session State
if "daily_picks" not in st.session_state:
    st.session_state.daily_picks = pd.DataFrame(
        columns=["上漲率預估", "族群", "股名", "股號", "當前實價", "建議進場", "建議退場"],
        data=[
            ["--%", "---", "---", "---", "---", "---", "---"],
            ["--%", "---", "---", "---", "---", "---", "---"],
            ["--%", "---", "---", "---", "---", "---", "---"]
        ]
    )

# 多模型自動降級 Gemini REST API 呼叫函式
def call_gemini_with_retry(prompt, max_retries=3):
    if not GEMINI_API_KEY:
        raise ValueError("Streamlit Secrets 中未找到 GEMINI_API_KEY，請確認設定。")
        
    api_key_clean = GEMINI_API_KEY.strip()
    models_to_try = ["gemini-3.6-flash", "gemini-1.5-flash"]
    
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={api_key_clean}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        for attempt in range(max_retries):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
                res_data = resp.json()
                
                if resp.status_code == 200:
                    candidates = res_data.get("candidates", [])
                    if candidates and len(candidates) > 0:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and len(parts) > 0:
                            return parts[0].get("text", "")
                elif resp.status_code == 429:
                    if attempt < max_retries - 1:
                        time.sleep(3 * (attempt + 1))
                        continue
                elif resp.status_code == 404:
                    break
            except Exception as e:
                if attempt == max_retries - 1 and model_name == models_to_try[-1]:
                    raise e
                    
    fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key_clean}"
    resp = requests.post(fallback_url, headers=headers, json=payload, timeout=30)
    res_data = resp.json()
    if resp.status_code == 200:
        candidates = res_data.get("candidates", [])
        if candidates and len(candidates) > 0:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and len(parts) > 0:
                return parts[0].get("text", "")
                
    err_msg = res_data.get("error", {}).get("message", resp.text)
    raise ValueError(f"API 請求失敗 ({resp.status_code}): {err_msg}")

# 即時台股價格抓取
def get_realtime_tw_price(stock_id):
    try:
        ticker_symbol = stock_id + ".TW"
        ticker = yf.Ticker(ticker_symbol)
        data = ticker.history(period="5d")
        if data.empty or len(data) == 0:
            ticker_symbol = stock_id + ".TWO"
            ticker = yf.Ticker(ticker_symbol)
            data = ticker.history(period="5d")
        if not data.empty:
            return round(float(data['Close'].iloc[-1]), 2)
    except Exception:
        pass
    return None

# 全球數據抓取 (含主要指數)
@st.cache_data(ttl=1800)
def get_macro_data(target_date_str):
    macro_tickers = {
        "道瓊工業": "^DJI",
        "標普500": "^GSPC",
        "那斯達克": "^IXIC",
        "費城半導體": "^SOX",
        "日經225": "^N225",
        "台灣加權": "^TWII"
    }
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    start_dt = target_dt - timedelta(days=10)
    macro_summary = {}
    for name, symbol in macro_tickers.items():
        try:
            data = yf.Ticker(symbol).history(start=start_dt.strftime("%Y-%m-%d"), end=(target_dt + timedelta(days=1)).strftime("%Y-%m-%d"))
            data = data.dropna(subset=['Close'])
            if not data.empty and len(data) >= 2:
                latest = data['Close'].iloc[-1]
                start = data['Close'].iloc[0]
                change = ((latest - start) / start) * 100
                macro_summary[name] = {"val": f"{latest:.2f}", "change": f"{change:+.2f}%"}
            else:
                macro_summary[name] = {"val": "資料更新中", "change": "0.00%"}
        except Exception:
            macro_summary[name] = {"val": "N/A", "change": "0.00%"}
    return macro_summary

# 類股數據抓取
@st.cache_data(ttl=1800)
def get_taiwan_sector_performance(target_date_str):
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    start_dt = target_dt - timedelta(days=10)
    url = "https://api.finmindtrade.com/api/v4/data"
    parameter = {
        "dataset": "TaiwanStockMarketSectorIndex",
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": target_date_str,
        "token": FINMIND_TOKEN,
    }
    try:
        resp = requests.get(url, params=parameter)
        data = resp.json()
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            df = pd.DataFrame(data["data"])
            latest_date = df['date'].max()
            first_date = df['date'].min()
            df_latest = df[df['date'] == latest_date].set_index('industry_category')['close']
            df_first = df[df['date'] == first_date].set_index('industry_category')['close']
            change_pct = ((df_latest - df_first) / df_first * 100).dropna()
            top_sectors = change_pct.sort_values(ascending=False).head(3).to_dict()
            bottom_sectors = change_pct.sort_values().head(3).to_dict()
            return {
                "領漲強勢產業": {k: f"{v:+.2f}%" for k, v in top_sectors.items()},
                "領跌弱勢產業": {k: f"{v:+.2f}%" for k, v in bottom_sectors.items()}
            }
    except Exception:
        pass
    return "無法取得類股數據"

# 籌碼數據抓取
@st.cache_data(ttl=1800)
def get_stock_chip(stock_id, target_date_str):
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    start_dt = target_dt - timedelta(days=14)
    url = "https://api.finmindtrade.com/api/v4/data"
    parameter = {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": stock_id,
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": target_date_str,
        "token": FINMIND_TOKEN,
    }
    resp = requests.get(url, params=parameter)
    data = resp.json()
    if data.get("msg") == "success" and len(data.get("data", [])) > 0:
        return pd.DataFrame(data["data"]).tail(6)[['date', 'name', 'buy', 'sell']]
    return pd.DataFrame()

# 生成 AI 精選股票
def generate_daily_picks(macro_data, sector_data, price_limit, target_date_str):
    price_limit_str = f"單股價格低於 {price_limit} 元" if price_limit and price_limit > 0 else "股價不限"
    prompt_select = (
        "請作為台股選股分析師，基準日期：" + str(target_date_str) + "。\n"
        "限制：" + price_limit_str + "。\n"
        "大盤：" + str(macro_data) + "\n"
        "強勢族群：" + str(sector_data) + "\n"
        "請挑選3檔符合強勢族群的台股個股，並嚴格只回傳 JSON 陣列，格式如：\n"
        '[{"上漲率預估":"75%","族群":"半導體","股名":"台積電","股號":"2330"}]\n'
        "不要包含任何Markdown標記。"
    )
    res_raw = call_gemini_with_retry(prompt_select)
    
    json_match = re.search(r'\[.*\]', res_raw, re.DOTALL)
    clean_json = json_match.group(0) if json_match else res_raw.strip()
    picks = json.loads(clean_json)
    
    final_results = []
    for item in picks:
        stock_id = item.get("股號")
        real_p = get_realtime_tw_price(stock_id)
        if real_p:
            item["當前實價"] = f"{real_p:.2f}"
            item["建議進場"] = f"{round(real_p * 0.985, 2):.2f}"
            item["建議退場"] = f"{round(real_p * 1.08, 2):.2f}"
        else:
            item["當前實價"] = "查無即時價"
            item["建議進場"] = "---"
            item["建議退場"] = "---"
        final_results.append(item)
    return final_results

# 生成詳細報告
def ai_single_stock_analysis(macro_data, sector_data, stock_id, chip_data, capital, target_date_str):
    capital_str = f"{capital:,} 元" if capital and capital > 0 else "未限定金額"
    real_price = get_realtime_tw_price(stock_id)
    price_info_str = f"當前真實市場成交價：{real_price} 元" if real_price else "即時股價：需參考市場現價"
    
    prompt = (
        "請作為華爾街 Top-Down 分析師。基準日期：" + str(target_date_str) + "。\n"
        "個股：" + str(stock_id) + "，" + price_info_str + "，預計資金：" + capital_str + "。\n"
        "全球宏觀：" + str(macro_data) + "\n"
        "台股族群：" + str(sector_data) + "\n"
        "籌碼：" + (chip_data.to_string() if not chip_data.empty else "無數據") + "\n"
        "請輸出繁體中文詳細報告：\n"
        "1. 全球宏觀與科技大勢總結\n"
        "2. 台股主流產業與資金流向研判\n"
        "3. 個股籌碼與連動分析\n"
        "4. 進退場價位規劃與部位建議\n"
        "5. 未來1週上漲機率估算"
    )
    return call_gemini_with_retry(prompt)

# 主 UI 邏輯
st.title("📈 AI 全球宏觀與台股 Top-Down 策略分析系統")

# 市場看板基準日期：加註資料來源並同行靠靠
selected_date = st.sidebar.date_input("市場看板基準日期 (資料來源：Yahoo Finance)", value=datetime.today())

target_date_str = selected_date.strftime("%Y-%m-%d")

macro_data = get_macro_data(target_date_str)
sector_data = get_taiwan_sector_performance(target_date_str)

# 取得當前操作的即時時間
current_time_str = datetime.now().strftime("%m/%d %H:%M:%S")
st.sidebar.markdown(f"### 🎯 今日 [{current_time_str}] AI 精選股票預測")

# 輸入框預設空白
price_limit_input = st.sidebar.number_input("設定股價金額上限 (新台幣元)", min_value=0, value=None, placeholder="請輸入金額上限", step=10)
price_limit = price_limit_input if price_limit_input is not None else 0

if st.sidebar.button("🚀 產生當日 AI 精選股票", use_container_width=True):
    with st.spinner("🤖 AI 正在掃描族群與即時股價..."):
        try:
            picks_data = generate_daily_picks(macro_data, sector_data, price_limit, target_date_str)
            st.session_state.daily_picks = pd.DataFrame(picks_data)
            st.sidebar.success("更新成功！")
        except Exception as e:
            st.sidebar.error(f"生成失敗: {e}")

st.sidebar.dataframe(st.session_state.daily_picks, hide_index=True, use_container_width=True)
st.sidebar.divider()

st.sidebar.markdown("### ⚙️ 個股詳細分析與資金設定")

# 輸入框預設空白
stock_id = st.sidebar.text_input("輸入台股代碼", value="", placeholder="例如: 2330")
capital_input = st.sidebar.number_input("預計進場金額 (新台幣元)", min_value=0, value=None, placeholder="請輸入金額", step=10000)
capital = capital_input if capital_input is not None else 0

btn_analyze_stock = st.sidebar.button("📊 開始 AI 個股分析", type="primary", use_container_width=True)

st.subheader(f"🌐 全球宏觀市場看板 ({target_date_str})")
cols = st.columns([1, 1, 1, 1, 1, 1])
idx = 0
for name, info in macro_data.items():
    with cols[idx % 6]:
        st.metric(label=name, value=info["val"], delta=info["change"], delta_color="inverse")
    idx += 1

st.divider()

col_left, col_right = st.columns([1, 1])
with col_left:
    st.subheader(f"📊 台股強弱勢族群 ({target_date_str})")
    if isinstance(sector_data, dict):
        st.write("**領漲強勢產業：**", sector_data.get("領漲強勢產業"))
        st.write("**領跌弱勢產業：**", sector_data.get("領跌弱勢產業"))

with col_right:
    st.subheader(f"🔍 個股 ({stock_id if stock_id else '未指定'}) 三大法人籌碼")
    if stock_id:
        chip_df = get_stock_chip(stock_id, target_date_str)
        if not chip_df.empty:
            st.dataframe(chip_df, use_container_width=True)
        else:
            st.info("尚無籌碼資料或代碼錯誤")
    else:
        st.info("請於左側輸入台股代碼後檢視籌碼")

st.divider()

if btn_analyze_stock:
    if not stock_id:
        st.warning("請先在左側欄位輸入台股代碼！")
    else:
        chip_df = get_stock_chip(stock_id, target_date_str)
        with st.spinner(f"🤖 AI 正在分析 {stock_id}..."):
            try:
                report = ai_single_stock_analysis(macro_data, sector_data, stock_id, chip_data=chip_df, capital=capital, target_date_str=target_date_str)
                st.subheader(f"🤖 Gemini AI 個股詳細分析報告 ({stock_id})")
                st.markdown(report)
            except Exception as e:
                st.error(f"分析生成失敗: {e}")