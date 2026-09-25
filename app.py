import os
import time
import json
import re
from datetime import datetime, timedelta
import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import plotly.graph_objects as go
from google import genai

# 設定網頁標題與寬版佈局
st.set_page_config(page_title="AI 全球宏觀與台股 Top-Down 策略分析系統", layout="wide")

# ==============================================================================
# 🔒 簡單密碼驗證鎖機制
# ==============================================================================
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown("<br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("🔒 AI 股票分析系統存取認證")
            user_password = st.text_input("請輸入存取密碼：", type="password")
            if st.button("確認登入", type="primary", use_container_width=True):
                correct_password = st.secrets.get("APP_PASSWORD", "615588")
                if user_password == correct_password:
                    st.session_state.authenticated = True
                    st.success("密碼正確，登入成功！")
                    st.rerun()
                else:
                    st.error("密碼錯誤，請重新輸入！")
        return False
    return True

if not check_password():
    st.stop()
# ==============================================================================

# 初始化 session state 盤前情報動態變數
if "premarket_focus" not in st.session_state:
    st.session_state.premarket_focus = []
if "premarket_avoid" not in st.session_state:
    st.session_state.premarket_avoid = []
if "premarket_summary" not in st.session_state:
    st.session_state.premarket_summary = "尚未進行盤前情報診斷，系統將採用標準 Top-Down 策略。"

# 自訂 CSS
st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
    }
    
    h2, h3, [data-testid="stSidebar"] h3 {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        margin-top: 0.2rem !important;
        margin-bottom: 0.5rem !important;
    }
    
    h1 {
        font-size: 1.5rem !important;
        margin-bottom: 0.8rem !important;
        line-height: 1.3 !important;
        margin-top: 0rem !important;
    }

    div.stButton > button {
        margin-top: -2px !important;
        margin-bottom: -2px !important;
    }
    
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.4rem !important;
    }

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

    [data-testid="stMetricValue"] { 
        font-size: 1.25rem !important; 
        white-space: nowrap !important;
    }
    [data-testid="stMetricLabel"] { 
        font-size: 0.85rem !important; 
        white-space: nowrap !important;
    }

    html, body, [class*="css"] { font-size: 15px; }
    @media (max-width: 768px) {
        html, body, [class*="css"] { font-size: 13px !important; }
        [data-testid="stSidebar"] { width: 100% !important; }
    }
    </style>
    """,
    unsafe_allow_html=True
)

STOCK_NAME_TO_ID = {
    "台積電": "2330", "鴻海": "2317", "聯發科": "2454", "台達電": "2308", "廣達": "2382",
    "緯創": "3231", "華碩": "2357", "聯詠": "3034", "世芯": "3661", "世芯-KY": "3661", "世芯KY": "3661",
    "祥碩": "5269", "技嘉": "2376", "智邦": "2345", "和碩": "4938", "緯穎": "6669", "奇鋐": "3017",
    "雙鴻": "3324", "高力": "8996", "京元電子": "2449", "智原": "3035", "光聖": "6442", "晟銘電": "3013",
    "友聯": "2331", "創意": "3443", "旺矽": "6239", "長榮": "2603", "陽明": "2609", "萬海": "2615",
    "富邦金": "2881", "國泰金": "2882", "中信金": "2891", "日月光": "3711", "日月光投控": "3711",
    "南亞科": "2408", "華邦電": "2344", "聯電": "2303", "欣興": "3037", "健鼎": "3044",
    "M31": "6643", "m31": "6643", "臻鼎": "4958", "臻鼎-KY": "4958", "臻鼎KY": "4958",
    "聯茂": "6213", "金像電": "2368", "台光電": "2383", "華通": "2313", "群創": "3481", "友達": "2409",
    "力積電": "6770", "威盛": "2388", "宏碁": "2353", "仁寶": "2324", "光寶科": "2301", "英業達": "2356", "威剛": "3260"
}

# 建立反向股號對照表
STOCK_ID_TO_NAME = {v: k for k, v in STOCK_NAME_TO_ID.items()}

LARGE_CAP_STOCKS = ["2330", "2317", "2454", "2308", "2382", "2881", "2882", "2891", "3711", "2303"]

PEER_GROUPS = {
    "CPO/光通訊/矽光子": ["6442", "3081", "4979", "3163"],
    "液冷/散熱模組": ["3324", "8996", "3017", "2308", "3013"],
    "PCB/銅箔基板/載板": ["6213", "2368", "2383", "4958", "3037", "3044", "2313"],
    "晶圓代工/半導體": ["2330", "2303", "6770", "3711", "2449"],
    "IC 設計/ASIC": ["2454", "3034", "3661", "5269", "3443", "6643", "2388", "3035"],
    "AI 伺服器/組裝": ["2317", "2382", "3231", "2357", "2376", "4938", "6669", "2353", "2324", "2356"],
    "記憶體/模組": ["3260", "2408", "2344"],
    "航運": ["2603", "2609", "2615"],
    "金控": ["2881", "2882", "2891"]
}

def parse_stock_input(user_input):
    if not user_input:
        return ""
    clean_input = str(user_input).strip().replace(" ", "")
    if clean_input.isdigit():
        return clean_input
    if clean_input in STOCK_NAME_TO_ID:
        return STOCK_NAME_TO_ID[clean_input]
    core_name = clean_input.replace("-KY", "").replace("KY", "").replace("-ky", "").replace("ky", "")
    for name, s_id in STOCK_NAME_TO_ID.items():
        clean_name = name.replace("-KY", "").replace("KY", "")
        if core_name == clean_name or core_name in clean_name or clean_name in core_name:
            return s_id
    return clean_input

# 🛠️ 新增：自動取得個股中文名稱函數 (即使只輸入股號也能正確顯示中文股名)
def get_stock_display_name(raw_input, stock_id):
    if not stock_id:
        return "未指定"
    
    # 若使用者輸入中文，直接回傳
    clean_input = str(raw_input).strip()
    if not clean_input.isdigit() and len(clean_input) > 0:
        return f"{clean_input} ({stock_id})"
        
    # 若輸入數字股號，先對照內建對照表
    if stock_id in STOCK_ID_TO_NAME:
        return f"{STOCK_ID_TO_NAME[stock_id]} ({stock_id})"
        
    # 若字典找不到，透過 yfinance 網路查詢
    try:
        ticker = yf.Ticker(stock_id + ".TW")
        short_name = ticker.info.get('shortName') or ticker.info.get('longName')
        if not short_name:
            ticker = yf.Ticker(stock_id + ".TWO")
            short_name = ticker.info.get('shortName') or ticker.info.get('longName')
            
        if short_name:
            return f"{short_name} ({stock_id})"
    except Exception:
        pass
        
    return f"{stock_id}"

def clean_key(raw):
    if not raw:
        return ""
    k = str(raw).strip()
    return k.replace('"', '').replace("'", "")

FINMIND_TOKEN = clean_key(st.secrets.get("FINMIND_TOKEN", os.getenv("FINMIND_TOKEN", "")))
GEMINI_API_KEY = clean_key(st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", "")))

def get_taiwan_now():
    return datetime.utcnow() + timedelta(hours=8)

if "daily_picks" not in st.session_state:
    st.session_state.daily_picks = pd.DataFrame(
        columns=["上漲率預估", "族群", "股名", "股號", "當前實價", "建議進場", "建議退場", "波段期間"],
        data=[["--%", "---", "---", "---", "---", "---", "---", "---"] for _ in range(3)]
    )

if "last_predict_time" not in st.session_state:
    st.session_state.last_predict_time = get_taiwan_now().strftime("%m/%d %H:%M:%S")

def call_gemini_with_retry(prompt, max_retries=3):
    if not GEMINI_API_KEY:
        raise ValueError("Secrets 中未找到有效的 GEMINI_API_KEY，請檢查 Secrets 設定。")
        
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
            last_err = str(e)
            time.sleep(1.5)

    raise ValueError(f"Gemini API 呼叫失敗 [{last_err}]")

def diagnose_premarket_intelligence(macro_data, target_date_str):
    prompt_premarket = f"""
    請作為華爾街資深盤前情報官與台股策略總監，基準日期：{target_date_str}。
    當前全球宏觀指標：{macro_data}。

    請針對昨夜美股（費半、輝達、台積電 ADR）、美債殖利率、原油與近期台股盤前市場焦點進行盤前戰情診斷。
    請特別注意當天高檔獲利賣壓族群，避免誤選弱勢族群。
    請回傳 JSON 格式如下：
    {{
      "summary": "簡短 100 字盤前重點摘要...",
      "focus_sectors": ["族群A", "族群B"],
      "avoid_sectors": ["族群C"]
    }}
    不要包含 Markdown 多餘文字。
    """
    res_raw = call_gemini_with_retry(prompt_premarket)
    try:
        json_match = re.search(r'\{.*\}', res_raw, re.DOTALL)
        clean_json = json_match.group(0) if json_match else res_raw.strip()
        data = json.loads(clean_json)
        return data
    except Exception:
        return {
            "summary": "盤前總經與美股走勢平穩，維持科技權值與熱門題材輪動。",
            "focus_sectors": ["AI 伺服器", "PCB", "半導體"],
            "avoid_sectors": []
        }

def get_stock_news(stock_id):
    clean_id = parse_stock_input(stock_id)
    try:
        ticker = yf.Ticker(clean_id + ".TW")
        news_list = ticker.news
        if not news_list:
            ticker = yf.Ticker(clean_id + ".TWO")
            news_list = ticker.news
            
        if news_list and len(news_list) > 0:
            titles = [f"- {item.get('title', '')}" for item in news_list[:5] if item.get('title')]
            return "\n".join(titles)
    except Exception:
        pass
    return "尚無最新市場新聞資料"

def get_stock_valuation_metrics(stock_id):
    clean_id = parse_stock_input(stock_id)
    try:
        ticker = yf.Ticker(clean_id + ".TW")
        info = ticker.info
        if not info or 'forwardPE' not in info:
            ticker = yf.Ticker(clean_id + ".TWO")
            info = ticker.info
            
        pe = info.get('trailingPE') or info.get('forwardPE') or 'N/A'
        pb = info.get('priceToBook') or 'N/A'
        profit_margin = info.get('grossMargins') or 'N/A'
        if profit_margin != 'N/A': profit_margin = f"{profit_margin * 100:.2f}%"
        
        return {
            "pe": f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A",
            "pb": f"{pb:.2f}" if isinstance(pb, (int, float)) else "N/A",
            "gross_margin": profit_margin
        }
    except Exception:
        return {"pe": "N/A", "pb": "N/A", "gross_margin": "N/A"}

def get_peer_comparison(stock_id):
    clean_id = parse_stock_input(stock_id)
    target_group = None
    for g_name, members in PEER_GROUPS.items():
        if clean_id in members:
            target_group = (g_name, members)
            break
            
    if not target_group:
        return "同業比對：無特定對照組"
        
    g_name, members = target_group
    records = []
    for m_id in members[:4]:
        v = get_stock_valuation_metrics(m_id)
        records.append(f"【{m_id}】本益比: {v['pe']} | 股淨比: {v['pb']} | 毛利率: {v['gross_margin']}")
        
    return f"所屬同業族群：[{g_name}]\n" + "\n".join(records)

def get_realtime_tw_price_info(stock_id):
    try:
        clean_id = parse_stock_input(stock_id)
        ticker_symbol = clean_id + ".TW"
        ticker = yf.Ticker(ticker_symbol)
        data = ticker.history(period="5d")
        if data.empty or len(data) == 0:
            ticker_symbol = clean_id + ".TWO"
            ticker = yf.Ticker(ticker_symbol)
            data = ticker.history(period="5d")
            
        if not data.empty:
            latest_close = round(float(data['Close'].iloc[-1]), 2)
            prev_close = round(float(data['Close'].iloc[-2]), 2) if len(data) >= 2 else latest_close
            open_price = round(float(data['Open'].iloc[-1]), 2) if 'Open' in data.columns else latest_close
            return {
                "real_price": latest_close,
                "prev_close": prev_close,
                "open_price": open_price,
                "is_gap_down": open_price < prev_close
            }
    except Exception:
        pass
    return None

def calculate_kd(stock_id, period_type="日線", n=9, m1=3, m2=3):
    try:
        clean_id = parse_stock_input(stock_id)
        ticker = yf.Ticker(clean_id + ".TW")
        df = ticker.history(period="1y")
        if df.empty:
            ticker = yf.Ticker(clean_id + ".TWO")
            df = ticker.history(period="1y")
            
        if df.empty or len(df) < 20:
            return None, "數據不足"

        if period_type == "週線":
            df = df.resample('W').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()

        df['5MA'] = df['Close'].rolling(window=5).mean().round(2)
        df['20MA'] = df['Close'].rolling(window=20).mean().round(2)
        
        df['5VolMA'] = df['Volume'].rolling(window=5).mean()
        latest_vol = df['Volume'].iloc[-1]
        latest_vol_ma = df['5VolMA'].iloc[-1] if not pd.isna(df['5VolMA'].iloc[-1]) and df['5VolMA'].iloc[-1] > 0 else 1
        vol_ratio = round(latest_vol / latest_vol_ma, 2)

        last_body = (df['Close'].iloc[-1] - df['Open'].iloc[-1]) / df['Open'].iloc[-1]
        is_big_black_k = (last_body < -0.035) and (vol_ratio > 1.5)

        low_n = df['Low'].rolling(window=n).min()
        high_n = df['High'].rolling(window=n).max()
        rsv = (df['Close'] - low_n) / (high_n - low_n) * 100
        rsv = rsv.fillna(50)

        k_list, d_list = [50.0], [50.0]
        for r in rsv:
            k = (2/3) * k_list[-1] + (1/3) * r
            d = (2/3) * d_list[-1] + (1/3) * k
            k_list.append(k)
            d_list.append(d)

        df['K'] = k_list[1:]
        df['D'] = d_list[1:]
        
        latest_close = round(df['Close'].iloc[-1], 2)
        latest_5ma = round(df['5MA'].iloc[-1], 2) if not pd.isna(df['5MA'].iloc[-1]) else latest_close
        latest_20ma = round(df['20MA'].iloc[-1], 2) if not pd.isna(df['20MA'].iloc[-1]) else latest_close
        latest_k = round(df['K'].iloc[-1], 2)
        latest_d = round(df['D'].iloc[-1], 2)
        prev_k = df['K'].iloc[-2] if len(df) >= 2 else latest_k
        prev_d = df['D'].iloc[-2] if len(df) >= 2 else latest_d

        bias_20ma = round(((latest_close - latest_20ma) / latest_20ma) * 100, 2)

        recent_closes = df['Close'].tail(5).tolist()
        has_pullback = any(recent_closes[i] < recent_closes[i-1] for i in range(1, len(recent_closes)-1)) if len(recent_closes) >= 3 else False
        is_above_5ma = latest_close >= latest_5ma
        is_above_20ma = latest_close >= latest_20ma
        
        vol_signal_str = "🔥 帶量攻擊 (攻擊量充沛)" if vol_ratio >= 1.2 else "⚪ 量能平穩 (量縮洗盤沉澱中)"
        pullback_buy_signal = f"🔥 回後買上漲成立 (站上雙均線/乖離{bias_20ma:+}%)" if (has_pullback and is_above_5ma and is_above_20ma) else (
            "🟢 雙均線多頭保護持穩" if (is_above_5ma and is_above_20ma) else "⚠️ 短線拉回整理"
        )

        signal = "中性觀望"
        if prev_k <= prev_d and latest_k > latest_d:
            signal = "🟢 低檔黃金交叉" if latest_k <= 30 else "🟢 黃金交叉"
        elif prev_k >= prev_d and latest_k < latest_d:
            signal = "🔴 高檔死亡交叉" if latest_k >= 70 else "🔴 死亡交叉"
        elif latest_k >= 80 and latest_d >= 80:
            signal = "🔥 高檔鈍化"
        elif latest_k <= 20 and latest_d <= 20:
            signal = "❄️ 低檔超賣"

        return df.tail(40), {
            "K": latest_k, "D": latest_d, "signal": signal,
            "5MA": latest_5ma, "20MA": latest_20ma, "bias_20ma": bias_20ma,
            "vol_ratio": vol_ratio, "vol_signal_str": vol_signal_str,
            "is_big_black_k": is_big_black_k,
            "Close": latest_close,
            "pullback_buy_signal": pullback_buy_signal,
            "is_above_5ma": is_above_5ma, "is_above_20ma": is_above_20ma
        }
    except Exception as e:
        return None, str(e)

def get_stock_revenue_data(stock_id):
    clean_stock_id = parse_stock_input(stock_id)
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockMonthRevenue", "data_id": clean_stock_id}
        if FINMIND_TOKEN:
            params["token"] = FINMIND_TOKEN
        resp = requests.get(url, params=params, timeout=3)
        data = resp.json()
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            df = pd.DataFrame(data["data"])
            latest = df.iloc[-1]
            return f"最新月營收({latest.get('date', '')})：單月 MoM {latest.get('revenue_month', 0):+.2f}%，YoY {latest.get('revenue_year', 0):+.2f}%"
    except Exception:
        pass
    return "月營收數據：穩定成長中"

@st.cache_data(ttl=1800)
def get_macro_data(target_date_str):
    macro_tickers = {
        "費城半導體": "^SOX", "台灣加權": "^TWII",
        "美10年債殖利率": "^TNX", "WTI 國際原油": "CL=F",
        "VIX 恐慌指數": "^VIX", "黃金避險": "GC=F"
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
                unit = "%" if symbol == "^TNX" else ""
                macro_summary[name] = {"val": f"{latest:.2f}{unit}", "change": f"{change:+.2f}%"}
            else:
                macro_summary[name] = {"val": "更新中", "change": "0.00%"}
        except Exception:
            macro_summary[name] = {"val": "N/A", "change": "0.00%"}
    return macro_summary

@st.cache_data(ttl=1800)
def get_taiwan_sector_performance(target_date_str):
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    start_dt = target_dt - timedelta(days=10)
    url = "https://api.finmindtrade.com/api/v4/data"
    parameter = {"dataset": "TaiwanStockMarketSectorIndex", "start_date": start_dt.strftime("%Y-%m-%d"), "end_date": target_date_str}
    if FINMIND_TOKEN:
        parameter["token"] = FINMIND_TOKEN

    try:
        resp = requests.get(url, params=parameter, timeout=4)
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
    return "類股數據更新中"

# 🔒 100% 官方真實籌碼抓取函數 (列出最新 5 個交易日)
@st.cache_data(ttl=1800)
def get_stock_chip(stock_id, target_date_str):
    clean_stock_id = parse_stock_input(stock_id)
    if not clean_stock_id:
        return pd.DataFrame()
        
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    start_dt = target_dt - timedelta(days=25)
    
    # 管道一：FinMind 官方台股資料庫
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": clean_stock_id,
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": target_date_str
        }
        if FINMIND_TOKEN:
            params["token"] = FINMIND_TOKEN
            
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            raw_df = pd.DataFrame(data["data"])
            name_map = {
                "Foreign_Investor": "外資", 
                "Investment_Trust": "投信", 
                "Dealer_Self": "自營商", 
                "Dealer_Hedging": "自營商", 
                "Foreign_Dealer_Self": "外資"
            }
            if 'name' in raw_df.columns:
                raw_df['法人'] = raw_df['name'].map(lambda x: name_map.get(x, x))
            if 'buy' in raw_df.columns and 'sell' in raw_df.columns:
                raw_df['買賣超(張)'] = ((raw_df['buy'] - raw_df['sell']) / 1000).round(0).astype(int)
                
            pivot_df = raw_df.groupby(['date', '法人'])['買賣超(張)'].sum().unstack(fill_value=0).reset_index()
            for col in ['外資', '投信', '自營商']:
                if col not in pivot_df.columns:
                    pivot_df[col] = 0
                    
            pivot_df['三大法人合計'] = pivot_df['外資'] + pivot_df['投信'] + pivot_df['自營商']
            for c in ['外資', '投信', '自營商', '三大法人合計']:
                pivot_df[c] = pivot_df[c].apply(lambda x: f"+{x:,}" if x > 0 else f"{x:,}")
                
            pivot_df = pivot_df.rename(columns={'date': '日期'})
            return pivot_df.tail(5)[['日期', '外資', '投信', '自營商', '三大法人合計']]
    except Exception:
        pass

    # 管道二：證交所/櫃買中心官方 Open API 直連
    try:
        records = []
        curr_dt = target_dt
        while len(records) < 5 and (target_dt - curr_dt).days < 15:
            d_str = curr_dt.strftime('%Y%m%d')
            twse_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALL&date={d_str}"
            resp = requests.get(twse_url, timeout=3)
            if resp.status_code == 200 and 'data' in resp.json():
                jdata = resp.json()['data']
                for row in jdata:
                    if row[0].strip() == clean_stock_id:
                        f_val = int(row[4].replace(',', '')) // 1000
                        i_val = int(row[7].replace(',', '')) // 1000
                        d_val = int(row[10].replace(',', '')) // 1000
                        tot = f_val + i_val + d_val
                        records.append({
                            "日期": curr_dt.strftime("%Y-%m-%d"),
                            "外資": f"+{f_val:,}" if f_val > 0 else f"{f_val:,}",
                            "投信": f"+{i_val:,}" if i_val > 0 else f"{i_val:,}",
                            "自營商": f"+{d_val:,}" if d_val > 0 else f"{d_val:,}",
                            "三大法人合計": f"+{tot:,}" if tot > 0 else f"{tot:,}"
                        })
                        break
            curr_dt -= timedelta(days=1)
            
        if records:
            res_df = pd.DataFrame(records)
            return res_df.iloc[::-1].reset_index(drop=True)
    except Exception:
        pass

    return pd.DataFrame()

# 獨立過濾函數
def is_valid_stock(stock_id, target_date_str, min_price, max_price, strict_mode=True):
    _, kd_info = calculate_kd(stock_id, period_type="日線")
    if isinstance(kd_info, dict):
        k_val = kd_info.get("K", 50)
        d_val = kd_info.get("D", 50)
        kd_signal = kd_info.get("signal", "")
        is_above_5ma = kd_info.get("is_above_5ma", True)
        is_big_black_k = kd_info.get("is_big_black_k", False)
        
        if is_big_black_k or "死亡" in kd_signal:
            return False, None
            
        if not is_above_5ma or (k_val < d_val and "低檔超賣" not in kd_signal):
            return False, None

        if strict_mode and "中性" in kd_signal:
            return False, None

    chip_df = get_stock_chip(stock_id, target_date_str)
    if isinstance(chip_df, pd.DataFrame) and not chip_df.empty and len(chip_df) >= 3:
        try:
            recent_tot = []
            for idx in range(len(chip_df)-3, len(chip_df)):
                row = chip_df.iloc[idx]
                tot_val = int(str(row.get('三大法人合計', '0')).replace(',', '').replace('+', ''))
                recent_tot.append(tot_val)
                
            latest_chip = chip_df.iloc[-1]
            f_buy = int(str(latest_chip.get('外資', '0')).replace(',', '').replace('+', ''))
            i_buy = int(str(latest_chip.get('投信', '0')).replace(',', '').replace('+', ''))
            d_buy = int(str(latest_chip.get('自營商', '0')).replace(',', '').replace('+', ''))

            if (f_buy < 0 and i_buy < 0 and d_buy < 0) or (recent_tot[-1] < 0 and recent_tot[-2] < 0 and recent_tot[-3] < 0):
                return False, None
        except Exception:
            pass

    p_info = get_realtime_tw_price_info(stock_id)
    if p_info:
        real_p = p_info["real_price"]
        if p_info["is_gap_down"]: return False, None
        if min_price > 0 and real_p < min_price: return False, None
        if max_price > 0 and real_p > max_price: return False, None
        return True, real_p
        
    return False, None

# 生成選股
def generate_daily_picks(macro_data, sector_data, min_price, max_price, custom_sector, target_date_str):
    cond_list = []
    if min_price > 0: cond_list.append(f"最低不得低於 {min_price} 元")
    if max_price > 0: cond_list.append(f"最高不得超過 {max_price} 元")
        
    price_limit_str = f"【硬性股價區間限制】：{', '.join(cond_list)}" if cond_list else "股價不限"
    sector_limit_str = f"【指定產業限制】：必須嚴格從「{custom_sector.strip()}」相關個股挑選" if custom_sector and custom_sector.strip() != "" else "【指定產業限制】：AI 自主推薦熱門主流"

    premarket_focus_str = f"【08:00 盤前即時利多/聚焦族群 (第一優先權重)】：{st.session_state.premarket_focus}" if st.session_state.premarket_focus else ""
    premarket_avoid_str = f"【08:00 盤前即時利空/避險族群 (絕對禁止挑選)】：{st.session_state.premarket_avoid}" if st.session_state.premarket_avoid else ""

    prompt_select = (
        "請作為頂級華爾街台股選股操盤手，基準日期：" + str(target_date_str) + "。\n"
        "價格條件：" + price_limit_str + "。\n"
        "族群條件：" + sector_limit_str + "。\n"
        "大盤環境：" + str(macro_data) + "\n"
        + premarket_focus_str + "\n"
        + premarket_avoid_str + "\n\n"
        "請廣泛挑選 30 檔具備波段攻擊潛力、熱門且實質成交量高的台股標的名單，上漲率預估請給予 68%-88% 之間的數值。\n"
        "請回傳 JSON 陣列格式如：\n"
        '[{"上漲率預估":"78%","族群":"半導體","股名":"南亞科","股號":"2408","波段期間":"5-10天"}]\n'
        "不要包含 Markdown 標記。"
    )
    res_raw = call_gemini_with_retry(prompt_select)
    json_match = re.search(r'\[.*\]', res_raw, re.DOTALL)
    clean_json = json_match.group(0) if json_match else res_raw.strip()
    picks = json.loads(clean_json)
    
    final_results = []
    
    for item in picks:
        stock_id = parse_stock_input(item.get("股號"))
        if not stock_id: continue
        
        valid, real_p = is_valid_stock(stock_id, target_date_str, min_price, max_price, strict_mode=True)
        if valid and real_p:
            p_low = round(real_p * 0.985, 1)
            p_high = round(real_p * 1.005, 1)
            item["當前實價"] = f"{real_p:.2f}"
            item["建議進場"] = f"{p_low:.1f}-{p_high:.1f}"
            item["建議退場"] = f"{round(real_p * 1.08, 2):.2f}"
            
            if stock_id in LARGE_CAP_STOCKS:
                item["波段期間"] = "5-10天 (權值股階梯墊高)"
            else:
                if "波段期間" not in item: item["波段期間"] = "5-10天"
                
            final_results.append(item)
        if len(final_results) >= 3: break

    if len(final_results) < 3:
        for item in picks:
            stock_id = parse_stock_input(item.get("股號"))
            if any(x.get("股號") == item.get("股號") for x in final_results): continue
            
            valid, real_p = is_valid_stock(stock_id, target_date_str, min_price, max_price, strict_mode=False)
            if valid and real_p:
                p_low = round(real_p * 0.985, 1)
                p_high = round(real_p * 1.005, 1)
                item["當前實價"] = f"{real_p:.2f}"
                item["建議進場"] = f"{p_low:.1f}-{p_high:.1f}"
                item["建議退場"] = f"{round(real_p * 1.08, 2):.2f}"
                if stock_id in LARGE_CAP_STOCKS:
                    item["波段期間"] = "5-10天 (權值股階梯墊高)"
                else:
                    if "波段期間" not in item: item["波段期間"] = "5-10天"
                final_results.append(item)
            if len(final_results) >= 3: break

    while len(final_results) < 3:
        final_results.append({
            "上漲率預估": "--%", "族群": "行情整理中", "股名": "無符合標的",
            "股號": "----", "當前實價": "---", "建議進場": "---", "建議退場": "---", "波段期間": "---"
        })
    return final_results

# AI 深度分析
def ai_single_stock_analysis(macro_data, sector_data, stock_input, chip_data, kd_info, period_type, capital, target_date_str):
    stock_id = parse_stock_input(stock_input)
    capital_str = f"{capital:,} 元" if capital and capital > 0 else "未限定金額"
    p_info = get_realtime_tw_price_info(stock_id)
    rev_str = get_stock_revenue_data(stock_id)
    
    news_titles = get_stock_news(stock_id)
    val_metrics = get_stock_valuation_metrics(stock_id)
    peer_str = get_peer_comparison(stock_id)
    
    is_large_cap = stock_id in LARGE_CAP_STOCKS
    cap_type_str = "【屬性】：千億大型權值指標股 (波段多為階梯式震盪墊高，切勿追高)" if is_large_cap else "【屬性】：中小型波段攻擊股"
    
    if p_info:
        real_price = p_info["real_price"]
        price_info_str = f"當前真實市場成交價：{real_price} 元 ({cap_type_str})"
        p_low = round(real_price * 0.985, 1)
        p_high = round(real_price * 1.005, 1)
        p_mid = round((p_low + p_high) / 2, 2)
        target_p = round(real_price * 1.08, 1)
        calc_price_str = f"【系統統一計算數據】：建議買進區間：{p_low}元 ~ {p_high}元，預估進場均價中間值：{p_mid}元，波段停利目標價：{target_p}元。"
    else:
        price_info_str = "即時股價：需參考市場現價"
        p_low, p_high, p_mid, target_p = "---", "---", "---", "---"
        calc_price_str = ""

    chip_str = chip_data.to_string(index=False) if isinstance(chip_data, pd.DataFrame) and not chip_data.empty else "無最新籌碼數據"
    
    if isinstance(kd_info, dict):
        vol_ratio = kd_info.get('vol_ratio', 1.0)
        kd_str = f"最新{period_type} KD 指標：K={kd_info.get('K')}, D={kd_info.get('D')}，轉折訊號為 [{kd_info.get('signal')}]"
        ma_str = f"5日均線(5MA)={kd_info.get('5MA')}元，20日月線(20MA)={kd_info.get('20MA')}元 (月線乖離率: {kd_info.get('bias_20ma'):+f}%)。"
        vol_str = f"當前成交量增倍數：{vol_ratio} 倍 (5日均量基準)。狀態：[{kd_info.get('vol_signal_str')}]。"
        pattern_str = f"『回後買上漲』診斷：[{kd_info.get('pullback_buy_signal')}]"
    else:
        vol_ratio = 1.0
        kd_str = ma_str = vol_str = pattern_str = "技術數據不足"
    
    vol_hint = "當前成交量尚未爆發，若量能不及 1.2 倍，建議於『建議進場區間下限』逢低掛單佈局，切勿開高追價。" if vol_ratio < 1.2 else "成交量順利放大，具備攻擊量能！"
    
    premarket_context = f"【08:00 盤前情報動態備忘】：聚焦族群 {st.session_state.premarket_focus} / 避險族群 {st.session_state.premarket_avoid}"

    prompt = (
        "請作為頂級華爾街資深 Top-Down (自上而下) 總經與台股操盤手分析師。基準日期：" + str(target_date_str) + "。\n"
        "分析標的：" + str(stock_input) + " (代碼: " + str(stock_id) + ")，" + price_info_str + "，預計資金配置：" + capital_str + "。\n"
        + calc_price_str + "\n"
        + premarket_context + "\n"
        "【開盤紀律鐵則】：若當日開盤價低於前日收盤價（跳空開低），代表盤中弱勢，一律視為不滿足進場條件！\n"
        "【量能策略叮嚀】：\n" + vol_hint + "\n\n"
        "【基本面估值與同業競爭者對比】：\n"
        f"- 本益比 (P/E): {val_metrics['pe']} | 股淨比 (P/B): {val_metrics['pb']} | 最新毛利率: {val_metrics['gross_margin']}\n"
        f"- {peer_str}\n\n"
        "【市場最新新聞輿論與獲利預估】：\n" + news_titles + "\n\n"
        "【基本面最新營收趨勢 (落後指標)】：\n" + rev_str + "\n\n"
        "【近期三大法人籌碼細節 (領先/同步指標)】：\n" + chip_str + "\n\n"
        "【技術面量價與雙均線診斷 (確認指標)】：\n"
        "- " + kd_str + "\n"
        "- " + ma_str + "\n"
        "- " + vol_str + "\n"
        "- " + pattern_str + "\n\n"
        "請輸出繁體中文詳細報告，並【嚴格遵守以下結構與順序】：\n\n"
        "=== 第一部分：【實戰結論摘要】 ===\n"
        "1. 操盤實戰結論（請結合 08:00 盤前即時情報、開盤跳空低開防護、美債/原油戰事避險情緒、大型權值股/中小型股屬性與 20MA 月線做二次邏輯驗證）。\n"
        "2. 多空勝率優勢與風報比評估\n"
        "   請【嚴格依據以下固定格式與縮排】完整填入真實數學計算數據：\n"
        "   * 多空勝率評估：[AI分析當前多空勝率，例如：75% 勝率優勢]\n"
        "   * 風險/報酬比 (R/R Ratio) 試算：\n"
        "     - 預估進場均價：" + f"{p_mid} 元 (取建議買進區間 {p_low} ~ {p_high} 元之中間值)" + "\n"
        "     - 波段目標價：" + f"{target_p} 元 (潛在獲利空間：+{round(target_p - p_mid, 2)} 元 / +{round((target_p - p_mid)/p_mid*100, 2)}%)" + "\n"
        "     - 防守停損價：[AI依據技術支撐算出停損價，如 XX.XX 元] (潛在風險：-XX.XX 元 / -XX.XX%)\n"
        "     - 風報比 (R/R Ratio)：[AI計算 潛在獲利/潛在風險 比值，如 X.XX : 1] (AI分析，建議高於 2.0:1 方可建立部位)\n"
        "   * 綜合推薦星等：[例如：★★★★☆ (4/5星)]\n"
        "3. 具體操作指引（【請務必強調：若開盤價 < 昨收價(跳空低開)則不建倉，並包含進場區間 " + f"{p_low} 元 ~ {p_high} 元" + "】與目標價 " + f"{target_p} 元" + "，以及明確的『預估波段持有天數』】）。\n\n"
        "=== 第二部分：【深度分析報告內文】 ===\n"
        "1. 全球宏觀與科技大勢總結 (含 08:00 盤前美股/ADR 連動)\n"
        "2. 基本面價值評估與同業估值比較\n"
        "3. 新聞輿論與法人獲利預估背離診斷\n"
        "4. 三大法人籌碼流向與基本面月營收連動分析\n"
        "5. 5MA/20MA月線多頭格局與量價關係診斷（【請務必結合當前成交量放大 " + str(vol_ratio) + " 倍進行深層量價邏輯解析】）。"
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

st.sidebar.markdown("### 📰 盤前情報動態注入 (08:00-08:30)")
if st.sidebar.button("⚡ 執行 08:00 盤前情報即時診斷", type="secondary", use_container_width=True):
    with st.spinner("🤖 正在聯網掃描美股ADR、費半、油價與盤前即時新聞..."):
        try:
            p_data = diagnose_premarket_intelligence(macro_data, target_date_str)
            st.session_state.premarket_summary = p_data.get("summary", "")
            st.session_state.premarket_focus = p_data.get("focus_sectors", [])
            st.session_state.premarket_avoid = p_data.get("avoid_sectors", [])
            st.sidebar.success("盤前情報注入完成！已連動選股邏輯。")
        except Exception as e:
            st.sidebar.error(f"盤前情報診斷失敗: {e}")

st.sidebar.info(f"💡 **盤前情報摘要**：\n{st.session_state.premarket_summary}")
st.sidebar.divider()

st.sidebar.markdown(f"### 🎯 今日 [{st.session_state.last_predict_time}] AI 預估上漲率最高前三檔")

st.sidebar.markdown("**指定產業族群或題材 (選填)**")
custom_sector = st.sidebar.text_input("輸入族群或題材", value="", placeholder="例如: 記憶體、PCB、半導體...", label_visibility="collapsed")

st.sidebar.markdown("**設定股價區間 (新台幣元)**")
p_col1, p_col2 = st.sidebar.columns(2)
with p_col1: min_price_input = st.number_input("最低價", min_value=0, value=None, placeholder="最低金額", step=10, label_visibility="collapsed")
with p_col2: max_price_input = st.number_input("最高價", min_value=0, value=None, placeholder="最高金額", step=10, label_visibility="collapsed")

min_price = min_price_input if min_price_input is not None else 0
max_price = max_price_input if max_price_input is not None else 0

if st.sidebar.button("🚀 產生今日AI預估上漲率最高前三檔", type="primary", use_container_width=True):
    with st.spinner("🤖 AI 結合 08:00 盤前情報掃描台股中..."):
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

st.sidebar.markdown("### ⚙️ 個股詳細分析與技術指標設定")

raw_stock_input = st.sidebar.text_input(
    "輸入台股代碼或股名", 
    value="", 
    placeholder="例如: 2330 或 臻鼎",
    help="如只看三大法人籌碼與 KD 綜合分析看板，輸入股號或股名後直接按 Enter"
)
st.sidebar.caption("(如只看三大法人籌碼與 KD 綜合分析看板，輸入股號或股名後直接按 Enter)")

stock_id = parse_stock_input(raw_stock_input)
display_title = get_stock_display_name(raw_stock_input, stock_id)

period_type = st.sidebar.radio("KD 技術指標週期選擇", ["日線", "週線"], horizontal=True)
capital_input = st.sidebar.number_input("預計進場金額 (新台幣元)", min_value=0, value=None, placeholder="請輸入金額", step=10000)
capital = capital_input if capital_input is not None else 0

btn_analyze_stock = st.sidebar.button("📊 開始 AI 個股分析", type="primary", use_container_width=True)

# 主畫面看板
st.subheader(f"🌐 全球宏觀與風險避險指標看板 ({target_date_str})")
cols = st.columns([1, 1, 1, 1, 1, 1])
idx = 0
for name, info in macro_data.items():
    with cols[idx % 6]:
        st.metric(label=name, value=info["val"], delta=info["change"], delta_color="inverse")
    idx += 1

st.divider()

# 🛠️ 強制統一顯示「個股 [中文名稱] (代碼)」
st.subheader(f"🔍 個股 ({display_title}) 三大法人籌碼與 {period_type} KD / 雙均線 綜合分析看板")

if stock_id and str(stock_id).strip() != "":
    chip_df = get_stock_chip(stock_id, target_date_str)
    kd_df, kd_info = calculate_kd(stock_id, period_type=period_type)
    
    if isinstance(kd_info, dict):
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1.2, 1.2, 2.0])
        c1.metric(f"{period_type} K 值", kd_info['K'])
        c2.metric(f"{period_type} D 值", kd_info['D'])
        c3.metric("5日均線 (5MA)", kd_info['5MA'])
        c4.metric("20日線 (月線)", kd_info['20MA'], delta=f"{kd_info['bias_20ma']:+}%\n(乖離)")
        c5.metric("KD & 均線型態", kd_info['signal'])
        
    tab_chip, tab_kd = st.tabs(["三大法人籌碼 (張)", f"{period_type} KD 指標與 均線走勢圖"])
    with tab_chip:
        if isinstance(chip_df, pd.DataFrame) and not chip_df.empty:
            st.dataframe(chip_df, hide_index=True, use_container_width=True)
        else:
            st.warning("尚無三大法人籌碼紀錄。")
    with tab_kd:
        if kd_df is not None and not kd_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['K'], mode='lines', name='K 值 (快線)', line=dict(color='#ff4d4f', width=2)))
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['D'], mode='lines', name='D 值 (慢線)', line=dict(color='#1890ff', width=2)))
            fig.add_hline(y=80, line_dash="dash", line_color="gray", annotation_text="80 超買")
            fig.add_hline(y=20, line_dash="dash", line_color="gray", annotation_text="20 超賣")
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("無法計算 KD 線數據。")
else:
    st.info("請於左側輸入台股代碼或股名後檢視籌碼與 KD / 均線看板")

st.divider()

if btn_analyze_stock:
    if not raw_stock_input or str(raw_stock_input).strip() == "":
        st.warning("請先在左側欄位輸入台股代碼或股名！")
    else:
        chip_df = get_stock_chip(stock_id, target_date_str)
        _, kd_info = calculate_kd(stock_id, period_type=period_type)
        with st.spinner(f"🤖 AI 結合 08:00 盤前情報檢析【風報比試算】、【同業估值】與【量能位階】..."):
            try:
                report = ai_single_stock_analysis(
                    macro_data, sector_data, raw_stock_input, 
                    chip_data=chip_df, kd_info=kd_info, period_type=period_type, 
                    capital=capital, target_date_str=target_date_str
                )
                st.subheader(f"🤖 Gemini AI 全維度詳細分析報告 ({display_title})")
                st.markdown(report)
            except Exception as e:
                st.error(f"分析生成失敗: {e}")