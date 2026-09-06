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

# 自訂 CSS：大標題縮小、台股漲跌色
st.markdown(
    """
    <style>
    h1 { font-size: 1.5rem !important; margin-bottom: 1rem !important; }
    
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

# 金鑰安全清理與讀取
def clean_key(raw):
    if not raw:
        return ""
    k = str(raw).strip()
    k = k.replace('"', '').replace("'", "")
    return k

FINMIND_TOKEN = clean_key(st.secrets.get("FINMIND_TOKEN", os.getenv("FINMIND_TOKEN", "")))
GEMINI_API_KEY = clean_key(st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", "")))

# 取得台灣標準時間 (UTC+8)
def get_taiwan_now():
    return datetime.utcnow() + timedelta(hours=8)

# 初始化 Session State
if "daily_picks" not in st.session_state:
    st.session_state.daily_picks = pd.DataFrame(
        columns=["上漲率預估", "族群", "股名", "股號", "當前實價", "建議進場", "建議退場", "波段期間"],
        data=[
            ["--%", "---", "---", "---", "---", "---", "---", "---"],
            ["--%", "---", "---", "---", "---", "---", "---", "---"],
            ["--%", "---", "---", "---", "---", "---", "---", "---"]
        ]
    )

if "last_predict_time" not in st.session_state:
    st.session_state.last_predict_time = get_taiwan_now().strftime("%m/%d %H:%M:%S")

# API 呼叫函式（付費版單一金鑰高穩定調用）
def call_gemini_with_retry(prompt, max_retries=3):
    if not GEMINI_API_KEY:
        raise ValueError("Secrets 中未找到有效的 GEMINI_API_KEY，請確認設定。")
        
    target_model = "gemini-3.6-flash"
    last_err = ""
    
    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
            )
            if response and response.text:
                return response.text
        except Exception as e:
            err_msg = str(e)
            last_err = f"嘗試 {attempt+1}/{max_retries} 失敗: {err_msg}"
            time.sleep(2)

    raise ValueError(f"Gemini API 呼叫失敗 [{last_err}]，請稍後重試。")

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

# 生成 AI 精選股票（支援自定義族群與價格區間自由組合）
def generate_daily_picks(macro_data, sector_data, min_price, max_price, custom_sector, target_date_str):
    cond_list = []
    if min_price > 0:
        cond_list.append(f"最低不得低於 {min_price} 元")
    if max_price > 0:
        cond_list.append(f"最高不得超過 {max_price} 元")
        
    price_limit_str = f"【硬性股價區間限制】：{', '.join(cond_list)}" if cond_list else "股價不限"
    
    if custom_sector and custom_sector.strip() != "":
        sector_limit_str = f"【指定產業或題材族群限制】：必須嚴格從「{custom_sector.strip()}」相關個股中挑選（例如次產業、細分板塊或熱門概念股）"
    else:
        sector_limit_str = "【指定產業或題材族群限制】：由 AI 結合大盤與強勢族群自主推薦當紅主流"

    prompt_select = (
        "請作為台股選股分析師，基準日期：" + str(target_date_str) + "。\n"
        "價格條件：" + price_limit_str + "。\n"
        "族群條件：" + sector_limit_str + "。\n"
        "大盤：" + str(macro_data) + "\n"
        "強勢族群參考：" + str(sector_data) + "\n"
        "請挑選 6 檔符合上述條件的台股個股，並評估波段期間。\n"
        "請嚴格只回傳 JSON 陣列，格式如：\n"
        '[{"上漲率預估":"75%","族群":"半導體/記憶體","股名":"南亞科","股號":"2408","波段期間":"5-10天"}]\n'
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
            if min_price > 0 and real_p < min_price:
                continue
            if max_price > 0 and real_p > max_price:
                continue
                
            item["當前實價"] = f"{real_p:.2f}"
            item["建議進場"] = f"{round(real_p * 0.985, 2):.2f}"
            item["建議退場"] = f"{round(real_p * 1.08, 2):.2f}"
        else:
            item["當前實價"] = "查無即時價"
            item["建議進場"] = "---"
            item["建議退場"] = "---"
        
        if "波段期間" not in item:
            item["波段期間"] = "5-10天"
            
        final_results.append(item)
        
        if len(final_results) >= 3:
            break
            
    while len(final_results) < 3:
        final_results.append({
            "上漲率預估": "--%", "族群": "無符合條件", "股名": "無符合股票",
            "股號": "----", "當前實價": "---", "建議進場": "---",
            "建議退場": "---", "波段期間": "---"
        })
        
    return final_results

# 生成詳細報告（加入頂端精闢結論與專業提示詞）
def ai_single_stock_analysis(macro_data, sector_data, stock_id, chip_data, capital, target_date_str):
    capital_str = f"{capital:,} 元" if capital and capital > 0 else "未限定金額"
    real_price = get_realtime_tw_price(stock_id)
    price_info_str = f"當前真實市場成交價：{real_price} 元" if real_price else "即時股價：需參考市場現價"
    
    chip_str = chip_data.to_string(index=False) if isinstance(chip_data, pd.DataFrame) and not chip_data.empty else "無最新籌碼數據"
    
    prompt = (
        "請作為頂級華爾街資深 Top-Down (自上而下) 總經與台股操盤手分析師。基準日期：" + str(target_date_str) + "。\n"
        "分析標的：" + str(stock_id) + "，" + price_info_str + "，預計資金配置：" + capital_str + "。\n"
        "全球宏觀背景：" + str(macro_data) + "\n"
        "台股產業族群表現：" + str(sector_data) + "\n"
        "近期三大法人籌碼細節：" + chip_str + "\n\n"
        "請輸出繁體中文詳細報告，並【嚴格遵守以下結構與順序】：\n\n"
        "=== 第一部分：【實戰結論摘要】（必須放置於報告最前端，內容以簡單明瞭為主） ===\n"
        "請直接給出一至兩段精闢的操盤結論。例如判斷是否處於低檔盤整、是否連續上漲不宜追高，或是明確給出建議買進價、賣出價與波段操作天數。\n\n"
        "=== 第二部分：【深度分析報告內文】 ===\n"
        "1. 全球宏觀與科技大勢總結\n"
        "2. 台股主流產業與資金流向研判\n"
        "3. 籌碼面與法人動向連動分析\n"
        "4. 進退場價位規劃、預估波段操作天數與部位建議\n"
        "5. 未來1週上漲機率估算與風險回報評估"
    )
    return call_gemini_with_retry(prompt)

# 主 UI 邏輯
st.title("📈 AI 全球宏觀與台股 Top-Down 策略分析系統")

taiwan_now = get_taiwan_now()
target_date_str = taiwan_now.strftime("%Y-%m-%d")
display_date_str = taiwan_now.strftime("%Y / %m / %d")

st.sidebar.markdown(
    f"""
    <div style="font-size: 0.9rem; font-weight: bold; margin-bottom: 12px; line-height: 1.8;">
        市場看板基準日期
        <span style="font-size: 0.75rem; color: #a0a0a0; font-weight: normal; margin-left: 4px;">(資料來源: Yahoo Finance)</span>
        <span style="background-color: #262730; border: 1px solid #464b5d; border-radius: 4px; padding: 2px 8px; color: #ff4d4f; font-weight: bold; margin-left: 8px;">{display_date_str}</span>
    </div>
    """,
    unsafe_allow_html=True
)

macro_data = get_macro_data(target_date_str)
sector_data = get_taiwan_sector_performance(target_date_str)

st.sidebar.markdown(f"### 🎯 今日 [{st.session_state.last_predict_time}] AI 預估上漲率最高前三檔")

# 自由輸入族群或題材欄位，並附上提示說明
st.sidebar.markdown("**指定產業族群或題材 (選填)**")
custom_sector = st.sidebar.text_input(
    "輸入族群或題材",
    value="",
    placeholder="例如: 記憶體、PCB、半導體、重電...",
    label_visibility="collapsed"
)
st.sidebar.markdown(
    "<div style='font-size: 0.75rem; color: #888888; margin-top: -6px; margin-bottom: 8px;'>"
    "💡 可輸入大類（如半導體）或細分題材（如記憶體、PCB、CPO、機器人）"
    "</div>",
    unsafe_allow_html=True
)

st.sidebar.markdown("**設定股價區間 (新台幣元)**")
p_col1, p_col2 = st.sidebar.columns(2)
with p_col1:
    min_price_input = st.number_input("最低價", min_value=0, value=None, placeholder="最低金額", step=10, label_visibility="collapsed")
with p_col2:
    max_price_input = st.number_input("最高價", min_value=0, value=None, placeholder="最高金額", step=10, label_visibility="collapsed")

min_price = min_price_input if min_price_input is not None else 0
max_price = max_price_input if max_price_input is not None else 0

if st.sidebar.button("🚀 產生今日AI預估上漲率最高前三檔", type="primary", use_container_width=True):
    with st.spinner("🤖 AI 正在結合自定義族群與即時股價掃描..."):
        try:
            picks_data = generate_daily_picks(macro_data, sector_data, min_price, max_price, custom_sector, target_date_str)
            st.session_state.daily_picks = pd.DataFrame(picks_data)
            st.session_state.last_predict_time = get_taiwan_now().strftime("%m/%d %H:%M:%S")
            st.sidebar.success("更新成功！")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"生成失敗: {e}")

st.sidebar.dataframe(st.session_state.daily_picks, hide_index=True, use_container_width=True)
st.sidebar.divider()

st.sidebar.markdown("### ⚙️ 個股詳細分析與資金設定")

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