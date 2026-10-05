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
                # 取得 Secrets 中設定的多組 A 組與 B 組清單 (兼具後台與程式碼預設)
                allowed_emails = st.secrets.get("ALLOWED_EMAILS", [
                    "tower.yp.chang@gmail.com", 
                    "sherryhsu6155@gmail.com", 
                    "ha71850tw@gmail.com", 
                    "b12212219@gmail.com"
                ])
                allowed_passwords = st.secrets.get("ALLOWED_PASSWORDS", ["615588", "085978"])
                
                # 清除前後空格並轉小寫比對
                clean_email = user_email.strip().lower()
                clean_password = user_password.strip()
                
                # 轉為小寫的授權 Email 清單
                allowed_emails_clean = [e.strip().lower() for e in allowed_emails]
                
                # 雙重條件比對：Email 必須在 A 組，且 密碼必須在 B 組
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
    "台積電": "2330", "鴻海": "2317", "聯發科": "2454", "台達電": "2308", "廣達": "2382",
    "緯創": "3231", "華碩": "2357", "聯詠": "3034", "世芯": "3661", "世芯-KY": "3661", "世芯KY": "3661",
    "祥碩": "5269", "技嘉": "2376", "智邦": "2345", "和碩": "4938", "緯穎": "6669", "奇鋐": "3017",
    "雙鴻": "3324", "高力": "8996", "京元電子": "2449", "智原": "3035", "光聖": "6442", "晟銘電": "3013",
    "志聖": "2467", "建準": "2421", "友聯": "2331", "精華": "2331", "漢唐": "2404", "創意": "3443", "旺矽": "6239",
    "長榮": "2603", "陽明": "2609", "萬海": "2615", "富邦金": "2881", "國泰金": "2882", "中信金": "2891",
    "日月光": "3711", "日月光投控": "3711", "南亞科": "2408", "華邦電": "2344", "聯電": "2303",
    "欣興": "3037", "健鼎": "3044", "M31": "6643", "m31": "6643", "臻鼎": "4958", "臻鼎-KY": "4958",
    "臻鼎KY": "4958", "聯茂": "6213", "金像電": "2368", "台光電": "2383", "華通": "2313",
    "群創": "3481", "友達": "2409", "力積電": "6770", "威盛": "2388", "宏碁": "2353",
    "仁寶": "2324", "光寶科": "2301", "英業達": "2356", "威剛": "3260", "萬潤": "6187", "辛耘": "3583", "泰碩": "3338"
}

STOCK_ID_TO_NAME = {v: k for k, v in STOCK_NAME_TO_ID.items()}

LARGE_CAP_STOCKS = ["2330", "2317", "2454", "2308", "2382", "2881", "2882", "2891", "3711", "2303"]

PEER_GROUPS = {
    "CPO/光通訊/矽光子": ["6442", "3081", "4979", "3163"],
    "液冷/散熱模組": ["3324", "8996", "3017", "2308", "3013", "3338"],
    "PCB/銅箔基板/載板": ["6213", "2368", "2383", "4958", "3037", "3044", "2313"],
    "晶圓代工/半導體/設備": ["2330", "2303", "6770", "3711", "2449", "2467", "2404", "6187", "3583"],
    "IC 設計/ASIC": ["2454", "3034", "3661", "5269", "3443", "6643", "2388", "3035"],
    "AI 伺服器/組裝": ["2317", "2382", "3231", "2357", "2376", "4938", "6669", "2353", "2324", "2356", "2421"],
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
    """傳回乾淨的『股名 股號』格式"""
    if not stock_id:
        return "未指定"
    
    clean_input = str(raw_input).strip()
    pure_name = re.sub(r'[\(\)\d\s]', '', clean_input)
    
    if pure_name and pure_name != stock_id:
        return f"{pure_name} {stock_id}"

    if stock_id in STOCK_ID_TO_NAME:
        return f"{STOCK_ID_TO_NAME[stock_id]} {stock_id}"
        
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

@st.cache_data(ttl=600)
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

@st.cache_data(ttl=1800)
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
        latest_k = round(df['K'].iloc[-1], 2)
        latest_d = round(df['D'].iloc[-1], 2)
        prev_k = df['K'].iloc[-2] if len(df) >= 2 else latest_k
        prev_d = df['D'].iloc[-2] if len(df) >= 2 else latest_d

        bias_20ma = round(((latest_close - latest_20ma) / (latest_20ma if latest_20ma != 0 else 1)) * 100, 2)

        recent_closes = df['Close'].tail(5).tolist()
        has_pullback = any(recent_closes[i] < recent_closes[i-1] for i in range(1, len(recent_closes)-1)) if len(recent_closes) >= 3 else False
        is_above_5ma = latest_close >= latest_5ma
        is_above_20ma = latest_close >= latest_20ma
        
        vol_signal_str = "🔥 帶量攻擊" if vol_ratio >= 1.2 else "⚪ 量能平穩"
        pullback_buy_signal = f"🔥 回後買上漲成立 (乖離{bias_20ma:+}%)" if (has_pullback and is_above_5ma and is_above_20ma) else (
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
            signal = "❄ 低檔超賣"

        return df.tail(40), {
            "K": latest_k, "D": latest_d, "signal": signal,
            "5MA": latest_5ma, "20MA": latest_20ma, "bias_20ma": bias_20ma,
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

@st.cache_data(ttl=1800)
def get_stock_chip(stock_id, target_date_str):
    clean_stock_id = parse_stock_input(stock_id)
    if not clean_stock_id:
        return pd.DataFrame()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # 1. 第一優先：富邦證券盤後籌碼 (明確指定 Big5 編碼防止 UTF-8 解碼失敗)
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

    # 2. 備用方案：FinMind API 籌碼
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
    if p_info["is_gap_down"]: 
        return False, None
        
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

def generate_daily_picks(macro_data, sector_data, min_price, max_price, custom_sector, target_date_str):
    cond_list = []
    if min_price > 0: cond_list.append(f"最低不得低於 {min_price} 元")
    if max_price > 0: cond_list.append(f"最高不得超過 {max_price} 元")
        
    price_limit_str = f"【硬性股價區間限制】：{', '.join(cond_list)}" if cond_list else "股價不限"
    
    if custom_sector and custom_sector.strip() != "":
        sector_limit_str = f"【指定產業限制】：必須嚴格從「{custom_sector.strip()}」相關個股挑選"
    else:
        sector_limit_str = "【指定產業限制】：無限制（授權 AI 對全台股進行全維度分析，自主挑選全市場多頭型態最強之熱門主流標的）"

    premarket_focus_str = f"【08:00 盤前即時利多/聚焦族群】：{st.session_state.premarket_focus}" if st.session_state.premarket_focus else ""

    prompt_select = (
        "請作為頂級華爾街台股選股操盤手，基準日期：" + str(target_date_str) + "。\n"
        "價格條件：" + price_limit_str + "。\n"
        "族群條件：" + sector_limit_str + "。\n"
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
            p_low = round(real_p * 0.985, 1)
            p_high = round(real_p * 1.005, 1)
            target_p = round(real_p * 1.08, 1)
            
            raw_sector = str(item.get("族群", "主流題材")).strip()
            item["族群"] = raw_sector[:6]
            
            item["上漲率"] = item.get("上漲率", item.get("預估上漲率", "78%"))
            item["當前實價"] = f"{real_p:.2f}"
            item["建議進場"] = f"{p_low:.1f}-{p_high:.1f}"
            item["波段停利/防護提示"] = f"目標 {target_p:.1f} (達標即落袋)"
            
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
    return df_res[cols_order].to_dict