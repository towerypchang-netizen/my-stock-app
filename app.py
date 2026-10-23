# -*- coding: utf-8 -*-

import json
import math
import os
import re
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from google import genai
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf

# 設定網頁標題與寬版佈局

st.set_page_config(
page_title="全球總經與台股資金流 AI 矩陣分析系統", layout="wide"
)

# ---------------------------------------------------------

# 🎨 CSS 注入

# ---------------------------------------------------------

st.markdown( """  .main .block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; }

```
h2, h3, [data-testid="stSidebar"] h3 {
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    margin-top: 0.2rem !important;
    margin-bottom: 0.5rem !important;
}

h1 {
    font-size: 1.4rem !important;
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
}
[data-testid="stMetricDelta"]:has(svg[data-testid="stMetricDeltaIcon-Down"]) * {
    color: #52c41a !important;
}

.top-macro-card [data-testid="stMetricLabel"] p,
.top-macro-card [data-testid="stMetricLabel"] {
    font-size: 1.05rem !important;
    font-weight: 700 !important;
}

.top-macro-card [data-testid="stMetricValue"] > div,
.top-macro-card [data-testid="stMetricValue"] {
    font-size: 1.55rem !important;
    font-weight: 800 !important;
}

.top-macro-card [data-testid="stMetricDelta"] {
    font-size: 0.9rem !important;
    font-weight: 600 !important;
}

[data-testid="stExpander"] [data-testid="stMetricLabel"] p,
[data-testid="stExpander"] [data-testid="stMetricLabel"] {
    font-size: 0.78rem !important;
    font-weight: 500 !important;
}

[data-testid="stExpander"] [data-testid="stMetricValue"] > div,
[data-testid="stExpander"] [data-testid="stMetricValue"] {
    font-size: 1.0rem !important;
    font-weight: 600 !important;
}

[data-testid="stExpander"] [data-testid="stMetricDelta"] {
    font-size: 0.72rem !important;
    font-weight: 500 !important;
}

/* 指標看板與型態文字字級對齊修正 */
div[data-testid="metric-container"] div[data-testid="stMetricValue"] > div {
    font-size: 1.45rem !important;
    font-weight: 700 !important;
}

html, body, [class*="css"] { font-size: 15px; }
@media (max-width: 768px) {
    html, body, [class*="css"] { font-size: 13px !important; }
    [data-testid="stSidebar"] { width: 100% !important; }
}
</style>
""",
unsafe_allow_html=True,

```

)

# ==============================================================================

# 🔒 雙重身分認證機制

# ==============================================================================

def check_password(): if "authenticated" not in st.session_state: st.session_state.authenticated = False

```
if not st.session_state.authenticated:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔒 AI 股票分析系統雙重身分認證")

        user_email = st.text_input(
            "請輸入授權 Email (A組)：", placeholder="例如: xxxxx@gmail.com"
        )
        user_password = st.text_input(
            "請輸入存取密碼 (B組)：", type="password"
        )

        if st.button("確認登入", type="primary", use_container_width=True):
            default_emails = [
                "tower.yp.chang@gmail.com",
                "sherryhsu6155@gmail.com",
                "ha71850tw@gmail.com",
                "b12212219@gmail.com",
            ]
            default_passwords = ["615588", "085978"]

            allowed_emails = st.secrets.get("ALLOWED_EMAILS", default_emails)
            allowed_passwords = st.secrets.get(
                "ALLOWED_PASSWORDS", default_passwords
            )

            clean_email = user_email.strip().lower()
            clean_password = user_password.strip()
            allowed_emails_clean = [e.strip().lower() for e in allowed_emails]

            if (
                clean_email in allowed_emails_clean
                and clean_password in allowed_passwords
            ):
                st.session_state.authenticated = True
                st.success("雙重驗證成功，正在進入系統...")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("驗證失敗！Email 或密碼不符合授權紀錄，請重新確認！")
    return False
return True

```

if not check_password(): st.stop()

# ==============================================================================

# 順序 1：預先建立股市產業族群類別名單索引清冊 (全域對照結構)

# ==============================================================================

OFFICIAL_33_SECTORS = \[ "水泥工業", "食品工業", "塑膠工業", "紡織纖維", "電機機械", "電器電纜", "化學工業", "生技醫療業", "玻璃陶瓷", "造紙工業", "鋼鐵工業", "橡膠工業", "汽車工業", "半導體業", "電腦及週邊設備業", "光電業", "通信網路業", "電子零組件業", "電子通路業", "資訊服務業", "其他電子業", "建材營造", "航運業", "觀光餐旅", "金融保險業", "貿易百貨", "油電燃氣業", "綜合", "其他類", "綠能環保", "數位雲端", "運動休閒", "居家生活" \]

STOCK_NAME_TO_ID = { "台積電": "2330", "鴻海": "2317", "聯發科": "2454", "台達電": "2308", "廣達": "2382", "聯鈞": "3450", "上詮": "3363", "緯創": "3231", "華碩": "2357", "聯詠": "3034", "世芯": "3661", "世芯-KY": "3661", "世芯KY": "3661", "神達": "3706", "祥碩": "5269", "技嘉": "2376", "智邦": "2345", "和碩": "4938", "緯穎": "6669", "奇鋐": "3017", "華星光": "4979", "雙鴻": "3324", "高力": "8996", "京元電子": "2449", "智原": "3035", "光聖": "6442", "晟銘電": "3013", "志聖": "2467", "建準": "2421", "精華": "1565", "漢唐": "2404", "創意": "3443", "旺矽": "6239", "長榮": "2603", "陽明": "2609", "萬海": "2615", "富邦金": "2881", "國泰金": "2882", "中信金": "2891", "日月光": "3711", "日月光投控": "3711", "南亞科": "2408", "華邦電": "2344", "聯電": "2303", "欣興": "3037", "健鼎": "3044", "M31": "6643", "m31": "6643", "臻鼎": "4958", "臻鼎-KY": "4958", "臻鼎KY": "4958", "聯茂": "6213", "金像電": "2368", "台光電": "2383", "華通": "2313", "群創": "3481", "友達": "2409", "力積電": "6770", "威盛": "2388", "宏碁": "2353", "仁寶": "2324", "光寶科": "2301", "英業達": "2356", "威剛": "3260", "萬潤": "6187", "辛耘": "3583", "泰碩": "3338", "金居": "8358", "眾達": "4977", "眾達-KY": "4977", "眾達KY": "4977", "昇陽半": "8028", "昇陽半導體": "8028", "貿聯": "3665", "貿聯-KY": "3665", "貿聯KY": "3665", "雷虎": "8033", "漢翔": "2634", "聯亞": "3081", "台塑化": "6505", "雲豹能源": "6869", "台塑": "1301", "南亞": "1303", "國喬": "1312", "三福化": "4755", "亞力": "1514", "佳龍": "9955", "中碳": "1723", "兆豐金": "2886", "中鋼": "2002" }

STOCK_ID_TO_NAME = {v: k for k, v in STOCK_NAME_TO_ID.items()}

SYSTEM_STOCK_CATALOG = { "2330": {"name": "台積電", "sector": "半導體業", "market": "TWSE", "attr": \["權值股", "成長股"\]}, "2317": {"name": "鴻海", "sector": "其他電子業", "market": "TWSE", "attr": \["權值股", "成長股"\]}, "2454": {"name": "聯發科", "sector": "半導體業", "market": "TWSE", "attr": \["權值股", "成長股"\]}, "2308": {"name": "台達電", "sector": "電子零組件業", "market": "TWSE", "attr": \["權值股", "成長股"\]}, "2382": {"name": "廣達", "sector": "電腦及週邊設備業", "market": "TWSE", "attr": \["權值股", "成長股"\]}, "2881": {"name": "富邦金", "sector": "金融保險業", "market": "TWSE", "attr": \["權值股", "高股息股"\]}, "2882": {"name": "國泰金", "sector": "金融保險業", "market": "TWSE", "attr": \["權值股", "高股息股"\]}, "2891": {"name": "中信金", "sector": "金融保險業", "market": "TWSE", "attr": \["權值股", "高股息股"\]}, "2603": {"name": "長榮", "sector": "航運業", "market": "TWSE", "attr": \["景氣循環股", "高股息股"\]}, "2609": {"name": "陽明", "sector": "航運業", "market": "TWSE", "attr": \["景氣循環股"\]}, "2615": {"name": "萬海", "sector": "航運業", "market": "TWSE", "attr": \["景氣循環股"\]}, "1301": {"name": "台塑", "sector": "塑膠工業", "market": "TWSE", "attr": \["景氣循環股", "防禦型股票"\]}, "1303": {"name": "南亞", "sector": "塑膠工業", "market": "TWSE", "attr": \["景氣循環股"\]}, "6505": {"name": "台塑化", "sector": "油電燃氣業", "market": "TWSE", "attr": \["景氣循環股", "防禦型股票"\]}, "1514": {"name": "亞力", "sector": "電機機械", "market": "TWSE", "attr": \["成長股"\]}, "6869": {"name": "雲豹能源", "sector": "綠能環保", "market": "TWSE", "attr": \["防禦型股票", "成長股"\]}, "3231": {"name": "緯創", "sector": "電腦及週邊設備業", "market": "TWSE", "attr": \["成長股"\]}, "3017": {"name": "奇鋐", "sector": "電子零組件業", "market": "TWSE", "attr": \["成長股"\]}, "3324": {"name": "雙鴻", "sector": "電子零組件業", "market": "TPEx", "attr": \["成長股"\]}, "6442": {"name": "光聖", "sector": "通信網路業", "market": "TWSE", "attr": \["成長股"\]}, "3081": {"name": "聯亞", "sector": "通信網路業", "market": "TPEx", "attr": \["成長股"\]}, "3661": {"name": "世芯-KY", "sector": "半導體業", "market": "TWSE", "attr": \["成長股"\]}, "2408": {"name": "南亞科", "sector": "半導體業", "market": "TWSE", "attr": \["景氣循環股"\]}, "2002": {"name": "中鋼", "sector": "鋼鐵工業", "market": "TWSE", "attr": \["權值股", "景氣循環股"\]}, }

OFFICIAL_STOCK_SECTOR_MAP = { "2330": "晶圓代工", "2303": "晶圓代工", "2317": "AI伺服器", "2454": "IC設計", "2308": "電源設備", "2382": "AI伺服器", "3231": "AI伺服器", "2357": "電腦週邊", "3034": "IC設計", "3661": "ASIC晶片", "3017": "液冷散熱", "3324": "液冷散熱", "8996": "液冷散熱", "6442": "CPO光通", "3081": "CPO光通", "4979": "CPO光通", "3450": "CPO光通", "3363": "CPO光通", "6213": "PCB銅箔", "2368": "PCB載板", "2383": "PCB銅箔", "4958": "PCB載板", "3037": "PCB載板", "6187": "半導體設備", "3583": "半導體設備", "8028": "半導體材料", "2449": "半導體封測", "6505": "塑化煉油", "1301": "塑化原料", "1303": "塑化原料", "1312": "塑膠工業", "1326": "塑化原料", "4755": "化學工業", "1514": "重電設備", "1513": "重電設備", "1504": "重電設備", "6869": "綠能雲端", "2603": "貨櫃航運", "2609": "貨櫃航運", "2615": "貨櫃航運", "2881": "金控金融", "2882": "金控金融", "2891": "金控金融", "2408": "記憶體", "2344": "記憶體", "3260": "記憶體", "9955": "綠能環保", }

FORBIDDEN_SECTOR_TAGS = \[ "高殖利率", "高股息", "防禦族群", "避險族群", "概念股", "潛力股" \]

LARGE_CAP_STOCKS = \[ "2330", "2317", "2454", "2308", "2382", "2881", "2882", "2891", "3711", "2303", "2886", "2002" \]

PEER_GROUPS = { "CPO/光通訊/矽光子": \["6442", "3081", "4979", "3163", "4977"\], "液冷/散熱模組": \["3324", "8996", "3017", "2308", "3013", "3338"\], "PCB/銅箔基板/載板": \["6213", "2368", "2383", "4958", "3037", "3044", "2313", "8358"\], "晶圓代工/半導體/設備": \["2330", "2303", "6770", "3711", "2449", "2467", "2404", "6187", "3583", "8028"\], "IC 設計/ASIC": \["2454", "3034", "3661", "5269", "3443", "6643", "2388", "3035"\], "AI 伺服器/組裝/線束": \["2317", "2382", "3231", "2357", "2376", "4938", "6669", "2353", "2324", "2356", "2421", "3665"\], "記憶體/模組": \["3260", "2408", "2344"\], "航運": \["2603", "2609", "2615"\], "金控": \["2881", "2882", "2891", "2886"\], "重電/綠能/環保": \["1514", "6869", "1513", "1504", "9955"\], "塑化原料/特化": \["6505", "1301", "1303", "1312", "4755", "1723"\], }

HTTP_HEADERS = { "User-Agent": ( "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" ) }

DEFAULT_MACRO_CACHE = { "台股加權": {"val": "46,041.43", "change": "-1.81%", "change_num": -846.34, "pct": -1.81, "raw_close": 46041.43}, "費城半導體 SOX": {"val": "11,505.56", "change": "+1.97%", "change_num": 222.10, "pct": 1.97, "raw_close": 11505.56}, "美債 10Y 殖利率": {"val": "5.09%", "change": "-1.17%", "change_num": -0.06, "pct": -1.17, "raw_close": 5.09}, "恐慌指數 VIX": {"val": "16.6800", "change": "-3.64%", "change_num": -0.63, "pct": -3.64, "raw_close": 16.68}, "台指期夜盤": {"val": "47,482", "change": "+469 點", "change_num": 469.0, "pct": 1.0, "raw_close": 47482.0}, "日經 225 N225": {"val": "62,907.84", "change": "-2.65%", "change_num": -1713.40, "pct": -2.65, "raw_close": 62907.84}, "道瓊工業 DJI": {"val": "52,856.09", "change": "+0.69%", "change_num": 362.10, "pct": 0.69, "raw_close": 52856.09}, "那斯達克 NASDAQ": {"val": "26,702.86", "change": "+1.05%", "change_num": 277.30, "pct": 1.05, "raw_close": 26702.86}, "標普 500 S&P500": {"val": "7,757.17", "change": "+0.58%", "change_num": 44.70, "pct": 0.58, "raw_close": 7757.17}, "羅素 2000 RUT": {"val": "2,781.02", "change": "+0.27%", "change_num": 7.50, "pct": 0.27, "raw_close": 2781.02}, "美聯儲 13W 短貼率": {"val": "4.06%", "change": "-0.42%", "change_num": -0.017, "pct": -0.42, "raw_close": 4.06}, "美元指數 DXY": {"val": "101.64", "change": "-0.14%", "change_num": -0.14, "pct": -0.14, "raw_close": 101.64}, "WTI 原油": {"val": "98.44", "change": "+0.45%", "change_num": 0.44, "pct": 0.45, "raw_close": 98.44}, "黃金現貨 Gold": {"val": "4,070.02", "change": "-1.34%", "change_num": -55.48, "pct": -1.34, "raw_close": 4070.02}, }

if "macro_cache" not in st.session_state: st.session_state.macro_cache = DEFAULT_MACRO_CACHE if "premarket_focus" not in st.session_state: st.session_state.premarket_focus = \[\] if "premarket_avoid" not in st.session_state: st.session_state.premarket_avoid = \[\] if "premarket_summary" not in st.session_state: st.session_state.premarket_summary = "尚未進行盤前情報診斷，系統將採用標準 Top-Down 策略。"

# ==============================================================================

# 順序 2：系統抓取與全量即時資訊網絡 (完全照抄原版 1022 資料源)

# ==============================================================================

def fetch_twse_mis_taiex(): ts = int(time.time() \* 1000) try: twse_url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&\_={ts}" resp = requests.get(twse_url, headers=HTTP_HEADERS, timeout=2.5) if resp.status_code == 200: msg_arr = resp.json().get("msgArray", \[\]) if msg_arr: data = msg_arr\[0\] p_str = data.get("z") if data.get("z") and data.get("z") != "-" else data.get("y") y_str = data.get("y") if p_str and y_str: p_val = float(p_str) y_val = float(y_str) chg_val = p_val - y_val pct_val = (chg_val / y_val) \* 100 if y_val > 0 else 0.0 if p_val > 10000: return { "val": f"{p_val:,.2f}", "change": f"{pct_val:+.2f}%", "change_num": round(chg_val, 2), "pct": round(pct_val, 2), "raw_close": p_val } except Exception: pass return None

def fetch_taifex_futures_night(): ts = int(time.time() \* 1000) try: url = f"https://mis.taifex.com.tw/futures/api/getQuoteList?\_={ts}" payload = {"MarketType": "1", "SymbolType": "F"} resp = requests.post(url, json=payload, headers=HTTP_HEADERS, timeout=2.5) if resp.status_code == 200: quotes = resp.json().get("rtData", {}).get("QuoteList", \[\]) for q in quotes: symbol = q.get("SymbolID", "") if symbol.startswith("TX") and not symbol.startswith("TXO"): p_str = q.get("CLastPrice") or q.get("CLastP") or q.get("CRefPrice") ref_str = q.get("CRefPrice") if p_str and ref_str and p_str != "-": p_val = float(p_str) ref_val = float(ref_str) chg_val = p_val - ref_val pct_val = (chg_val / ref_val) \* 100 if ref_val > 0 else 0.0 return { "val": f"{int(p_val):,}", "change": f"{chg_val:+.0f} 點", "change_num": round(chg_val, 1), "pct": round(pct_val, 2), "raw_close": p_val } except Exception: pass return None

def fetch_yahoo_api_quote(symbol_encoded, is_yield=False, is_points=False): ts = int(time.time() \* 1000) url = f"https://tw.stock.yahoo.com/v1/finance/price?symbol={symbol_encoded}&\_t={ts}" try: resp = requests.get(url, headers=HTTP_HEADERS, timeout=3.0) if resp.status_code == 200: quote = resp.json().get("data", {}).get("quote", {}) price = quote.get("price") or quote.get("regularMarketPrice") prev_close = quote.get("previousClose") or quote.get("regularMarketPreviousClose") if price is not None and prev_close is not None and prev_close > 0: p_val = float(price) prev_val = float(prev_close) chg_val = p_val - prev_val pct_val = (chg_val / prev_val) \* 100

```
            if is_yield:
                fmt_val = f"{p_val:.2f}%"
                chg_str = f"{pct_val:+.2f}%"
            elif is_points:
                fmt_val = f"{int(p_val):,}"
                chg_str = f"{chg_val:+.0f} 點"
            elif symbol_encoded in ["%5EVIX"]:
                fmt_val = f"{p_val:.4f}"
                chg_str = f"{pct_val:+.2f}%"
            else:
                fmt_val = f"{p_val:,.2f}".replace(".00", "")
                chg_str = f"{pct_val:+.2f}%"

            return {
                "val": fmt_val,
                "change": chg_str,
                "change_num": round(chg_val, 2),
                "pct": round(pct_val, 2),
                "raw_close": p_val
            }
except Exception:
    pass
return None

```

def fetch_yfinance_fallback(symbol, is_yield=False): try: ticker = yf.Ticker(symbol) df = ticker.history(period="5d").dropna(subset=\["Close"\]) if not df.empty and len(df) >= 1: p_val = float(df\["Close"\].iloc\[-1\]) prev_val = float(df\["Close"\].iloc\[-2\]) if len(df) >= 2 else p_val chg_val = p_val - prev_val pct_val = (chg_val / prev_val) \* 100 if prev_val > 0 else 0.0

```
        if is_yield:
            fmt_val = f"{p_val:.2f}%"
        elif symbol in ["^VIX"]:
            fmt_val = f"{p_val:.4f}"
        else:
            fmt_val = f"{p_val:,.2f}".replace(".00", "")

        return {
            "val": fmt_val,
            "change": f"{pct_val:+.2f}%",
            "change_num": round(chg_val, 2),
            "pct": round(pct_val, 2),
            "raw_close": p_val
        }
except Exception:
    pass
return None

```

def get_macro_item_with_pipeline(name, twse_code=None, taifex_type=None, yahoo_symbol=None, is_yield=False, is_points=False): if twse_code: res = fetch_twse_mis_taiex() if res: return res if taifex_type: res = fetch_taifex_futures_night() if res: return res if yahoo_symbol: res = fetch_yahoo_api_quote(yahoo_symbol, is_yield=is_yield, is_points=is_points) if res: return res if yahoo_symbol: sym_clean = yahoo_symbol.replace("%5E", "^").replace("%26", "&") res = fetch_yfinance_fallback(sym_clean, is_yield=is_yield) if res: return res return st.session_state.macro_cache.get(name, DEFAULT_MACRO_CACHE.get(name))

def force_refresh_all_macro_data(): st.cache_data.clear() new_cache = {} new_cache\["台股加權"\] = get_macro_item_with_pipeline("台股加權", twse_code="tse_t00.tw", yahoo_symbol="%5ETWII") new_cache\["台指期夜盤"\] = get_macro_item_with_pipeline("台指期夜盤", taifex_type="TX", yahoo_symbol="%5ETW%26", is_points=True) new_cache\["日經 225 N225"\] = get_macro_item_with_pipeline("日經 225 N225", yahoo_symbol="%5EN225") new_cache\["費城半導體 SOX"\] = get_macro_item_with_pipeline("費城半導體 SOX", yahoo_symbol="%5ESOX") new_cache\["美債 10Y 殖利率"\] = get_macro_item_with_pipeline("美債 10Y 殖利率", yahoo_symbol="%5ETNX", is_yield=True) new_cache\["恐慌指數 VIX"\] = get_macro_item_with_pipeline("恐慌指數 VIX", yahoo_symbol="%5EVIX") new_cache\["道瓊工業 DJI"\] = get_macro_item_with_pipeline("道瓊工業 DJI", yahoo_symbol="%5EDJI") new_cache\["那斯達克 NASDAQ"\] = get_macro_item_with_pipeline("那斯達克 NASDAQ", yahoo_symbol="%5EIXIC") new_cache\["標普 500 S&P500"\] = get_macro_item_with_pipeline("標普 500 S&P500", yahoo_symbol="%5EGSPC") new_cache\["羅素 2000 RUT"\] = get_macro_item_with_pipeline("羅素 2000 RUT", yahoo_symbol="%5ERUT") new_cache\["美聯儲 13W 短貼率"\] = get_macro_item_with_pipeline("美聯儲 13W 短貼率", yahoo_symbol="%5EIRX", is_yield=True) new_cache\["美元指數 DXY"\] = get_macro_item_with_pipeline("美元指數 DXY", yahoo_symbol="DX-Y.NYB") new_cache\["WTI 原油"\] = get_macro_item_with_pipeline("WTI 原油", yahoo_symbol="CL%3DF") new_cache\["黃金現貨 Gold"\] = get_macro_item_with_pipeline("黃金現貨 Gold", yahoo_symbol="GC%3DF")

```
st.session_state.macro_cache = new_cache
return new_cache

```

@st.cache_data(ttl=86400) def get_all_taiwan_stocks_dict(): all_stocks = {} for k, v in STOCK_NAME_TO_ID.items(): all_stocks\[k\] = v all_stocks\[v\] = k try: url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL" resp = requests.get(url_twse, headers=HTTP_HEADERS, timeout=3) if resp.status_code == 200: for item in resp.json(): s_id = str(item.get("Code", "")).strip() s_name = str(item.get("Name", "")).strip() if s_id and s_name: all_stocks\[s_name\] = s_id all_stocks\[s_id\] = s_name except Exception: pass

```
try:
    url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    resp = requests.get(url_tpex, headers=HTTP_HEADERS, timeout=3)
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

```

def parse_stock_input(user_input): if not user_input: return "" clean_input = str(user_input).strip().replace(" ", "") if clean_input.isdigit(): return clean_input if clean_input in STOCK_NAME_TO_ID: return STOCK_NAME_TO_ID\[clean_input\]

```
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

```

@st.cache_data(ttl=86400) def get_twse_stock_name(stock_id): try: url = "https://www.twse.com.tw/rwd/zh/api/codeMarket?response=json" resp = requests.get(url, headers=HTTP_HEADERS, timeout=2) if resp.status_code == 200: data = resp.json() for row in data.get("data", \[\]): if len(row) >= 2 and row\[0\].strip() == str(stock_id).strip(): return row\[1\].strip() except Exception: pass return None

def get_stock_display_name(raw_input, stock_id): if not stock_id: return "未指定" clean_input = str(raw_input).strip() pure_name = re.
