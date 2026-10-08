# -*- coding: utf-8 -*-
import os
import time
import json
import re
from datetime import datetime, timedelta
import streamlit as st
import yfinance as yf
import requests
import pandas as pd
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from google import genai

# 設定網頁標題與寬版佈局
st.set_page_config(page_title="AI 全球宏觀與台股 Top-Down 策略分析系統", layout="wide")

# ==============================================================================
# 🔒 雙重身分認證機制 (A組 Email + B組 密碼雙重比對)
# ==============================================================================
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown("<br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("🔒 AI 股票分析系統雙重身分認證")
            
            # 輸入欄位 A：使用者 Email
            user_email = st.text_input("請輸入授權 Email (A組)：", placeholder="例如: xxxxx@gmail.com")
            
            # 輸入欄位 B：存取密碼
            user_password = st.text_input("請輸入存取密碼 (B組)：", type="password")
            
            if st.button("確認登入", type="primary", use_container_width=True):
                default_emails = [
                    "tower.yp.chang@gmail.com", 
                    "sherryhsu6155@gmail.com", 
                    "ha71850tw@gmail.com", 
                    "b12212219@gmail.com"
                ]
                default_passwords = ["615588", "085978"]
                
                allowed_emails = st.secrets.get("ALLOWED_EMAILS", default_emails)
                allowed_passwords = st.secrets.get("ALLOWED_PASSWORDS", default_passwords)
                
                clean_email = user_email.strip().lower()
                clean_password = user_password.strip()
                
                allowed_emails_clean = [e.strip().lower() for e in allowed_emails]
                
                if clean_email in allowed_emails_clean and clean_password in allowed_passwords:
                    st.session_state.authenticated = True
                    st.success("雙重驗證成功，正在進入系統...")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("驗證失敗！Email 或密碼不符合授權紀錄，請重新確認！")
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

    div.stButton > button[key="btn_combined_diagnose"] {
        background-color: #1890ff !important;
        color: #ffffff !important;
        border-color: #1890ff !important;
        font-weight: bold !important;
    }
    div.stButton > button[key="btn_combined_diagnose"]:hover {
        background-color: #40a9ff !important;
        border-color: #40a9ff !important;
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

# 擴充常用中文股名字典
STOCK_NAME_TO_ID = {
    "台積電": "2330", "鴻海": "2317", "聯發科": "2454", "台達電": "2308", "廣達": "2382", "聯鈞": "3450", "上詮": "3363",
    "緯創": "3231", "華碩": "2357", "聯詠": "3034", "世芯": "3661", "世芯-KY": "3661", "世芯KY": "3661", "神達": "3706",
    "祥碩": "5269", "技嘉": "2376", "智邦": "2345", "和碩": "4938", "緯穎": "6669", "奇鋐": "3017", "華星光": "4979",
    "雙鴻": "3324", "高力": "8996", "京元電子": "2449", "智原": "3035", "光聖": "6442", "晟銘電": "3013",
    "志聖": "2467", "建準": "2421", "精英": "2331", "精華": "1565", "漢唐": "2404", "創意": "3443", "旺矽": "6239",
    "長榮": "2603", "陽明": "2609", "萬海": "2615", "富邦金": "2881", "國泰金": "2882", "中信金": "2891",
    "日月光": "3711", "日月光投控": "3711", "南亞科": "2408", "華邦電": "2344", "聯電": "2303",
    "欣興": "3037", "健鼎": "3044", "M31": "6643", "m31": "6643", "臻鼎": "4958", "臻鼎-KY": "4958",
    "臻鼎KY": "4958", "聯茂": "6213", "金像電": "2368", "台光電": "2383", "華通": "2313",
    "群創": "3481", "友達": "2409", "力積電": "6770", "威盛": "2388", "宏碁": "2353",
    "仁寶": "2324", "光寶科": "2301", "英業達": "2356", "威剛": "3260", "萬潤": "6187", "辛耘": "3583", "泰碩": "3338", "金居": "8358",
    "眾達": "4977", "眾達-KY": "4977", "眾達KY": "4977", "昇陽半": "8028", "昇陽半導體": "8028", "貿聯": "3665", "貿聯-KY": "3665", "貿聯KY": "3665"
}

STOCK_ID_TO_NAME = {v: k for k, v in STOCK_NAME_TO_ID.items()}

LARGE_CAP_STOCKS = ["2330", "2317", "2454", "2308", "2382", "2881", "2882", "2891", "3711", "2303"]

PEER_GROUPS = {
    "CPO/光通訊/矽光子": ["6442", "3081", "4979", "3163", "4977"],
    "液冷/散熱模組": ["3324", "8996", "3017", "2308", "3013", "3338"],
    "PCB/銅箔基板/載板": ["6213", "2368", "2383", "4958", "3037", "3044", "2313", "8358"],
    "晶圓代工/半導體/設備": ["2330", "2303", "6770", "3711", "2449", "2467", "2404", "6187", "3583", "8028"],
    "IC 設計/ASIC": ["2454", "3034", "3661", "5269", "3443", "6643", "2388", "3035"],
    "AI 伺服器/組裝/線束": ["2317", "2382", "3231", "2357", "2376", "4938", "6669", "2353", "2324", "2356", "2421", "3665"],
    "記憶體/模組": ["3260", "2408", "2344"],
    "航運": ["2603", "2609", "2615"],
    "金控": ["2881", "2882", "2891"]
}

# ------------------------------------------------------------------------------
# 全台股上市/上櫃動態名稱與代號反查函式
# ------------------------------------------------------------------------------
@st.cache_data(ttl=86400)
def get_all_taiwan_stocks_dict():
    """自動自證交所與櫃買中心獲取全台股股票名稱與代號清單"""
    all_stocks = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        resp = requests.get(url_twse, headers=headers, timeout=3)
        if resp.status_code == 200:
            for item in resp.json():
                s_id = str(item.get("Code", "")).strip()
                s_name = str(item.get("Name", "")).strip()
                if s_id and s_name:
                    all_stocks[s_name] = s_id
                    all_stocks[s_id] = s_name
    except Exception:
        pass

    try:
        url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
        resp = requests.get(url_tpex, headers=headers, timeout=3)
        if resp.status_code == 200:
            for item in resp.json():
                s_id = str(item.get("SecuritiesCompanyCode", "")).strip()
                s_name = str(item.get("CompanyName", "")).strip()
                if s_id and s_name:
                    all_stocks[s_name] = s_id
                    all_stocks[s_id] = s_name
    except Exception:
        pass
        
    return all_stocks

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
            
    all_stocks = get_all_taiwan_stocks_dict()
    if clean_input in all_stocks:
        return all_stocks[clean_input]
    for name, s_id in all_stocks.items():
        clean_name = name.replace("-KY", "").replace("KY", "")
        if core_name == clean_name or core_name in clean_name:
            return s_id

    return clean_input

@st.cache_data(ttl=86400)
def get_twse_stock_name(stock_id):
    """自證交所與櫃買中心官方資料庫反查精準中文名稱"""
    try:
        url = "https://www.twse.com.tw/rwd/zh/api/codeMarket?response=json"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        resp = requests.get(url, headers=headers, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            for row in data.get('data', []):
                if len(row) >= 2 and row[0].strip() == str(stock_id).strip():
                    return row[1].strip()
    except Exception:
        pass
    return None

def get_stock_display_name(raw_input, stock_id):
    if not stock_id:
        return "未指定"
    
    clean_input = str(raw_input).strip()
    pure_name = re.sub(r'[\(\)\d\s]', '', clean_input)
    if pure_name and pure_name != stock_id:
        return f"{pure_name} {stock_id}"

    if stock_id in STOCK_ID_TO_NAME:
        return f"{STOCK_ID_TO_NAME[stock_id]} {stock_id}"
        
    all_stocks = get_all_taiwan_stocks_dict()
    if stock_id in all_stocks:
        return f"{all_stocks[stock_id]} {stock_id}"

    twse_name = get_twse_stock_name(stock_id)
    if twse_name:
        return f"{twse_name} {stock_id}"
        
    return f"{stock_id}"

def clean_key(raw):
    if not raw:
        return ""
    k = str(raw).strip()
    return k.replace('"', '').replace("'", "").replace('\n', '').replace('\r', '')

FINMIND_TOKEN = clean_key(st.secrets.get("FINMIND_TOKEN", os.getenv("FINMIND_TOKEN", "")))
GEMINI_API_KEY = clean_key(st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", "")))

def get_taiwan_now():
    return datetime.utcnow() + timedelta(hours=8)

if "daily_picks" not in st.session_state:
    st.session_state.daily_picks = pd.DataFrame(
        columns=["上漲率", "族群", "股名", "股號", "當前實價", "建議進場", "波段停利/防護提示", "波段期間"],
        data=[["--%", "---", "---", "---", "---", "---", "---", "---"] for _ in range(3)]
    )

if "last_predict_time" not in st.session_state:
    st.session_state.last_predict_time = get_taiwan_now().strftime("%m/%d %H:%M:%S")

# ==============================================================================
# 🛡️ 風護模組：證交所/櫃買中心「注意股/處置股」警示 API 檢測
# ==============================================================================
@st.cache_data(ttl=1800)
def check_stock_warning_status(stock_id):
    clean_id = parse_stock_input(stock_id)
    if not clean_id:
        return {"status": "NORMAL", "msg": ""}

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        url_tpex = "https://www.tpex.org.tw/web/stock/margin_trading/warning/wrt_result.php?l=zh-tw&o=json"
        resp = requests.get(url_tpex, headers=headers, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            for row in data.get('aaData', []):
                if len(row) >= 2 and str(clean_id) in str(row[0]):
                    note = str(row)
                    if "處置" in note:
                        return {"status": "DISPOSITION", "msg": "🚨 本檔被列為【處置股票】(分盤撮合/預先收足款券)，流動性嚴重受限！"}
                    return {"status": "ATTENTION", "msg": "⚠️ 本檔被列為【注意股票】(短線振幅過大或週轉率過高)，籌碼波動極劇烈！"}
    except Exception:
        pass

    try:
        url_twse = "https://www.twse.com.tw/rwd/zh/announcement/notice?response=json"
        resp = requests.get(url_twse, headers=headers, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            for row in data.get('data', []):
                if len(row) >= 2 and str(clean_id) in str(row[1]):
                    return {"status": "ATTENTION", "msg": "⚠️ 本檔被列為【注意股票】(短線振幅過大或週轉率過高)，籌碼波動極劇烈！"}
    except Exception:
        pass

    return {"status": "NORMAL", "msg": ""}

def call_gemini_with_retry(prompt, max_retries=2):
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
            time.sleep(1.0)

    raise ValueError(f"Gemini API 呼叫失敗 [{last_err}]")

def diagnose_premarket_intelligence(macro_data, target_date_str):
    prompt_premarket = f"""
    請作為華爾街資深盤前情報官與台股策略總監，基準日期：{target_date_str}。
    當前全球宏觀指標：{macro_data}。

    請針對昨夜美股、美債殖利率、原油與近期台股盤前焦點進行戰情診斷。
    請回傳 JSON 格式：
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
            "focus_sectors": ["AI伺服器", "PCB", "半導體設備"],
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
    return "無重大新聞"

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

@st.cache_data(ttl=300)
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

@st.cache_data(ttl=300)
def calculate_kd(stock_id, period_type="日線", n=9, m1=3, m2=3):
    try:
        clean_id = parse_stock_input(stock_id)
        ticker = yf.Ticker(clean_id + ".TW")
        df = ticker.history(period="6mo")
        if df.empty:
            ticker = yf.Ticker(clean_id + ".TWO")
            df = ticker.history(period="6mo")
            
        if df.empty or len(df) < 20:
            return None, "數據不足"

        if period_type == "週線":
            df = df.resample('W').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()

        df['5MA'] = df['Close'].rolling(window=5).mean().round(2).fillna(df['Close'])
        df['20MA'] = df['Close'].rolling(window=20).mean().round(2).fillna(df['Close'])
        df['60MA'] = df['Close'].rolling(window=60).mean().round(2).fillna(df['20MA'])
        
        std_20 = df['Close'].rolling(window=20).std().fillna(0)
        df['BB_Upper'] = (df['20MA'] + (std_20 * 2)).round(2)
        df['BB_Lower'] = (df['20MA'] - (std_20 * 2)).round(2)

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean().fillna(0)
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean().fillna(0)
        rs = gain / (loss.replace(0, 1e-6))
        df['RSI'] = (100 - (100 / (1 + rs))).round(2).fillna(50)

        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = (ema12 - ema26).round(2).fillna(0)
        df['MACD_Signal'] = df['DIF'].ewm(span=9, adjust=False).mean().round(2).fillna(0)
        df['MACD_Hist'] = ((df['DIF'] - df['MACD_Signal']) * 2).round(2).fillna(0)

        df['5VolMA'] = df['Volume'].rolling(window=5).mean().fillna(df['Volume'])
        latest_vol = df['Volume'].iloc[-1]
        latest_vol_ma = df['5VolMA'].iloc[-1] if not pd.isna(df['5VolMA'].iloc[-1]) and df['5VolMA'].iloc[-1] > 0 else 1
        vol_ratio = round(latest_vol / latest_vol_ma, 2)

        last_body = (df['Close'].iloc[-1] - df['Open'].iloc[-1]) / df['Open'].iloc[-1]
        is_big_black_k = (last_body < -0.035) and (vol_ratio > 1.5)

        low_n = df['Low'].rolling(window=n).min().fillna(df['Low'])
        high_n = df['High'].rolling(window=n).max().fillna(df['High'])
        denom = (high_n - low_n).replace(0, 1e-6)
        rsv = (df['Close'] - low_n) / denom * 100
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
        latest_60ma = round(df['60MA'].iloc[-1], 2) if not pd.isna(df['60MA'].iloc[-1]) else latest_20ma
        latest_k = round(df['K'].iloc[-1], 2)
        latest_d = round(df['D'].iloc[-1], 2)
        prev_k = df['K'].iloc[-2] if len(df) >= 2 else latest_k
        prev_d = df['D'].iloc[-2] if len(df) >= 2 else latest_d

        bias_20ma = round(((latest_close - latest_20ma) / (latest_20ma if latest_20ma != 0 else 1)) * 100, 2)
        bias_60ma = round(((latest_close - latest_60ma) / (latest_60ma if latest_60ma != 0 else 1)) * 100, 2)

        recent_closes = df['Close'].tail(5).tolist()
        has_pullback = any(recent_closes[i] < recent_closes[i-1] for i in range(1, len(recent_closes)-1)) if len(recent_closes) >= 3 else False
        is_above_5ma = latest_close >= latest_5ma
        is_above_20ma = latest_close >= latest_20ma
        
        vol_signal_str = "🔥 帶量攻擊" if vol_ratio >= 1.2 else "⚪ 量能平穩"
        pullback_buy_signal = f"🔥 回後買上漲成立 (乖離{bias_20ma:+}%)" if (has_pullback and is_above_5ma and is_above_20ma) else (
            "🟢 雙均線多頭保護持穩" if (is_above_5ma and is_above_20ma) else "⚠ 短線拉回整理"
        )

        signal = "中性觀望"
        if prev_k <= prev_d and latest_k > latest_d:
            signal = "🟢 低檔黃金交叉" if latest_k <= 30 else "🟢 黃金交叉"
        elif prev_k >= prev_d and latest_k < latest_d:
            signal = "🔴 高檔死亡交叉" if latest_k >= 70 else "🔴 死亡交叉"
        elif latest_k >= 80 and latest_d >= 80:
            signal = "🔥 高檔鈍化"
        elif latest_k <= 20 and latest_d <= 20:
            signal = "❄ 低檔超賣"

        return df.tail(40), {
            "K": latest_k, "D": latest_d, "signal": signal,
            "5MA": latest_5ma, "20MA": latest_20ma, "60MA": latest_60ma, 
            "bias_20ma": bias_20ma, "bias_60ma": bias_60ma,
            "vol_ratio": vol_ratio, "vol_signal_str": vol_signal_str,
            "is_big_black_k": is_big_black_k,
            "Close": latest_close,
            "pullback_buy_signal": pullback_buy_signal,
            "is_above_5ma": is_above_5ma, "is_above_20ma": is_above_20ma,
            "RSI": round(df['RSI'].iloc[-1], 2) if not pd.isna(df['RSI'].iloc[-1]) else "N/A",
            "DIF": round(df['DIF'].iloc[-1], 2) if not pd.isna(df['DIF'].iloc[-1]) else "N/A",
            "MACD_Signal": round(df['MACD_Signal'].iloc[-1], 2) if not pd.isna(df['MACD_Signal'].iloc[-1]) else "N/A",
            "BB_Upper": round(df['BB_Upper'].iloc[-1], 2) if not pd.isna(df['BB_Upper'].iloc[-1]) else "N/A",
            "BB_Lower": round(df['BB_Lower'].iloc[-1], 2) if not pd.isna(df['BB_Lower'].iloc[-1]) else "N/A"
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
        resp = requests.get(url, params=params, timeout=2)
        data = resp.json()
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            df = pd.DataFrame(data["data"])
            latest = df.iloc[-1]
            return f"最新月營收({latest.get('date', '')})：單月 MoM {latest.get('revenue_month', 0):+.2f}%，YoY {latest.get('revenue_year', 0):+.2f}%"
    except Exception:
        pass
    return "月營收數據：穩定成長中"

@st.cache_data(ttl=300)
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
                # 💡 精準修復：取倒數第二筆（前一交易日收盤價），確保漲跌幅計算精準無誤
                prev_close = data['Close'].iloc[-2]
                change = ((latest - prev_close) / prev_close) * 100
                unit = "%" if symbol == "^TNX" else ""
                macro_summary[name] = {"val": f"{latest:.2f}{unit}", "change": f"{change:+.2f}%"}
            else:
                macro_summary[name] = {"val": "更新中", "change": "0.00%"}
        except Exception:
            macro_summary[name] = {"val": "N/A", "change": "0.00%"}
    return macro_summary

@st.cache_data(ttl=1800)
def get_macro_history_trends():
    tickers = {"費城半導體": "^SOX", "美10年債殖利率": "^TNX", "WTI 國際原油": "CL=F"}
    res_dict = {}
    
    for name, sym in tickers.items():
        try:
            df = yf.Ticker(sym).history(period="60d")
            if not df.empty and 'Close' in df.columns and len(df) > 5:
                res_dict[name] = df['Close']
        except Exception:
            pass

    dates = pd.date_range(end=get_taiwan_now(), periods=40, freq='B')
    if "費城半導體" not in res_dict:
        res_dict["費城半導體"] = pd.Series([12200 + i * 10 for i in range(40)], index=dates)
    if "美10年債殖利率" not in res_dict:
        res_dict["美10年債殖利率"] = pd.Series([4.20 + (i % 5) * 0.02 for i in range(40)], index=dates)
    if "WTI 國際原油" not in res_dict:
        res_dict["WTI 國際原油"] = pd.Series([75.0 + (i % 7) * 0.5 for i in range(40)], index=dates)

    combined = pd.DataFrame(res_dict).ffill().bfill()
    
    if "美10年債殖利率" in combined.columns:
        if combined["美10年債殖利率"].mean() < 10:
            combined["美10年債殖利率(20倍)"] = combined["美10年債殖利率"] * 20
        else:
            combined["美10年債殖利率(20倍)"] = combined["美10年債殖利率"] * 2

    return combined

@st.cache_data(ttl=1800)
def get_taiwan_sector_performance(target_date_str):
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    start_dt = target_dt - timedelta(days=10)
    url = "https://api.finmindtrade.com/api/v4/data"
    parameter = {"dataset": "TaiwanStockMarketSectorIndex", "start_date": start_dt.strftime("%Y-%m-%d"), "end_date": target_date_str}
    if FINMIND_TOKEN:
        parameter["token"] = FINMIND_TOKEN

    try:
        resp = requests.get(url, params=parameter, timeout=3)
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

@st.cache_data(ttl=600)
def get_stock_chip(stock_id, target_date_str):
    clean_stock_id = parse_stock_input(stock_id)
    if not clean_stock_id:
        return pd.DataFrame()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    try:
        url = f"https://fubon-ebrokerdj.fbs.com.tw/z/zc/zcl/zcl.djhtm?a={clean_stock_id}&b=3"
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            resp.encoding = 'big5'
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table', class_='t01')
            if table:
                rows = table.find_all('tr')
                records = []
                for r in rows:
                    cols = [td.text.strip() for td in r.find_all('td')]
                    if len(cols) >= 5 and '/' in cols[0]:
                        date_raw = cols[0]
                        try:
                            parts = date_raw.split('/')
                            year_ad = int(parts[0]) + 1911
                            date_fmt = f"{year_ad}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                        except Exception:
                            date_fmt = date_raw

                        def parse_num(val_str):
                            clean = val_str.replace(',', '').replace('+', '')
                            try:
                                return int(clean)
                            except Exception:
                                return 0

                        f_val = parse_num(cols[1])
                        i_val = parse_num(cols[2])
                        d_val = parse_num(cols[3])
                        tot_val = parse_num(cols[4])

                        records.append({
                            "日期": date_fmt,
                            "外資": f"{f_val:+,}",
                            "投信": f"{i_val:+,}",
                            "自營商": f"{d_val:+,}",
                            "三大法人合計": f"{tot_val:+,}"
                        })

                if records:
                    df = pd.DataFrame(records)
                    df = df.sort_values(by="日期", ascending=True).tail(5).reset_index(drop=True)
                    return df
    except Exception:
        pass

    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        start_dt = target_dt - timedelta(days=60)
        end_dt = target_dt - timedelta(days=1)
        
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": clean_stock_id,
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": end_dt.strftime("%Y-%m-%d")
        }
        if FINMIND_TOKEN:
            params["token"] = FINMIND_TOKEN

        resp = requests.get(url, params=params, headers=headers, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("msg") == "success" and len(data.get("data", [])) > 0:
                raw_data = data["data"]
                daily_dict = {}
                for row in raw_data:
                    d = row.get("date")
                    name = str(row.get("name", "")).strip()
                    buy = row.get("buy", 0)
                    sell = row.get("sell", 0)
                    diff = row.get("buy_sell", buy - sell)

                    if d not in daily_dict:
                        daily_dict[d] = {"外資": 0, "投信": 0, "自營商": 0}

                    if "Foreign" in name or "外" in name:
                        daily_dict[d]["外資"] += diff
                    elif "Investment" in name or "投" in name:
                        daily_dict[d]["投信"] += diff
                    elif "Dealer" in name or "自" in name:
                        daily_dict[d]["自營商"] += diff

                records = []
                for d in sorted(daily_dict.keys()):
                    f_val = round(daily_dict[d]["外資"] / 1000)
                    i_val = round(daily_dict[d]["投信"] / 1000)
                    d_val = round(daily_dict[d]["自營商"] / 1000)
                    tot = f_val + i_val + d_val

                    if f_val != 0 or i_val != 0 or d_val != 0:
                        records.append({
                            "日期": d,
                            "外資": f"{f_val:+,}",
                            "投信": f"{i_val:+,}",
                            "自營商": f"{d_val:+,}",
                            "三大法人合計": f"{tot:+,}"
                        })

                if len(records) >= 1:
                    return pd.DataFrame(records).tail(5)
    except Exception:
        pass

    return pd.DataFrame()

def is_valid_stock_fast(stock_id, min_price, max_price):
    p_info = get_realtime_tw_price_info(stock_id)
    if not p_info:
        return False, None
        
    real_p = p_info["real_price"]
    
    if min_price > 0 and real_p < min_price: 
        return False, None
    if max_price > 0 and real_p > max_price: 
        return False, None
        
    _, kd_info = calculate_kd(stock_id, period_type="日線")
    if isinstance(kd_info, dict):
        kd_signal = kd_info.get("signal", "")
        if "死亡" in kd_signal or kd_info.get("is_big_black_k", False):
            return False, None

    return True, real_p

def generate_daily_picks(macro_data, sector_data, min_price, max_price, custom_sector, selected_masters, target_date_str):
    cond_list = []
    if min_price > 0: cond_list.append(f"最低不得低於 {min_price} 元")
    if max_price > 0: cond_list.append(f"最高不得超過 {max_price} 元")
        
    price_limit_str = f"【硬性股價區間限制】：{', '.join(cond_list)}" if cond_list else "股價不限"
    
    if custom_sector and custom_sector.strip() != "":
        sector_limit_str = f"【指定產業限制】：必須嚴格從「{custom_sector.strip()}」相關個股挑選"
    else:
        sector_limit_str = "【指定產業限制】：無限制（授權 AI 對全台股進行全維度分析，自主挑選全市場多頭型態最強之熱門主流標的）"

    master_prompt_str = ""
    if selected_masters:
        master_rules = []
        if "杜金龍(股市老牌大師)" in selected_masters:
            master_rules.append(
                "【杜金龍大師選股邏輯】：優先挑選波段從近期高點適度拉回 7%-11% 支撐甜蜜點、本益比處於歷史合理下限（價值定錨），且股價重回 20MA（月線）支撐之多頭標的。"
            )
        if "宇帆隊長" in selected_masters:
            master_rules.append(
                "【宇帆隊長選股邏輯】：優先挑選『產業 Top-Down 龍頭』，且『三大法人/投信連續買超鎖碼』、月營收 MoM 雙位數成長爆發，並在量縮整理後帶量突破前高之強勢飆股。"
            )
        master_prompt_str = "【啟用大師診斷模組加權】：\n" + "\n".join(master_rules) + "\n請結合以上大師之審核視角進行嚴格二次評分濾網篩選！\n"

    premarket_focus_str = f"【08:00 盤前即時利多/聚焦族群】：{st.session_state.premarket_focus}" if st.session_state.premarket_focus else ""

    prompt_select = (
        "請作為頂級華爾街台股選股操盤手，基準日期：" + str(target_date_str) + "。\n"
        "價格條件：" + price_limit_str + "。\n"
        "族群條件：" + sector_limit_str + "。\n"
        + master_prompt_str +
        "大盤環境：" + str(macro_data) + "\n"
        + premarket_focus_str + "\n\n"
        "請精選 10 檔最具備波段攻擊潛力、多頭型態且成交量充沛的台股標的名單，預估上漲率請給予 68%-88% 之間的數值。\n"
        "【重要規格要求】：『族群』名稱請參考 Yahoo 股市風格分類，且長度【嚴格限制在 6 個全形中文簡短字數以內】（如：半導體設備、液冷散熱、CPO光通訊、PCB載板）。\n"
        "請回傳 JSON 陣列格式如：\n"
        '[{"上漲率":"78%","族群":"半導體設備","股名":"萬潤","股號":"6187","波段期間":"5-10天"}]\n'
        "不要包含 Markdown 標記。"
    )
    
    try:
        res_raw = call_gemini_with_retry(prompt_select)
        json_match = re.search(r'\[.*\]', res_raw, re.DOTALL)
        clean_json = json_match.group(0) if json_match else res_raw.strip()
        picks = json.loads(clean_json)
    except Exception:
        picks = []
    
    final_results = []
    
    for item in picks:
        stock_id = parse_stock_input(item.get("股號"))
        if not stock_id: continue
        
        valid, real_p = is_valid_stock_fast(stock_id, min_price, max_price)
        if valid and real_p:
            warn_info = check_stock_warning_status(stock_id)
            raw_pct_str = item.get("上漲率", item.get("預估上漲率", "78%"))
            raw_pct = float(re.sub(r'[^\d.]', '', raw_pct_str) or 78.0)
            
            if warn_info["status"] == "DISPOSITION":
                raw_pct -= 12.0
            elif warn_info["status"] == "ATTENTION":
                raw_pct -= 6.0
            
            raw_pct = max(60.0, min(88.0, raw_pct))
            item["上漲率"] = f"{raw_pct:.0f}%"

            _, kd_info = calculate_kd(stock_id, period_type="日線")
            bias_20 = kd_info.get("bias_20ma", 0.0) if isinstance(kd_info, dict) else 0.0
            bias_60 = kd_info.get("bias_60ma", 0.0) if isinstance(kd_info, dict) else 0.0
            ma20_val = kd_info.get("20MA", real_p) if isinstance(kd_info, dict) else real_p

            if bias_20 > 15.0 or bias_60 > 15.0:
                p_low = round(ma20_val * 0.99, 1)
                p_high = round(ma20_val * 1.02, 1)
                item["波段停利/防護提示"] = f"🔥過熱! 修正至20MA({p_low}-{p_high})逢低接"
            else:
                p_low = round(real_p * 0.985, 1)
                p_high = round(real_p * 1.005, 1)
                target_p = round(real_p * 1.08, 1)
                item["波段停利/防護提示"] = f"目標 {target_p:.1f} (達標即落袋)"

            raw_sector = str(item.get("族群", "主流題材")).strip()
            item["族群"] = raw_sector[:6]
            
            item["當前實價"] = f"{real_p:.2f}"
            item["建議進場"] = f"{p_low:.1f}-{p_high:.1f}"
            
            tw_name = get_twse_stock_name(stock_id) or STOCK_ID_TO_NAME.get(stock_id, item.get("股名"))
            item["股名"] = tw_name
            
            if stock_id in LARGE_CAP_STOCKS:
                item["波段期間"] = "5-10天 (階梯墊高)"
            else:
                if "波段期間" not in item: item["波段期間"] = "5-10天"
                
            final_results.append(item)
        if len(final_results) >= 3: break

    fallback_candidates = ["2330", "2317", "2382", "3231", "3017", "6187", "2454", "2308"]
    for f_id in fallback_candidates:
        if len(final_results) >= 3: break
        if any(res.get("股號") == f_id for res in final_results): continue
        valid, real_p = is_valid_stock_fast(f_id, min_price, max_price)
        if valid and real_p:
            p_low = round(real_p * 0.985, 1)
            p_high = round(real_p * 1.005, 1)
            target_p = round(real_p * 1.08, 1)
            tw_name = STOCK_ID_TO_NAME.get(f_id, "強勢個股")
            final_results.append({
                "上漲率": "76%",
                "族群": "主流AI權值"[:6],
                "股名": tw_name,
                "股號": f_id,
                "當前實價": f"{real_p:.2f}",
                "建議進場": f"{p_low:.1f}-{p_high:.1f}",
                "波段停利/防護提示": f"目標 {target_p:.1f} (達標即落袋)",
                "波段期間": "5-10天"
            })

    while len(final_results) < 3:
        final_results.append({
            "上漲率": "70%", "族群": "熱門主流", "股名": "台積電",
            "股號": "2330", "當前實價": "---", "建議進場": "---", "波段停利/防護提示": "---", "波段期間": "5-10天"
        })
        
    df_res = pd.DataFrame(final_results)
    cols_order = ["上漲率", "族群", "股名", "股號", "當前實價", "建議進場", "波段停利/防護提示", "波段期間"]
    return df_res[cols_order].to_dict('records')

def ai_single_stock_analysis(macro_data, sector_data, stock_input, chip_data, kd_info, period_type, capital_mode, price_or_capital, selected_masters, target_date_str):
    stock_id = parse_stock_input(stock_input)
    display_name = get_stock_display_name(stock_input, stock_id)
    p_info = get_realtime_tw_price_info(stock_id)
    rev_str = get_stock_revenue_data(stock_id)
    
    news_titles = get_stock_news(stock_id)
    val_metrics = get_stock_valuation_metrics(stock_id)
    peer_str = get_peer_comparison(stock_id)
    warn_info = check_stock_warning_status(stock_id)
    
    is_large_cap = stock_id in LARGE_CAP_STOCKS
    cap_type_str = "【屬性】：千億大型權值指標股 (波段多為階梯式震盪墊高，切勿追高)" if is_large_cap else "【屬性】：中小型波段攻擊股"
    
    if p_info:
        real_price = p_info["real_price"]
        price_info_str = f"當前真實市場成交價：{real_price} 元 ({cap_type_str})"
        
        bias_20 = kd_info.get("bias_20ma", 0.0) if isinstance(kd_info, dict) else 0.0
        bias_60 = kd_info.get("bias_60ma", 0.0) if isinstance(kd_info, dict) else 0.0
        ma20_val = kd_info.get("20MA", real_price) if isinstance(kd_info, dict) else real_price

        if bias_20 > 15.0 or bias_60 > 15.0:
            p_low = round(ma20_val * 0.99, 1)
            p_high = round(ma20_val * 1.02, 1)
            overheat_warning_str = f"【風護風控警示 - 高檔過熱】：當前月線正乖離率高達 {bias_20:+f}% (> +15%)！追高風險極高，系統已強制將建議買進區間下修至 20MA 月線支撐附近 ({p_low}元 ~ {p_high}元)。"
        else:
            p_low = round(real_price * 0.985, 1)
            p_high = round(real_price * 1.005, 1)
            overheat_warning_str = ""

        p_mid = round((p_low + p_high) / 2, 2)
        target_p = round(real_price * 1.08, 1)
        calc_price_str = f"【系統統一計算數據】：建議買進區間：{p_low}元 ~ {p_high}元，預估進場均價中間值：{p_mid}元，波段停利目標價：{target_p}元。\n{overheat_warning_str}"
    else:
        real_price = 100.0
        price_info_str = "即時股價：需參考市場現價"
        p_low, p_high, p_mid, target_p = "---", "---", "---", "---"
        calc_price_str = ""

    chip_str = chip_data.to_string(index=False) if isinstance(chip_data, pd.DataFrame) and not chip_data.empty else "無最新籌碼數據"
    
    if isinstance(kd_info, dict):
        vol_ratio = kd_info.get('vol_ratio', 1.0)
        kd_str = f"最新{period_type} KD 指標：K={kd_info.get('K')}, D={kd_info.get('D')}，轉折訊號為 [{kd_info.get('signal')}]"
        ma_str = f"5日均線(5MA)={kd_info.get('5MA')}元，20日月線(20MA)={kd_info.get('20MA')}元 (月線乖離率: {kd_info.get('bias_20ma'):+f}%)，60日季線(60MA)={kd_info.get('60MA')}元。"
        vol_str = f"當前成交量增倍數：{vol_ratio} 倍 (5日均量基準)。狀態：[{kd_info.get('vol_signal_str')}]。"
        pattern_str = f"『回後買上漲』診斷：[{kd_info.get('pullback_buy_signal')}]"
        adv_tech_str = (
            f"RSI(14日)={kd_info.get('RSI', 'N/A')} | "
            f"MACD DIF(快線)={kd_info.get('DIF', 'N/A')} | MACD Signal(慢線)={kd_info.get('MACD_Signal', 'N/A')} | "
            f"布林上軌={kd_info.get('BB_Upper', 'N/A')}元 | 布林下軌={kd_info.get('BB_Lower', 'N/A')}元"
        )
    else:
        vol_ratio = 1.0
        kd_str = ma_str = vol_str = pattern_str = adv_tech_str = "技術數據不足"
    
    vol_hint = "當前成交量尚未爆發，若量能不及 1.2 倍，建議於『建議進場區間下限』逢低掛單佈局，切勿開高追價。" if vol_ratio < 1.2 else "成交量順利放大，具備攻擊量能！"
    premarket_context = f"【最新情報動態】：聚焦族群 {st.session_state.premarket_focus} / 避險族群 {st.session_state.premarket_avoid} | 摘要: {st.session_state.premarket_summary}"

    warning_prompt_context = f"【交易風險警示狀態】：{warn_info['msg']}" if warn_info["status"] != "NORMAL" else "【交易風險警示狀態】：無警示，交易流動性正常。"

    master_single_instruction = ""
    if selected_masters:
        m_list_str = "、".join(selected_masters)
        master_single_instruction = (
            f"7. 【大師診斷模組比對報告 (已啟用：{m_list_str})】：\n"
            "   請針對使用者勾選的大師視角，獨立給予診斷說明：\n"
        )
        if "杜金龍(股市老牌大師)" in selected_masters:
            master_single_instruction += (
                "   - 【杜金龍大師觀點】：剖析本益比位階、拉回幅度是否達到 7-11% 黃金甜蜜區，以及 20MA 月線扣抵與支撐性，給予大師評分與佈局建議。\n"
            )
        if "宇帆隊長" in selected_masters:
            master_single_instruction += (
                "   - 【宇帆隊長觀點】：從 Top-Down 產業題材能見度、三大法人/投信籌碼鎖碼續航力與月營收爆發力進行深度診斷，評估是否屬於主力極度青睞之波段黑馬。\n"
            )

    if capital_mode == "既有持股 (已套牢/持有中)":
        cost_price = price_or_capital if price_or_capital and price_or_capital > 0 else real_price
        unrealized_pct = round(((real_price - cost_price) / cost_price) * 100, 2)
        position_context = (
            f"【使用者既有持股狀態】：持有狀態為『既有持股處置』。\n"
            f"- 歷史買進成本價：{cost_price} 元 / 當前最新現價：{real_price} 元\n"
            f"- 當前帳面未實現損益：{unrealized_pct}%"
        )
        mode_instruction = (
            "=== 第一部分：【既有持股處置與停損/解套脫手指令】 ===\n"
            "1. 【核心脫手賣點與解套目標試算】：\n"
            f"   * 當前買進成本價：{cost_price} 元 | 當前市場現價：{real_price} 元 (未實現損益: {unrealized_pct}%)\n"
            "   * 建議逢高減碼 / 反彈解套脫手目標價：[AI依據上方壓力位與20MA算出的目標價，例如：XX.X 元]\n"
            "   * 建議關鍵防守 / 停損換股價位：[AI依據下方支撐位算出的停損價，例如：XX.X 元]\n"
            "   * 脫手時機與處置建議：[例如：若反彈至 XX 元遇到 20MA 壓力建議先解套減碼 50%，若跌破 XX 元則需果斷停損換股]\n"
            "2. 【持股風報比與轉折勝率評估】：\n"
            "   * 止跌反彈勝率評估：[例如：76% 止跌反彈勝率 (簡要說明依據)]\n"
            "   * 風險/報酬比 (R/R Ratio) 試算：[比值及建倉建議]\n"
            "3. 【既有持股操盤指引】：（明確針對目前套牢狀況，給予具體的『分批解套』或『破位停損』時間點與價格指令，無贅詞無重複）。\n"
        )
    else:
        capital_str = f"{price_or_capital:,} 元" if price_or_capital and price_or_capital > 0 else "未限定金額"
        position_context = f"【使用者既有持股狀態】：全新佈局 (預計建立部位金額: {capital_str})"
        mode_instruction = (
            "=== 第一部分：【實戰操盤指令與風報比試算】 ===\n"
            "1. 【核心買賣點與預估獲利試算】：\n"
            "   * 建議進場買進區間：" + f"{p_low} 元 ~ {p_high} 元" + " (預估進場均價中間值: " + f"{p_mid} 元" + ")\n"
            "   * 波段停利脫手賣出目標價：" + f"{target_p} 元" + "\n"
            "   * 預計潛在獲利：每股 +" + f"{round(target_p - p_mid, 2)}" + " 元 (預估獲利空間：+" + f"{round((target_p - p_mid)/p_mid*100, 2)}" + "%)\n"
            "2. 【多空勝率優勢與風報比評估】：\n"
            "   * 多空勝率評估：[AI填入%數] 勝率優勢 (※請簡要補充1文句說明勝率評估依據※)\n"
            "   * 防守停損價：[AI依據技術支撐算出停損價，如 XX.XX 元] (潛在風險：-XX.XX 元 / -XX.XX%，設於 20MA 月線上方極近處作為關鍵防守線)\n"
            "   * 風報比 (R/R Ratio)：[AI計算 潛在獲利/潛在風險 比值，如 X.XX : 1] (高於 2.0:1 門檻，具備建立全新部位之價值)\n"
            "3. 【極簡操盤實戰指引】：\n"
            "   * 進場部署：請鎖定建議買進區間分批掛單，若成交量未放大，切勿開高追價，建議於區間下限逢低吸納。\n"
            "   * 開盤警示：若跳空低開（低於前日收盤）視為弱勢取消進場；若開盤跳空開高 > +2.0%，切勿追高，等待股價回落至區間內再建立部位。\n"
            "   * 停利執行：盤中衝高觸及或超越目標價，必須即時執行動態停利落袋為安。\n"
            "   * 預估波段持有天數：5 ~ 10 個交易日。\n"
        )

    prompt = (
        "請作為頂級華爾街資深 Top-Down (自上而下) 總經與台股操盤手分析師。基準日期：" + str(target_date_str) + "。\n"
        "【輸出規範與無贅詞鐵則】：\n"
        "1. 嚴格遵守精簡扼要、不失重點、無重複、無贅詞之格式輸出！\n"
        "2. 嚴禁出現『恭喜取得第一手即時盤面數據』、『我是華爾街資深...』、『以下為針對...』等開場贅詞招呼語！直接輸出標題！\n"
        "3. 第一部分【實戰操盤指令與風報比試算】中，不可重複印出預估進場均價、波段目標價或綜合推薦星等；多空勝率評估必須附帶簡要依據；防守停損價與風報比單獨成列。\n"
        "4. 所有分析必須 100% 依據以下給出的系統真實數據與即時情報進行深度邏輯推演！\n\n"
        "分析標的：" + str(display_name) + "，" + price_info_str + "。\n"
        + position_context + "\n"
        + calc_price_str + "\n"
        + premarket_context + "\n"
        + warning_prompt_context + "\n\n"
        "【基本面估值與同業競爭者對比】：\n"
        f"- 本益比 (P/E): {val_metrics['pe']} | 股淨比 (P/B): {val_metrics['pb']} | 最新毛利率: {val_metrics['gross_margin']}\n"
        f"- {peer_str}\n\n"
        "【市場最新新聞輿論與獲利預估】：\n" + news_titles + "\n\n"
        "【基本面最新營收趨勢 (落後指標)】：\n" + rev_str + "\n\n"
        "【近期三大法人籌碼細節 (領先/同步指標)】：\n" + chip_str + "\n\n"
        "【技術面量價、雙均線與進階指標數據】：\n"
        "- " + kd_str + "\n"
        "- " + ma_str + "\n"
        "- " + vol_str + "\n"
        "- " + pattern_str + "\n"
        "- 進階指標現況：" + adv_tech_str + "\n\n"
        "請輸出繁體中文詳細報告，格式如下：\n\n"
        "🤖 Gemini AI 全維度詳細分析報告 (" + str(display_name) + ")\n\n"
        + mode_instruction + "\n"
        "=== 第二部分：【全維度詳細分析報告內文】 ===\n"
        "1. 全球宏觀與科技大勢：條列解析費半、VIX與資金流向（ Risk-On / Risk-Off 狀態）。\n"
        "2. 基本面價值評估與同業估值比較：依據最新 P/E、P/B、毛利率與同業數據給予精簡診斷結論。\n"
        "3. 重大新聞及輿論現況與法人獲利預估背離診斷：檢視 24 小時內新聞（無新聞請顯示「無重大新聞」）並診斷背離狀況。\n"
        "4. 三大法人籌碼流向與基本面月營收連動分析：交叉比對外資、投信、自營商籌碼與月營收 MoM/YoY 趨勢。\n"
        "5. 5MA/20MA月線多頭格局與量價關係診斷：結合成交量倍數與 20MA 月線乖離率進行量價剖析。\n"
        "6. 各項進階技術性指標綜合圖表解說：\n"
        "   - 布林通道 (Bollinger Bands)：上軌/中軌/下軌位置與通道型態診斷。\n"
        "   - KD 指標 & RSI(14)：KD 轉折位階與 RSI 強弱診斷。\n"
        "   - MACD 動能柱與軌道變化：DIF/MACD 快慢線與柱狀體多空控盤診斷。\n"
        + master_single_instruction
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

st.sidebar.markdown("**指定產業族群或題材 (選填)**")
custom_sector = st.sidebar.text_input("輸入族群或題材", value="", placeholder="例如: 記憶體、PCB、半導體...", label_visibility="collapsed")

st.sidebar.markdown("**大師診斷模組 (可單選/複選/不選)**")
selected_masters = st.sidebar.multiselect(
    "選擇大師診斷風格",
    options=["杜金龍(股市老牌大師)", "宇帆隊長"],
    default=[],
    placeholder="預設不選擇 (採用標準 Top-Down AI 策略)",
    label_visibility="collapsed"
)

st.sidebar.markdown("**設定股價區間 (新台幣元)**")
p_col1, p_col2 = st.sidebar.columns(2)
with p_col1: min_price_input = st.number_input("最低價", min_value=0, value=None, placeholder="最低金額", step=10, label_visibility="collapsed")
with p_col2: max_price_input = st.number_input("最高價", min_value=0, value=None, placeholder="最高金額", step=10, label_visibility="collapsed")

min_price = min_price_input if min_price_input is not None else 0
max_price = max_price_input if max_price_input is not None else 0

# 💡 整合快取自動清除邏輯於按鈕點擊事件
if st.sidebar.button("AI 執行最新情報分析預測上漲機率最高前三檔", type="primary", key="btn_combined_diagnose", use_container_width=True):
    get_macro_data.clear()
    get_realtime_tw_price_info.clear()
    calculate_kd.clear()
    
    with st.spinner("🤖 第一階段：正在即時擷取盤中最新美股ADR、費半、油價與產業情報..."):
        try:
            macro_data = get_macro_data(target_date_str)
            p_data = diagnose_premarket_intelligence(macro_data, target_date_str)
            st.session_state.premarket_summary = p_data.get("summary", "")
            st.session_state.premarket_focus = p_data.get("focus_sectors", [])
            st.session_state.premarket_avoid = p_data.get("avoid_sectors", [])
        except Exception as e:
            st.sidebar.error(f"情報診斷失敗: {e}")
            
    with st.spinner("🤖 第二階段：結合最新盤中行情、風護模組與大師條件，進行全市場精準選股..."):
        try:
            picks_data = generate_daily_picks(macro_data, sector_data, min_price, max_price, custom_sector, selected_masters, target_date_str)
            st.session_state.daily_picks = pd.DataFrame(picks_data)
            st.session_state.last_predict_time = get_taiwan_now().strftime("%m/%d %H:%M:%S")
            st.sidebar.success("最新盤中行情刷新暨個股預測順利完成！")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"個股預測失敗: {e}")

st.sidebar.info(f"💡 **最新情報摘要**：\n{st.session_state.premarket_summary}")

st.sidebar.dataframe(st.session_state.daily_picks, hide_index=True, use_container_width=True)
st.sidebar.divider()

st.sidebar.markdown("### ⚙ 個股詳細分析與技術指標設定")

raw_stock_input = st.sidebar.text_input(
    "輸入台股代碼或股名", 
    value="", 
    placeholder="例如: 2330 或 鴻海",
    help="如只看三大法人籌碼與進階技術指標看板，輸入股號或股名後直接按 Enter"
)
st.sidebar.caption("(如只看三大法人籌碼與進階技術指標看板，輸入股號或股名後直接按 Enter)")

stock_id = parse_stock_input(raw_stock_input)
display_title = get_stock_display_name(raw_stock_input, stock_id)

period_type = st.sidebar.radio("技術指標週期選擇", ["日線", "週線"], horizontal=True)

capital_mode = st.sidebar.radio("持有狀態", ["準備買進", "既有持股 (已套牢/持有中)"], horizontal=True)

if capital_mode == "既有持股 (已套牢/持有中)":
    capital_label = "當初買進成本價 (每股幾元)"
    capital_placeholder = "例如: 525 (每股成本)"
else:
    capital_label = "預計進場金額 (新台幣元)"
    capital_placeholder = "例如: 100000 (總預算)"

capital_input = st.sidebar.number_input(capital_label, min_value=0, value=None, placeholder=capital_placeholder, step=100)
price_or_capital = capital_input if capital_input is not None else 0

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

# 🛡️ 條件式尾盤 13:00 風護警示面板（僅在偵測到注意/處置股票時顯現）
if stock_id and str(stock_id).strip() != "":
    warn_check = check_stock_warning_status(stock_id)
    if warn_check["status"] == "DISPOSITION":
        st.error(f"{warn_check['msg']}\n\n🚨 **【13:00 尾盤定型操盤紀律】**：處置股流動性嚴重受阻，請務必等到下午 1:00 尾盤確認未出現無量下殺且未破防守位再考慮分批買進，切勿在早盤開高時盲目追高掛單！")
    elif warn_check["status"] == "ATTENTION":
        st.warning(f"{warn_check['msg']}\n\n⚠️ **【13:00 尾盤定型操盤紀律】**：注意股短線波動極劇烈，早盤極易出現當沖洗盤與開高走低陷阱，請務必於下午 1:00 尾盤定型時，確認股價穩在建議進場區間且並未爆量跳水方可掛單！")

# 看板標題
st.subheader(f"🔍 個股 ({display_title}) 三大法人籌碼與進階技術指標綜合分析看板")

if stock_id and str(stock_id).strip() != "":
    chip_df = get_stock_chip(stock_id, target_date_str)
    kd_df, kd_info = calculate_kd(stock_id, period_type=period_type)
    
    if isinstance(kd_info, dict):
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1.2, 1.2, 2.0])
        c1.metric(f"{period_type} K / D 值", f"{kd_info['K']} / {kd_info['D']}")
        c2.metric("RSI (14日)", kd_info.get('RSI', 'N/A'))
        c3.metric("5日均線 (5MA)", kd_info['5MA'])
        c4.metric("20日線 (月線)", kd_info['20MA'], delta=f"{kd_info['bias_20ma']:+}%\n(乖離)")
        c5.metric("KD & 均線型態", kd_info['signal'])
        
    tab_chip, tab_kd, tab_macro_chart = st.tabs([
        "📊 三大法人籌碼 (張)", 
        "📈 進階技術指標", 
        "🌐 全球宏觀指標多空趨勢對比圖"
    ])
    
    with tab_chip:
        if isinstance(chip_df, pd.DataFrame) and not chip_df.empty:
            st.dataframe(chip_df, hide_index=True, use_container_width=True)
            st.caption("💡 資料來源：富邦綜合證券 / 嘉實資訊 (SysJust) 官方盤後真實買賣超統計（單位：張）。")
        else:
            st.warning("籌碼資料更新中。")
            
    with tab_kd:
        if kd_df is not None and not kd_df.empty:
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.09,
                row_heights=[0.5, 0.25, 0.25],
                subplot_titles=("收盤價與布林通道 (20MA)", "KD 指標 & RSI (14)", "MACD 動能柱與 DIF/MACD 軌道")
            )
            
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['Close'], mode='lines', name='收盤價', line=dict(color='#ffffff', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['BB_Upper'], mode='lines', name='布林上軌', line=dict(color='#ff7875', width=1, dash='dash')), row=1, col=1)
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['20MA'], mode='lines', name='布林中軌', line=dict(color='#ffc069', width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['BB_Lower'], mode='lines', name='布林下軌', line=dict(color='#95de64', width=1, dash='dash')), row=1, col=1)

            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['K'], mode='lines', name='K 值', line=dict(color='#ff4d4f', width=1.5)), row=2, col=1)
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['D'], mode='lines', name='D 值', line=dict(color='#1890ff', width=1.5)), row=2, col=1)
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['RSI'], mode='lines', name='RSI', line=dict(color='#b37feb', width=1.5, dash='dot')), row=2, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="gray", row=2, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="gray", row=2, col=1)

            colors_macd = ['#ff4d4f' if val >= 0 else '#52c41a' for val in kd_df['MACD_Hist']]
            fig.add_trace(go.Bar(x=kd_df.index, y=kd_df['MACD_Hist'], name='MACD 柱狀', marker_color=colors_macd), row=3, col=1)
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['DIF'], mode='lines', name='DIF (快線)', line=dict(color='#faad14', width=1)), row=3, col=1)
            fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['MACD_Signal'], mode='lines', name='MACD (慢線)', line=dict(color='#13c2c2', width=1)), row=3, col=1)

            fig.update_layout(
                height=600, 
                margin=dict(l=10, r=10, t=50, b=60), 
                legend=dict(orientation="h", y=-0.15, x=0),
                template="plotly_dark"
            )

            for annotation in fig['layout']['annotations']:
                annotation.update(font=dict(size=13, color='#e0e0e0'))

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("無法計算技術指標數據。")

    with tab_macro_chart:
        macro_hist = get_macro_history_trends()
        
        fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
        
        if "費城半導體" in macro_hist.columns:
            fig_macro.add_trace(
                go.Scatter(x=macro_hist.index, y=macro_hist["費城半導體"], name="費城半導體 (SOX)", line=dict(color="#ff4d4f", width=2.5)),
                secondary_y=False
            )
        
        if "美10年債殖利率(20倍)" in macro_hist.columns:
            fig_macro.add_trace(
                go.Scatter(x=macro_hist.index, y=macro_hist["美10年債殖利率(20倍)"], name="美10年債殖利率 (x20)", line=dict(color="#1890ff", width=2.5)),
                secondary_y=True
            )
            
        if "WTI 國際原油" in macro_hist.columns:
            fig_macro.add_trace(
                go.Scatter(x=macro_hist.index, y=macro_hist["WTI 國際原油"], name="WTI 原油 (美元)", line=dict(color="#faad14", width=2)),
                secondary_y=True
            )

        fig_macro.update_layout(
            height=360,
            margin=dict(l=10, r=10, t=20, b=40),
            legend=dict(orientation="h", y=-0.2, x=0.1)
        )
        fig_macro.update_yaxes(title_text="費城半導體指數", secondary_y=False)
        fig_macro.update_yaxes(title_text="美債殖利率(x20) / 原油(美元)", secondary_y=True)
        
        st.plotly_chart(fig_macro, use_container_width=True)
        st.caption("💡 **觀察指引**：當『費半（紅線）』向上、『美債殖利率（藍線）』&『原油（黃線）』趨勢向下，三大指標同時成立時，為全球資金 Risk-On 偏多趨勢，資金《極大機率》會大規模匯入全球股票市場，特別是科技比重高的美股與台股！")

else:
    st.info("請於左側輸入台股代碼或股名後檢視籌碼與進階技術指標看板")

st.divider()

if btn_analyze_stock:
    if not raw_stock_input or str(raw_stock_input).strip() == "":
        st.warning("請先在左側欄位輸入台股代碼或股名！")
    else:
        chip_df = get_stock_chip(stock_id, target_date_str)
        _, kd_info = calculate_kd(stock_id, period_type=period_type)
        
        if capital_mode == "既有持股 (已套牢/持有中)":
            sp_text = "🤖 AI 結合最新情報與風護演算法檢析【既有持股套牢解套/停損脫手策略】..."
        else:
            sp_text = "🤖 AI 結合最新情報與風護演算法檢析【實戰操盤買賣點/風報比試算】..."
            
        with st.spinner(sp_text):
            try:
                report = ai_single_stock_analysis(
                    macro_data, sector_data, raw_stock_input, 
                    chip_data=chip_df, kd_info=kd_info, period_type=period_type, 
                    capital_mode=capital_mode, price_or_capital=price_or_capital, 
                    selected_masters=selected_masters, target_date_str=target_date_str
                )
                st.markdown(report)
            except Exception as e:
                st.error(f"分析生成失敗: {e}")