import os
import time
import json
import re
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

# 多模型自動退回與重試機制
def call_gemini_with_retry(prompt, max_retries=3):
    models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash']
    
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    if attempt < max_retries - 1:
                        time.sleep(3 * (attempt + 1))
                        continue
                elif "404" in err_msg or "NOT_FOUND" in err_msg:
                    break
                if attempt == max_retries - 1 and model_name == models_to_try[-1]:
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

# 功能一：生成當日 3 檔精選股票 JSON
def generate_daily_picks(macro_data, sector_data, price_limit, target_date_str):
    price_limit_str = f"單股價格低於 {price_limit} 元" if price_limit > 0 else "股價不限"
    
    prompt_select = (
        "你是一位專業台股選股分析師。基準日期：" + str(target_date_str) + "。\n"
        "條件限制：" + price_limit_str + "。\n"
        "全球大盤：" + str(macro_data) + "\n"
        "台股強勢族群：" + str(sector_data) + "\n\n"
        "請從台股市場挑選 3 檔最符合當前強勢族群與美股連動的優質個股，並嚴格只回傳 JSON 格式陣列，格式範例如下：\n"
        '[\n'
        '  {"上漲率預估": "75%", "族群": "半導體", "股名": "台積電", "股號": "2330"},\n'
        '  {"上漲率預估": "70%", "族群": "記憶體", "股名": "華邦電", "股號": "2344"},\n'
        '  {"上漲率預估": "68%", "族群": "組裝", "股名": "廣達", "股號": "2382"}\n'
        ']\n'
        "不要加入 Markdown 標記或額外文字。"
    )
    
    res_raw = call_gemini_with_retry(prompt_select)
    
    json_match = re.search(r'\[.*\]', res_raw, re.DOTALL)
    if json_match:
        clean_json = json_match.group(0)
    else:
        clean_json = res_raw.strip()
        
    picks = json.loads(clean_json)
    
    final_results = []
    for item in picks:
        stock_id = item.get("股號")
        real_p = get_realtime_tw_price(stock_id)
        
        if real_p:
            buy_p = round(real_p * 0.985, 2)
            sell_p = round(real_p * 1.08, 2)
            item["當前實價"] = f"{real_p:.2f}"
            item["建議進場"] = f"{buy_p:.2f}"
            item["建議退場"] = f"{sell_p:.2f}"
        else:
            item["當前實價"] = "查無即時價"
            item["建議進場"] = "---"
            item["建議退場"] = "---"
            
        final_results.append(item)
        
    return final_results

# 功能二：個股 Top-Down 詳細報告
def ai_single_stock_analysis(macro_data, sector_data, stock_id, chip_data, capital, target_date_str):
    capital_str = f"{capital:,} 元" if capital > 0 else "未限定金額"
    real_price = get_realtime_tw_price(stock_id)
    price_info_str = f"當前真實市場成交價：{real_price} 元" if real_price else "即時股價：需參考市場現價"
    
    prompt = (
        "你是一位華爾街頂尖 Top-Down 分析師。基準日期：" + str(target_date_str) + "。\n"
        "個股：" + str(stock_id) + "，" + price_info_str + "，預計進場金額：" + capital_str + "。\n"
        "全球宏觀：" + str(macro_data) + "\n"
        "台股族群：" + str(sector_data) + "\n"
        "籌碼資料：" + (chip_data.to_string() if not chip_data.empty else "無數據") + "\n\n"
        "請輸出繁體中文詳細報告：\n"
        "1. **全球宏觀與科技大勢總結**\n"
        "2. **台股主流產業與資金流向研判**\n"
        "3. **個股 (" + str(stock_id) + ") 籌碼與連動分析**\n"
        "4. **進退場價位規劃與部位建議**（務必基於「" + price_info_str + "」來建議精確的進場價、止盈價、停損價、建議買進張數/零股）\n"
        "5. **未來 1 週上漲機率估算**"
    )
    return call_gemini_with_retry(prompt)

# ================= 畫面 UI 邏輯 =================
st.title("📈 AI 全球宏觀與台股 Top-Down 策略分析系統")

selected_date = st.sidebar.date_input("市場看板基準日期", value=datetime.today())
target_date_str = selected_date.strftime("%Y-%m-%d")

macro_data = get_macro_data(target_date_str)
sector_data = get_taiwan_sector_performance(target_date_str)

# ----------------- 側邊欄：功能一 -----------------
st.sidebar.markdown("### 🎯 當日 AI 精選股票預測")
price_limit = st.sidebar.number_input("設定股價金額上限 (新台幣元)", min_value=0, value=200, step=10, help="0 為不設定上限")

btn_generate_daily = st.sidebar.button("🚀 產生當日 AI 精選股票", type="secondary", use_container_width=True)

if btn_generate_daily:
    with st.spinner("🤖 AI 正在掃描族群，並同步驗證 Yahoo 即時股價中..."):
        try:
            picks_data = generate_daily_picks(macro_data, sector_data, price_limit, target_date_str)
            st.session_state.daily_picks = pd.DataFrame(picks_data)
            st.sidebar.success("即時驗證更新成功！")
        except Exception as e:
            st.sidebar.error(f"生成失敗，請稍候再試一次: {e}")

st.sidebar.dataframe(st.session_state.daily_picks, hide_index=True, use_container_width=True)
st.sidebar.divider()

# ----------------- 側邊欄：功能二 -----------------
st.sidebar.markdown("### ⚙️ 個股詳細分析與資金設定")
stock_id = st.sidebar.text_input("輸入台股代碼", value="2330")
capital = st.sidebar.number_input("預計進場金額 (新台幣元)", min_value=0, value=100000, step=10000)

btn_analyze_stock = st.sidebar.button("📊 開始 AI 個股分析", type="primary", use_container_width=True)

# ----------------- 主頁面展示 -----------------
st.subheader(f"🌐 全球宏觀市場看板 ({target_date_str})")

cols = st.columns([1, 1, 1, 1])
idx = 0
for name, info in macro_data.items():
    with cols[idx % 4]:
        st.metric(label=name, value=info["val"], delta=info["change"])
    idx += 1

st.divider()

col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader(f"📊 台股強弱勢族群 ({target_date_str})")
    if isinstance(sector_data, dict):
        st.write("**領漲強勢產業：**", sector_data.get("領漲強勢產業"))
        st.write("**領跌弱勢產業：**", sector_data.get("領跌弱勢產業"))

with col_right:
    st.subheader(f"🔍 個股 ({stock_id}) 三大法人籌碼")
    chip_df = get_stock_chip(stock_id, target_date_str)
    if not chip_df.empty:
        st.dataframe(chip_df, use_container_width=True)
    else:
        st.info("尚無籌碼資料或代碼錯誤")

st.divider()

if btn_analyze_stock:
    with st.spinner(f"🤖 AI 正在抓取 {stock_id} 即時行情並進行詳細分析..."):
        try:
            report = ai_single_stock_analysis(macro_data, sector_data, stock_id, chip_df, capital, target_date_str)
            st.subheader(f"🤖 Gemini AI 個股詳細分析報告 ({stock_id})")
            st.markdown(report)
        except Exception as e:
            st.error(f"分析生成失敗: {e}")