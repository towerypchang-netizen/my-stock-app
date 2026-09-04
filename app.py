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

# 自訂 CSS：響應式裝置與顏色設定
st.markdown(
    "<style>\n"
    "[data-testid=\"stMetricDelta\"] svg[data-testid=\"stMetricDeltaIcon-Up\"] { fill: #ff4d4f !important; }\n"
    "[data-testid=\"stMetricDelta\"] div:has(svg[data-testid=\"stMetricDeltaIcon-Up\"]) { color: #ff4d4f !important; }\n"
    "[data-testid=\"stMetricDelta\"] svg[data-testid=\"stMetricDeltaIcon-Down\"] { fill: #52c41a !important; }\n"
    "[data-testid=\"stMetricDelta\"] div:has(svg[data-testid=\"stMetricDeltaIcon-Down\"]) { color: #52c41a !important; }\n"
    "html, body, [class*=\"css\"] { font-size: 16px; }\n"
    "@media (max-width: 768px) {\n"
    "    html, body, [class*=\"css\"] { font-size: 13.5px !important; }\n"
    "    [data-testid=\"stSidebar\"] { width: 100% !important; }\n"
    "}\n"
    "</style>",
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

# 直連 Google 官方 REST API (自動列出精確報錯原因)
def call_gemini_with_retry(prompt):
    if not GEMINI_API_KEY:
        raise ValueError("Streamlit Secrets 中未找到 GEMINI_API_KEY，請確認設定。")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY.strip()}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    res_data = resp.json()
    
    if resp.status_code == 200:
        candidates = res_data.get("candidates", [])
        if candidates and len(candidates) > 0:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and len(parts) > 0:
                return parts[0].get("text", "")
        raise ValueError("Google API 回傳成功，但未包含內容 (candidates 為空)。")
    else:
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

# 全球數據抓取
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
    price_limit_str = f"單股價格低於 {price_limit} 元" if price_limit > 0 else "股價不限"
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
    capital_str = f"{capital:,} 元" if capital > 0 else "未限定金額"
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

selected_date = st.sidebar.date_input("市場看板基準日期", value=datetime.today())
target_date_str = selected_date.strftime("%Y-%m-%d")

macro_data = get_macro_data(target_date_str)
sector_data = get_taiwan_sector_performance(target_date_str)

st.sidebar.markdown("### 🎯 當日 AI 精選股票預測")
price_limit = st.sidebar.number_input("設定股價金額上限 (新台幣元)", min_value=0, value=200, step=10)

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
stock_id = st.sidebar.text_input("輸入台股代碼", value="2330")
capital = st.sidebar.number_input("預計進場金額 (新台幣元)", min_value=0, value=100000, step=10000)

btn_analyze_stock = st.sidebar.button("📊 開始 AI 個股分析", type="primary", use_container_width=True)

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
    with st.spinner(f"🤖 AI 正在分析 {stock_id}..."):
        try:
            report = ai_single_stock_analysis(macro_data, sector_data, stock_id, chip_df, capital, target_date_str)
            st.subheader(f"🤖 Gemini AI 個股詳細分析報告 ({stock_id})")
            st.markdown(report)
        except Exception as e:
            st.error(f"分析生成失敗: {e}")