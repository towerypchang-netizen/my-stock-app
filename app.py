import os
import time
import json
from datetime import datetime, timedelta
import streamlit as st
import yfinance as yf
import requests
import pandas as pd
from google import genai

# 設定網頁標題與寬版佈局
st.set_page_config(page_title="AI 全球宏觀與台股 Top-Down 策略分析系統", layout="wide")

# 自訂 CSS：響應式裝置偵測
st.markdown("""
<style>
/* 1. 台股漲跌顏色習慣 (上漲紅色、下跌綠色) */
[data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Up"] { fill: #ff4d4f !important; }
[data-testid="stMetricDelta"] div:has(svg[data-testid="stMetricDeltaIcon-Up"]) { color: #ff4d4f !important; }
[data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Down"] { fill: #52c41a !important; }
[data-testid="stMetricDelta"] div:has(svg[data-testid="stMetricDeltaIcon-Down"]) { color: #52c41a !important; }

/* 2. 預設電腦/桌上型裝置字體大小 */
html, body, [class*="css"] {
    font-size: 16px;
}
h1 { font-size: 2.2rem !important; }
h2 { font-size: 1.8rem !important; }
h3 { font-size: 1.4rem !important; }

/* 3. 平板 / 手機橫向 */
@media (max-width: 992px) {
    html, body, [class*="css"] {
        font-size: 15px;
    }
    h1 { font-size: 1.8rem !important; }
    h2 { font-size: 1.5rem !important; }
    h3 { font-size: 1.2rem !important; }
}

/* 4. 手機直向自動最佳化 */
@media (max-width: 768px) {
    html, body, [class*="css"] {
        font-size: 13.5px !important;
    }
    h1 { font-size: 1.4rem !important; text-align: center; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; }
    
    .stMainBlockContainer {
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        padding-top: 1rem !important;
    }
    
    [data-testid="stSidebar"] {
        width: 100% !important;
    }
    
    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.03);
        padding: 8px !important;
        border-radius: 8px;
        margin-bottom: 5px;
    }
}
</style>
""", unsafe_allow_html=True)

# ================= 金鑰讀取設定 =================
FINMIND_TOKEN = st.secrets.get("FINMIND_TOKEN", os.getenv("FINMIND_TOKEN", ""))
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

client = genai.Client(api_key=GEMINI_API_KEY)
# ===============================================

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

# 帶有自動重試與避難機率的 Gemini 調用函式
def call_gemini_with_retry(prompt, model_name='gemini-2.5-flash', max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < max_retries - 1:
                    time.sleep(4 * (attempt + 1))
                    continue
            raise e

# 即時抓取台股真實股價函數
def get_realtime_tw_price(stock_id):
    try:
        ticker_symbol = f"{stock_id}.TW"
        ticker = yf.Ticker(ticker_symbol)
        data = ticker.history(period="5d")
        if data.empty or len(data) == 0:
            ticker_symbol = f"{stock_id}.TWO"
            ticker = yf.Ticker(ticker_symbol)
            data = ticker.history(period="5d")
        if not data.empty:
            real_price = round(float(data['Close'].iloc[-1]), 2)
            return real_price
    except Exception:
        pass
    return None

# 1. 資料抓取函數
@st.cache_data(ttl=1800)
def get_macro_data(target_date_str):
    macro_tickers = {
        "道瓊工業": "^DJI", "標普500": "^GSPC", "那斯達克": "^IXIC", "費城半導體": "^SOX",
        "美債10年殖利率": "^TNX", "美元指數": "DX-Y.NYB", "台積電ADR": "TSM", "輝達": "NVDA", "美光": "MU"
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

# 功能一：生成當日 3 檔精選股票 JSON (含真實股價校正與重試)
def generate_daily_picks(macro_data, sector_data, price_limit, target_date_str):
    price_limit_str = f"單股價格低於 {price_limit} 元" if price_limit > 0 else "股價不限"
    
    prompt_select = f"""
    你是一位專業台股選股分析師。基準日期：{target_date_str}。
    條件限制：{price_limit_str}。
    全球大盤：{macro_data}
    台股強勢族群：{sector_data}
    
    請從台股市場挑選 3 檔最符合當前強勢族群與美股連動的優質個股，並嚴格只回傳 JSON 格式陣列，格式如下：
    [
        {{"上漲率預估": "75%", "族群": "半導體", "股名": "台積電", "股號": "2330"}},
        {{"上漲率預估": "70%", "族群": "記憶體", "股名": "華邦電", "股號": "2344"}},
        {{"上漲率預估": "68%", "族群": "組裝", "股名": "廣達", "股號": "2382"}}
    ]
    不要加入 Markdown 標記或額外文字。
    """
    res_raw = call_gemini_with_retry(prompt_select, model_name='gemini-2.5-flash')
    res_text = res_raw.strip().replace("```json", "").replace("