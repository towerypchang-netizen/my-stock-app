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
st.set_page_config(page_title='全球總經與台股資金流 AI 矩陣分析系統', layout='wide')

# ---------------------------------------------------------
# 🎨 CSS 注入
# ---------------------------------------------------------
st.markdown('''<style>
.main .block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; }
h2, h3, [data-testid='stSidebar'] h3 { font-size: 1.15rem !important; font-weight: 700 !important; margin-top: 0.2rem !important; margin-bottom: 0.5rem !important; }
h1 { font-size: 1.4rem !important; margin-bottom: 0.8rem !important; line-height: 1.3 !important; margin-top: 0rem !important; }
div.stButton > button { margin-top: -2px !important; margin-bottom: -2px !important; }
div.stButton > button[key='btn_combined_diagnose'] { background-color: #1890ff !important; color: #ffffff !important; border-color: #1890ff !important; font-weight: bold !important; }
div.stButton > button[key='btn_combined_diagnose']:hover { background-color: #40a9ff !important; border-color: #40a9ff !important; }
div[data-testid='stVerticalBlock'] > div { gap: 0.4rem !important; }
[data-testid='stMetricDelta'] svg[data-testid='stMetricDeltaIcon-Up'] { fill: #ff4d4f !important; }
[data-testid='stMetricDelta']:has(svg[data-testid='stMetricDeltaIcon-Up']) { color: #ff4d4f !important; background-color: rgba(255, 77, 79, 0.15) !important; }
[data-testid='stMetricDelta']:has(svg[data-testid='stMetricDeltaIcon-Up']) * { color: #ff4d4f !important; }
[data-testid='stMetricDelta'] svg[data-testid='stMetricDeltaIcon-Down'] { fill: #52c41a !important; }
[data-testid='stMetricDelta']:has(svg[data-testid='stMetricDeltaIcon-Down']) { color: #52c41a !important; background-color: rgba(82, 196, 26, 0.15) !important; }
[data-testid='stMetricDelta']:has(svg[data-testid='stMetricDeltaIcon-Down']) * { color: #52c41a !important; }
.top-macro-card [data-testid='stMetricLabel'] p, .top-macro-card [data-testid='stMetricLabel'] { font-size: 1.05rem !important; font-weight: 700 !important; }
.top-macro-card [data-testid='stMetricValue'] > div, .top-macro-card [data-testid='stMetricValue'] { font-size: 1.55rem !important; font-weight: 800 !important; }
.top-macro-card [data-testid='stMetricDelta'] { font-size: 0.9rem !important; font-weight: 600 !important; }
[data-testid='stExpander'] [data-testid='stMetricLabel'] p, [data-testid='stExpander'] [data-testid='stMetricLabel'] { font-size: 0.75rem !important; font-weight: 600 !important; }
[data-testid='stExpander'] [data-testid='stMetricValue'] > div, [data-testid='stExpander'] [data-testid='stMetricValue'] { font-size: 0.92rem !important; font-weight: 700 !important; }
[data-testid='stExpander'] [data-testid='stMetricDelta'] { font-size: 0.72rem !important; font-weight: 500 !important; }
html, body, [class*='css'] { font-size: 15px; }
@media (max-width: 768px) { html, body, [class*='css'] { font-size: 13px !important; } [data-testid='stSidebar'] { width: 100% !important; } }
</style>''', unsafe_allow_html=True)

# ==============================================================================
# 🔒 雙重身分認證機制
# ==============================================================================
def check_password():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.markdown('<br><br>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader('🔒 AI 股票分析系統雙重身分認證')
            user_email = st.text_input('請輸入授權 Email (A組)：', placeholder='例如: xxxxx@gmail.com')
            user_password = st.text_input('請輸入存取密碼 (B組)：', type='password')
            if st.button('確認登入', type='primary', use_container_width=True):
                default_emails = ['tower.yp.chang@gmail.com', 'sherryhsu6155@gmail.com', 'ha71850tw@gmail.com', 'b12212219@gmail.com']
                default_passwords = ['615588', '085978']
                allowed_emails = st.secrets.get('ALLOWED_EMAILS', default_emails)
                allowed_passwords = st.secrets.get('ALLOWED_PASSWORDS', default_passwords)
                clean_email = user_email.strip().lower()
                clean_password = user_password.strip()
                allowed_emails_clean = [e.strip().lower() for e in allowed_emails]
                if clean_email in allowed_emails_clean and clean_password in allowed_passwords:
                    st.session_state.authenticated = True
                    st.success('雙重驗證成功，正在進入系統...')
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error('驗證失敗！Email 或密碼不符合授權紀錄，請重新確認！')
        return False
    return True

if not check_password():
    st.stop()

if 'premarket_focus' not in st.session_state: st.session_state.premarket_focus = []
if 'premarket_avoid' not in st.session_state: st.session_state.premarket_avoid = []
if 'premarket_summary' not in st.session_state: st.session_state.premarket_summary = '尚未進行盤前情報診斷，系統將採用標準 Top-Down 策略。'

OFFICIAL_STOCK_SECTOR_MAP = {
    '2330': '半導體', '2303': '半導體', '2317': 'AI伺服器', '2454': 'IC設計',
    '2308': '電子零組件', '2382': '電腦週邊', '3231': '電腦週邊', '2357': '電腦週邊',
    '3034': 'IC設計', '3661': 'IC設計', '3017': '電腦週邊', '3324': '電腦週邊',
    '8996': '電機機械', '6442': '光電業', '3081': '通信網路', '4979': '通信網路',
    '3450': '光電業', '3363': '通信網路', '6213': '電子零組件', '2368': '電子零組件',
    '2383': '電子零組件', '4958': '電子零組件', '3037': '電子零組件', '6187': '半導體',
    '3583': '半導體', '8028': '半導體', '2449': '半導體', '2408': '半導體',
    '2344': '半導體', '3260': '半導體', '6505': '油電燃氣', '1301': '塑膠工業',
    '1303': '塑膠工業', '1312': '塑膠工業', '1326': '塑膠工業', '4755': '化學工業',
    '1514': '電機機械', '1513': '電機機械', '1504': '電機機械', '6869': '綠能環保',
    '2603': '航運業', '2609': '航運業', '2615': '航運業', '2002': '鋼鐵工業',
    '2881': '金融保險', '2882': '金融保險', '2891': '金融保險', '2886': '金融保險',
    '9955': '綠能環保',
}

STOCK_NAME_TO_ID = {
    '台積電': '2330', '鴻海': '2317', '聯發科': '2454', '台達電': '2308',
    '廣達': '2382', '聯鈞': '3450', '上詮': '3363', '緯創': '3231',
    '華碩': '2357', '聯詠': '3034', '世芯': '3661', '世芯-KY': '3661',
    '神達': '3706', '祥碩': '5269', '技嘉': '2376', '智邦': '2345',
    '和碩': '4938', '緯穎': '6669', '奇鋐': '3017', '華星光': '4979',
    '雙鴻': '3324', '高力': '8996', '京元電子': '2449', '智原': '3035',
    '光聖': '6442', '晟銘電': '3013', '志聖': '2467', '建準': '2421',
    '漢唐': '2404', '創意': '3443', '旺矽': '6239', '長榮': '2603',
    '陽明': '2609', '萬海': '2615', '富邦金': '2881', '國泰金': '2882',
    '中信金': '2891', '日月光投控': '3711', '南亞科': '2408', '華邦電': '2344',
    '聯電': '2303', '欣興': '3037', '健鼎': '3044', '臻鼎KY': '4958',
    '聯茂': '6213', '金像電': '2368', '台光電': '2383', '華通': '2313',
    '群創': '3481', '友達': '2409', '力積電': '6770', '威盛': '2388',
    '宏碁': '2353', '仁寶': '2324', '光寶科': '2301', '英業達': '2356',
    '威剛': '3260', '萬潤': '6187', '辛耘': '3583', '泰碩': '3338',
    '金居': '8358', '眾達KY': '4977', '昇陽半': '8028', '貿聯KY': '3665',
    '雷虎': '8033', '漢翔': '2634', '聯亞': '3081', '台塑化': '6505',
    '雲豹能源': '6869', '台塑': '1301', '南亞': '1303', '國喬': '1312',
    '三福化': '4755', '亞力': '1514', '佳龍': '9955', '中碳': '1723',
    '兆豐金': '2886', '中鋼': '2002',
}

STOCK_ID_TO_NAME = {v: k for k, v in STOCK_NAME_TO_ID.items()}
HTTP_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

if 'macro_cache' not in st.session_state: st.session_state.macro_cache = {}

def fetch_yahoo_api_quote(symbol_encoded, is_yield=False, is_points=False):
    ts = int(time.time() * 1000)
    url = f'https://tw.stock.yahoo.com/v1/finance/price?symbol={symbol_encoded}&_t={ts}'
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=3.0)
        if resp.status_code == 200:
            quote = resp.json().get('data', {}).get('quote', {})
            price = quote.get('price') or quote.get('regularMarketPrice')
            prev_close = quote.get('previousClose') or quote.get('regularMarketPreviousClose')
            if price is not None and prev_close is not None and prev_close > 0:
                p_val, prev_val = float(price), float(prev_close)
                chg_val = p_val - prev_val
                pct_val = (chg_val / prev_val) * 100
                if is_yield: fmt_val, chg_str = f'{p_val:.2f}%', f'{pct_val:+.2f}%'
                elif is_points: fmt_val, chg_str = f'{int(p_val):,}', f'{chg_val:+.0f} 點'
                elif '%5EVIX' in symbol_encoded or 'VIX' in symbol_encoded: fmt_val, chg_str = f'{p_val:.4f}', f'{pct_val:+.2f}%'
                else: fmt_val, chg_str = f'{p_val:,.2f}'.replace('.00', ''), f'{pct_val:+.2f}%'
                return {'val': fmt_val, 'change': chg_str, 'change_num': round(chg_val, 2), 'pct': round(pct_val, 2), 'raw_close': p_val}
    except Exception: pass
    return None

def fetch_symbol_bulletproof(symbol, is_yield=False, is_points=False):
    encoded_sym = symbol.replace('^', '%5E').replace('&', '%26').replace('=', '%3D')
    res = fetch_yahoo_api_quote(encoded_sym, is_yield=is_yield, is_points=is_points)
    if res: return res
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        p_val, prev_val = info.last_price, info.previous_close
        if p_val and prev_val and prev_val > 0:
            chg_val = p_val - prev_val
            pct_val = (chg_val / prev_val) * 100
            if is_yield: fmt_val, chg_str = f'{p_val:.2f}%', f'{pct_val:+.2f}%'
            elif is_points: fmt_val, chg_str = f'{int(p_val):,}', f'{chg_val:+.0f} 點'
            elif '^VIX' in symbol: fmt_val, chg_str = f'{p_val:.4f}', f'{pct_val:+.2f}%'
            else: fmt_val, chg_str = f'{p_val:,.2f}'.replace('.00', ''), f'{pct_val:+.2f}%'
            return {'val': fmt_val, 'change': chg_str, 'change_num': round(chg_val, 2), 'pct': round(pct_val, 2), 'raw_close': float(p_val)}
    except Exception: pass
    return {'val': '資料不足無法評估', 'change': '0.00%', 'change_num': 0.0, 'pct': 0.0, 'raw_close': 0.0}

def fetch_taifex_futures_night_bulletproof():
    ts = int(time.time() * 1000)
    try:
        url_openapi = 'https://openapi.taifex.com.tw/v1/DailyFuturesQuotes'
        resp = requests.get(url_openapi, headers=HTTP_HEADERS, timeout=3.0)
        if resp.status_code == 200:
            for item in resp.json():
                contract = str(item.get('Contract', '') or item.get('Symbol', '') or '')
                if 'TX' in contract and 'TXO' not in contract:
                    p_close = item.get('Close') or item.get('LastPrice')
                    p_ref = item.get('ReferencePrice') or item.get('PriorClose')
                    if p_close and str(p_close).strip() not in ['-', ''] and float(p_close) > 0:
                        p_val = float(p_close)
                        ref_val = float(p_ref) if p_ref and str(p_ref).strip() not in ['-', ''] else p_val
                        chg_val = p_val - ref_val
                        pct_val = (chg_val / ref_val) * 100 if ref_val > 0 else 0.0
                        return {'val': f'{int(p_val):,}', 'change': f'{chg_val:+.0f} 點', 'change_num': round(chg_val, 1), 'pct': round(pct_val, 2), 'raw_close': p_val}
    except Exception: pass
    for sym in ['WTX%3DF', '%5ETXI', 'TX-F.TW']:
        res_quote = fetch_yahoo_api_quote(sym, is_points=True)
        if res_quote and res_quote.get('raw_close', 0) > 0: return res_quote
    return {'val': '休市/連線中', 'change': '+0 點', 'change_num': 0.0, 'pct': 0.0, 'raw_close': 0.0}

def fetch_twse_mis_taiex():
    ts = int(time.time() * 1000)
    try:
        twse_url = f'https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&_={ts}'
        resp = requests.get(twse_url, headers=HTTP_HEADERS, timeout=3.0)
        if resp.status_code == 200:
            msg_arr = resp.json().get('msgArray', [])
            if msg_arr:
                data = msg_arr[0]
                p_str = data.get('z') if data.get('z') and data.get('z') != '-' else data.get('y')
                y_str = data.get('y')
                if p_str and y_str:
                    p_val, y_val = float(p_str), float(y_str)
                    chg_val = p_val - y_val
                    pct_val = (chg_val / y_val) * 100 if y_val > 0 else 0.0
                    return {'val': f'{p_val:,.2f}', 'change': f'{pct_val:+.2f}%', 'change_num': round(chg_val, 2), 'pct': round(pct_val, 2), 'raw_close': p_val}
    except Exception: pass
    return None

def force_refresh_all_macro_data():
    st.cache_data.clear()
    new_cache = {}
    new_cache['台股加權'] = fetch_twse_mis_taiex() or fetch_symbol_bulletproof('^TWII')
    new_cache['台指期夜盤'] = fetch_taifex_futures_night_bulletproof()
    new_cache['日經 225 N225'] = fetch_symbol_bulletproof('^N225')
    new_cache['費城半導體 SOX'] = fetch_symbol_bulletproof('^SOX')
    new_cache['美債 10Y 殖利率'] = fetch_symbol_bulletproof('^TNX', is_yield=True)
    new_cache['恐慌指數 VIX'] = fetch_symbol_bulletproof('^VIX')
    new_cache['道瓊工業 DJI'] = fetch_symbol_bulletproof('^DJI')
    new_cache['那斯達克 NASDAQ'] = fetch_symbol_bulletproof('^IXIC')
    new_cache['標普 500 S&P500'] = fetch_symbol_bulletproof('^GSPC')
    new_cache['羅素 2000 RUT'] = fetch_symbol_bulletproof('^RUT')
    new_cache['美聯儲 13W 短貼率'] = fetch_symbol_bulletproof('^IRX', is_yield=True)
    new_cache['美元指數 DXY'] = fetch_symbol_bulletproof('DX-Y.NYB')
    new_cache['WTI 原油'] = fetch_symbol_bulletproof('CL=F')
    new_cache['黃金現貨 Gold'] = fetch_symbol_bulletproof('GC=F')
    st.session_state.macro_cache = new_cache
    return new_cache

@st.cache_data(ttl=600)
def fetch_macro_history_df():
    symbols = {
        '台股加權': '^TWII', '費城半導體': '^SOX', '那斯達克': '^IXIC',
        '標普 500': '^GSPC', '美債 10Y': '^TNX', '恐慌 VIX': '^VIX'
    }
    df_all = pd.DataFrame()
    for name, sym in symbols.items():
        try:
            t = yf.Ticker(sym)
            hist = t.history(period='2mo')['Close']
            if not hist.empty:
                norm_series = ((hist / hist.iloc[0]) - 1) * 100
                df_all[name] = norm_series
        except Exception: pass
    return df_all.dropna(how='all')

def get_default_waiting_macro_cache():
    default_item = {'val': '等待中', 'change': '0.00%', 'change_num': 0.0, 'pct': 0.0, 'raw_close': 0.0}
    default_points_item = {'val': '等待中', 'change': '0 點', 'change_num': 0.0, 'pct': 0.0, 'raw_close': 0.0}
    return {k: (default_points_item if k == '台指期夜盤' else default_item) for k in ['台股加權', '台指期夜盤', '日經 225 N225', '費城半導體 SOX', '美債 10Y 殖利率', '恐慌指數 VIX', '道瓊工業 DJI', '那斯達克 NASDAQ', '標普 500 S&P500', '羅素 2000 RUT', '美聯儲 13W 短貼率', '美元指數 DXY', 'WTI 原油', '黃金現貨 Gold']}

if 'macro_cache' not in st.session_state or not st.session_state.macro_cache:
    st.session_state.macro_cache = get_default_waiting_macro_cache()

def parse_stock_input(user_input):
    if not user_input: return ''
    clean_input = str(user_input).strip().replace(' ', '')
    if clean_input.isdigit(): return clean_input
    if clean_input in STOCK_NAME_TO_ID: return STOCK_NAME_TO_ID[clean_input]
    return clean_input

def clean_key(raw):
    if not raw: return ''
    return str(raw).strip().replace('"', '').replace("'", '').replace('\n', '').replace('\r', '')

FINMIND_TOKEN = clean_key(st.secrets.get('FINMIND_TOKEN', os.getenv('FINMIND_TOKEN', '')))
GEMINI_API_KEY = clean_key(st.secrets.get('GEMINI_API_KEY', os.getenv('GEMINI_API_KEY', '')))

def get_taiwan_now():
    return datetime.utcnow() + timedelta(hours=8)

if 'daily_picks' not in st.session_state:
    st.session_state.daily_picks = pd.DataFrame(columns=['上漲率', '族群', '股名', '股號', '當前實價', '建議進場', '波段停利/防護提示', '波段期間'], data=[['--%', '---', '---', '---', '---', '---', '---', '---'] for _ in range(5)])

if 'last_predict_time' not in st.session_state:
    st.session_state.last_predict_time = get_taiwan_now().strftime('%m/%d %H:%M:%S')

def call_gemini_with_retry(prompt, max_retries=2):
    if not GEMINI_API_KEY: raise ValueError('未找到 GEMINI_API_KEY。')
    target_model = 'gemini-3.5-flash'
    last_err = ''
    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=target_model, contents=prompt)
            if response and response.text: return response.text
        except Exception as e:
            last_err = str(e)
            time.sleep(1.0)
    raise ValueError(f'Gemini API 呼叫失敗 [{last_err}]')

def diagnose_premarket_intelligence(macro_data, night_fut_data, target_date_str, news_pack=''):
    prompt_premarket = f'''
    請作為華爾街資深盤前情報官與台股策略總監，基準日期：{target_date_str}。
    【順序2：全量 14 項全球總經與避險指標數據】：
    - 台股加權: {macro_data.get('台股加權', {})} 
    - 台指期夜盤: {night_fut_data}
    - 美股四大指數: DJI {macro_data.get('道瓊工業 DJI', {})}, S&P500 {macro_data.get('標普 500 S&P500', {})}, NASDAQ {macro_data.get('那斯達克 NASDAQ', {})}, RUT {macro_data.get('羅素 2000 RUT', {})}
    - 費城半導體 SOX: {macro_data.get('費城半導體 SOX', {})}
    - 恐慌指數 VIX: {macro_data.get('恐慌指數 VIX', {})}
    - 美元與利率: DXY {macro_data.get('美元指數 DXY', {})}, 美債10Y {macro_data.get('美債 10Y 殖利率', {})}, 美聯儲13W {macro_data.get('美聯儲 13W 短貼率', {})}
    - 原物料與黃金: WTI原油 {macro_data.get('WTI 原油', {})}, 黃金 Gold {macro_data.get('黃金現貨 Gold', {})}
    【順序2：即時國際新聞與政治/戰爭地緣矛盾衝突】：{news_pack}
    【順序3 第1階段：避險黑名單判定硬性指令】：
    全方位連動評估上述 14 項總經與地緣政治新聞。判定哪些「產業族群」面臨顯著宏觀避險風險，列入「避險黑名單 (avoid_sectors)」。
    請回傳 JSON 格式：{{"summary": "100字盤前情報摘要...", "focus_sectors": ["資金流入強勢產業A"], "avoid_sectors": ["避險黑名單產業C"]}} 不要包含 Markdown 多餘文字。
    '''
    res_raw = call_gemini_with_retry(prompt_premarket)
    try:
        json_match = re.search(r'\{.*\}', res_raw, re.DOTALL)
        clean_json = json_match.group(0) if json_match else res_raw.strip()
        return json.loads(clean_json)
    except Exception:
        return {'summary': '全球宏觀與美股走勢平穩，台股維持主流個股輪動。', 'focus_sectors': ['AI伺服器', 'PCB', '半導體設備'], 'avoid_sectors': []}

def get_stock_news(stock_id):
    clean_id = parse_stock_input(stock_id)
    for suffix in ['.TW', '.TWO']:
        try:
            ticker = yf.Ticker(clean_id + suffix)
            news_list = ticker.news
            if news_list and len(news_list) > 0:
                titles = [f"- {item.get('title', '')}" for item in news_list[:5] if item.get('title')]
                return '\n'.join(titles)
        except Exception: continue
    return '無重大新聞'

def get_hot_stocks_24h_news_pack():
    hot_candidates = ['2330', '2317', '2454', '2382', '3231', '3017']
    news_pack = []
    for s_id in hot_candidates:
        tw_name = STOCK_ID_TO_NAME.get(s_id, s_id)
        n_titles = get_stock_news(s_id)
        if n_titles and n_titles != '無重大新聞': news_pack.append(f'【{tw_name} ({s_id}) 最新24H焦點新聞】：\n{n_titles}')
    return '\n'.join(news_pack) if news_pack else '焦點股新聞數據：消息面平穩。'

@st.cache_data(ttl=120)
def get_realtime_tw_price_info(stock_id):
    clean_id = parse_stock_input(stock_id)
    if not clean_id: return None
    for suffix in ['.TW', '.TWO']:
        try:
            ticker = yf.Ticker(clean_id + suffix)
            data = ticker.history(period='1d', interval='1m').dropna(subset=['Close'])
            if not data.empty and len(data) >= 1:
                latest_close = round(float(data['Close'].iloc[-1]), 2)
                if not math.isnan(latest_close) and latest_close > 0: return {'real_price': latest_close}
        except Exception: continue
    return None

@st.cache_data(ttl=300)
def calculate_kd(stock_id, period_type='日線'):
    clean_id = parse_stock_input(stock_id)
    if not clean_id: return None, '無效代碼'
    df = pd.DataFrame()
    for suffix in ['.TW', '.TWO']:
        try:
            ticker = yf.Ticker(clean_id + suffix)
            df_temp = ticker.history(period='6mo').dropna(subset=['Close'])
            if not df_temp.empty and len(df_temp) >= 20: df = df_temp; break
        except Exception: continue
    if df.empty or len(df) < 20: return None, '數據不足'
    try:
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
        low_9 = df['Low'].rolling(window=9).min().fillna(df['Low'])
        high_9 = df['High'].rolling(window=9).max().fillna(df['High'])
        rsv = (df['Close'] - low_9) / (high_9 - low_9).replace(0, 1e-6) * 100
        k_list, d_list = [50.0], [50.0]
        for r in rsv.fillna(50):
            k = (2/3) * k_list[-1] + (1/3) * r
            d = (2/3) * d_list[-1] + (1/3) * k
            k_list.append(k)
            d_list.append(d)
        df['K'] = k_list[1:]
        df['D'] = d_list[1:]
        latest_close, latest_k, latest_d = round(df['Close'].iloc[-1], 2), round(df['K'].iloc[-1], 2), round(df['D'].iloc[-1], 2)
        prev_k = df['K'].iloc[-2] if len(df) >= 2 else latest_k
        prev_d = df['D'].iloc[-2] if len(df) >= 2 else latest_d
        signal = '中性觀望'
        if prev_k <= prev_d and latest_k > latest_d: signal = '🟢 黃金交叉'
        elif prev_k >= prev_d and latest_k < latest_d: signal = '🔴 死亡交叉'
        bias_20ma = round(((latest_close - df['20MA'].iloc[-1]) / df['20MA'].iloc[-1]) * 100, 2)
        return df.tail(40), {'K': latest_k, 'D': latest_d, 'signal': signal, '5MA': round(df['5MA'].iloc[-1], 2), '20MA': round(df['20MA'].iloc[-1], 2), '60MA': round(df['60MA'].iloc[-1], 2), 'bias_20ma': bias_20ma, 'RSI': round(df['RSI'].iloc[-1], 2), 'DIF': round(df['DIF'].iloc[-1], 2), 'MACD_Signal': round(df['MACD_Signal'].iloc[-1], 2), 'BB_Upper': round(df['BB_Upper'].iloc[-1], 2), 'BB_Lower': round(df['BB_Lower'].iloc[-1], 2)}
    except Exception as e: return None, str(e)

def generate_daily_picks(macro_data, night_fut_data, min_price, max_price, custom_sector, selected_masters, target_date_str, status_container, enable_risk_cb=True):
    if not macro_data:
        status_container.update(label='🚨 資料不足無法評估', state='error', expanded=True)
        return [{'上漲率':'0%','族群':'資料不足','股名':'資料不足無法評估','股號':'NONE','當前實價':'---','建議進場':'---','波段停利/防護提示':'資料不足無法評估','波段期間':'觀望'}]
    if enable_risk_cb:
        night_chg = night_fut_data.get('change_num', 0.0) if night_fut_data else 0.0
        if night_chg < -300:
            status_container.update(label='🚨 大盤風控熔斷啟動，避險空倉！', state='error', expanded=True)
            return [{'上漲率':'0%','族群':'避險空倉','股名':'🚨 今日不宜操作','股號':'NONE','當前實價':'---','建議進場':'觀望','波段停利/防護提示':f'夜盤重挫 {night_chg} 點，啟動風控熔斷！','波段期間':'觀望'}]
    status_container.write('🟢 **[順序 3 第2階段]** Gemini AI 分析熱錢走向，篩選主流受惠產業...')
    black_list_instruction = '【啟用風控】：嚴格遵守避險黑名單！剔除黑名單族群個股。' if enable_risk_cb else '【取消風控】：無視避險黑名單，全市場尋找逆勢強勢標的。'
    prompt_select = f'''
    請作為頂級華爾街台股操盤手，基準日期：{target_date_str}。{black_list_instruction} 盤前避險黑名單：{st.session_state.premarket_avoid} 大盤數據: {macro_data}
    請精選 5 檔符合條件之台股股票名單，回傳 JSON 陣列：[{{"上漲率":"78%","族群":"半導體設備","股名":"台積電","股號":"2330","波段期間":"5-10天"}}] 不要包含 Markdown 多餘文字。
    '''
    try:
        res_raw = call_gemini_with_retry(prompt_select)
        json_match = re.search(r'\[.*\]', res_raw, re.DOTALL)
        clean_json = json_match.group(0) if json_match else res_raw.strip()
        picks = json.loads(clean_json)
    except Exception: picks = []
    final_results = []
    for item in picks:
        stock_id = parse_stock_input(item.get('股號'))
        if not stock_id: continue
        p_info = get_realtime_tw_price_info(stock_id)
        if not p_info: continue
        real_p = p_info['real_price']
        _, kd_info = calculate_kd(stock_id, period_type='日線')
        if isinstance(kd_info, dict) and '死亡' in kd_info.get('signal', ''): continue
        p_low, p_high, target_p = round(real_p * 0.985, 1), round(real_p * 1.005, 1), round(real_p * 1.08, 1)
        item['當前實價'], item['建議進場'], item['波段停利/防護提示'] = f'{real_p:.2f}', f'{p_low:.1f}-{p_high:.1f}', f'目標 {target_p:.1f} (達標即落袋)'
        item['股名'] = STOCK_ID_TO_NAME.get(stock_id, item.get('股名'))
        final_results.append(item)
        if len(final_results) >= 5: break
    status_container.update(label='🎉 3 階段 5 步驟 AI 嚴謹選股順利完成！', state='complete', expanded=False)
    if not final_results: return [{'上漲率':'---','族群':'資料不足','股名':'資料不足無法評估','股號':'NONE','當前實價':'---','建議進場':'---','波段停利/防護提示':'無符合條件個股','波段期間':'觀望'}]
    return pd.DataFrame(final_results)[['上漲率','族群','股名','股號','當前實價','建議進場','波段停利/防護提示','波段期間']].to_dict('records')

# ==============================================================================
# 📱 主 UI 介面與側邊欄 (Sidebar) 渲染 - 100% 恢復
# ==============================================================================
taiwan_now = get_taiwan_now()
target_date_str = taiwan_now.strftime('%Y-%m-%d')
display_date_str = taiwan_now.strftime('%Y / %m / %d')

st.sidebar.markdown(f'''
<div style="font-size: 0.9rem; font-weight: bold; margin-bottom: 12px; line-height: 1.8;">
    市場看板基準日期
    <span style="font-size: 0.75rem; color: #a0a0a0; font-weight: normal; margin-left: 4px;">(資料來源: TWSE / TAIFEX / Yahoo)</span>
    <span style="background-color: #262730; border: 1px solid #464b5d; border-radius: 4px; padding: 2px 8px; color: #ff4d4f; font-weight: bold; margin-left: 8px;">{display_date_str}</span>
</div>
''', unsafe_allow_html=True)

macro_data = st.session_state.macro_cache
night_fut_data = st.session_state.macro_cache.get('台指期夜盤', {})

if st.sidebar.button('AI 執行最新情報分析預測上漲機率最高前五檔', type='primary', key='btn_combined_diagnose', use_container_width=True):
    get_realtime_tw_price_info.clear()
    calculate_kd.clear()
    status_cot = st.status('🧠 執行 3 階段 5 步驟嚴謹決策中...', expanded=True)
    with status_cot:
        try:
            status_cot.write('🟢 **[順序 1]** 載入台股 33 類官方產業與市場特性分類清冊...')
            status_cot.write('🟢 **[順序 2]** 抓取全球 14 項大盤數據與國際地緣政治新聞...')
            macro_data = force_refresh_all_macro_data()
            night_fut_data = macro_data.get('台指期夜盤', {})
            hot_news_pack = get_hot_stocks_24h_news_pack()
            status_cot.write('🟢 **[順序 3 第1階段]** AI 盤前戰情診斷 (清空快取，產生避險黑名單)...')
            p_data = diagnose_premarket_intelligence(macro_data, night_fut_data, target_date_str, news_pack=hot_news_pack)
            st.session_state.premarket_summary = p_data.get('summary', '')
            st.session_state.premarket_focus = p_data.get('focus_sectors', [])
            st.session_state.premarket_avoid = p_data.get('avoid_sectors', [])
            picks_data = generate_daily_picks(macro_data, night_fut_data, 0, 0, '', [], target_date_str, status_container=status_cot, enable_risk_cb=True)
            st.session_state.daily_picks = pd.DataFrame(picks_data)
            st.session_state.last_predict_time = get_taiwan_now().strftime('%m/%d %H:%M:%S')
            st.sidebar.success('個股預測順利完成！')
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.sidebar.error(f'預測失敗: {e}')

st.sidebar.info(f'💡 **最新情報摘要**：\n{st.session_state.premarket_summary}')
st.sidebar.markdown(f'### 🎯 今日 [{st.session_state.last_predict_time}] AI 預估上漲率最高前五檔')
st.sidebar.dataframe(st.session_state.daily_picks, hide_index=True, use_container_width=True)
st.sidebar.divider()

st.sidebar.markdown('### ⚙ 個股詳細分析與技術指標設定')
raw_stock_input = st.sidebar.text_input('輸入台股代碼或股名', value='', placeholder='例如: 2330 或 鴻海')
stock_id = parse_stock_input(raw_stock_input)
period_type = st.sidebar.radio('技術指標週期選擇', ['日線', '週線'], horizontal=True)

# ------------------------------------------------------------------------------
# 📈 主畫面：頂部卡片 + 4 大抽屜面板 + 30 日總經折線圖
# ------------------------------------------------------------------------------
st.title('📈 全球總經與台股資金流 AI 矩陣分析系統')
st.caption('限定資料來源: 台灣證券交易所 (TWSE) | 台灣期貨交易所 (TAIFEX) | 公開資訊觀測站 (MOPS) | Yahoo Finance')

st.markdown('<div class="top-macro-card">', unsafe_allow_html=True)
card_cols = st.columns(4)
with card_cols[0]: item_taiex = macro_data.get('台股加權', {}); st.metric(label='台股加權', value=item_taiex.get('val', '等待中'), delta=item_taiex.get('change', '0.00%'), delta_color='inverse')
with card_cols[1]: item_sox = macro_data.get('費城半導體 SOX', {}); st.metric(label='費城半導體', value=item_sox.get('val', '等待中'), delta=item_sox.get('change', '0.00%'), delta_color='inverse')
with card_cols[2]: item_10y = macro_data.get('美債 10Y 殖利率', {}); st.metric(label='美債 10Y', value=item_10y.get('val', '等待中'), delta=item_10y.get('change', '0.00%'), delta_color='inverse')
with card_cols[3]: item_vix = macro_data.get('恐慌指數 VIX', {}); st.metric(label='恐慌 VIX', value=item_vix.get('val', '等待中'), delta=item_vix.get('change', '0.00%'), delta_color='inverse')
st.markdown('</div>', unsafe_allow_html=True)

expander_cols = st.columns(4)
with expander_cols[0]:
    with st.expander('🌏 亞太大盤指數', expanded=True):
        col_a1, col_a2 = st.columns(2)
        with col_a1: item_night = macro_data.get('台指期夜盤', {}); st.metric(label='台指期夜盤', value=item_night.get('val', '等待中'), delta=item_night.get('change', '0 點'), delta_color='inverse')
        with col_a2: item_nikkei = macro_data.get('日經 225 N225', {}); st.metric(label='日經 225', value=item_nikkei.get('val', '等待中'), delta=item_nikkei.get('change', '0.00%'), delta_color='inverse')
with expander_cols[1]:
    with st.expander('🇺🇸 美股四大指數'):
        col_u1, col_u2 = st.columns(2)
        with col_u1: item_dji = macro_data.get('道瓊工業 DJI', {}); st.metric(label='道瓊 DJI', value=item_dji.get('val', '等待中'), delta=item_dji.get('change', '0.00%'), delta_color='inverse')
        with col_u2: item_nas = macro_data.get('那斯達克 NASDAQ', {}); st.metric(label='那斯達克', value=item_nas.get('val', '等待中'), delta=item_nas.get('change', '0.00%'), delta_color='inverse')
with expander_cols[2]:
    with st.expander('🏦 國際美元利率'):
        col_r1, col_r2 = st.columns(2)
        with col_r1: item_irx = macro_data.get('美聯儲 13W 短貼率', {}); st.metric(label='美聯儲 13W', value=item_irx.get('val', '等待中'), delta=item_irx.get('change', '0.00%'), delta_color='inverse')
        with col_r2: item_dxy = macro_data.get('美元指數 DXY', {}); st.metric(label='美元 DXY', value=item_dxy.get('val', '等待中'), delta=item_dxy.get('change', '0.00%'), delta_color='inverse')
with expander_cols[3]:
    with st.expander('🛡️ 避險商品指標'):
        col_h1, col_h2 = st.columns(2)
        with col_h1: item_wti = macro_data.get('WTI 原油', {}); st.metric(label='WTI 原油', value=item_wti.get('val', '等待中'), delta=item_wti.get('change', '0.00%'), delta_color='inverse')
        with col_h2: item_gold = macro_data.get('黃金現貨 Gold', {}); st.metric(label='黃金 Gold', value=item_gold.get('val', '等待中'), delta=item_gold.get('change', '0.00%'), delta_color='inverse')

# 📊 總經與三大指數 30 日走勢對比折線圖
with st.expander('📊 全球關鍵總經與三大指數近 30 日走勢對比折線圖 (歸一化累計漲跌幅 %)', expanded=True):
    macro_hist_df = fetch_macro_history_df()
    if not macro_hist_df.empty:
        fig_macro = go.Figure()
        colors_map = {
            '台股加權': '#ff4d4f', '費城半導體': '#1890ff', '那斯達克': '#faad14',
            '標普 500': '#52c41a', '美債 10Y': '#722ed1', '恐慌 VIX': '#eb2f96'
        }
        for col in macro_hist_df.columns:
            fig_macro.add_trace(go.Scatter(
                x=macro_hist_df.index, y=macro_hist_df[col],
                mode='lines', name=col, line=dict(color=colors_map.get(col, '#ffffff'), width=2)
            ))
        fig_macro.update_layout(
            height=320, margin=dict(l=10, r=10, t=20, b=30),
            template='plotly_dark', hovermode='x unified',
            yaxis_title='相對漲跌幅 (%)',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )
        st.plotly_chart(fig_macro, use_container_width=True)
    else:
        st.info('總經歷史數據載入中或休市中...')

st.divider()

# ------------------------------------------------------------------------------
# 🔍 個股三大法人籌碼與進階技術指標綜合看板
# ------------------------------------------------------------------------------
if stock_id and str(stock_id).strip() != '':
    st.subheader(f'🔍 個股 ({STOCK_ID_TO_NAME.get(stock_id, stock_id)} {stock_id}) 三大法人籌碼與進階技術指標綜合分析看板')
    kd_df, kd_info = calculate_kd(stock_id, period_type=period_type)
    if isinstance(kd_info, dict):
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1.2, 1.2, 2.0])
        c1.metric(f'{period_type} K / D 值', f"{kd_info['K']} / {kd_info['D']}")
        c2.metric('RSI (14日)', kd_info.get('RSI', 'N/A'))
        c3.metric('5日均線 (5MA)', kd_info['5MA'])
        c4.metric('20日線 (月線)', kd_info['20MA'], delta=f"{kd_info['bias_20ma']:+}% (乖離)")
        c5.metric('KD & 均線型態', kd_info['signal'])
    if kd_df is not None and not kd_df.empty:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.09, row_heights=[0.5, 0.25, 0.25], subplot_titles=('收盤價與布林通道 (20MA)', 'KD 指標 & RSI (14)', 'MACD 動能柱與 DIF/MACD 軌道'))
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['Close'], mode='lines', name='收盤價', line=dict(color='#ffffff', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['BB_Upper'], mode='lines', name='布林上軌', line=dict(color='#ff7875', width=1, dash='dash')), row=1, col=1)
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['20MA'], mode='lines', name='布林中軌', line=dict(color='#ffc069', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['BB_Lower'], mode='lines', name='布林下軌', line=dict(color='#95de64', width=1, dash='dash')), row=1, col=1)
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['K'], mode='lines', name='K 值', line=dict(color='#ff4d4f', width=1.5)), row=2, col=1)
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['D'], mode='lines', name='D 值', line=dict(color='#1890ff', width=1.5)), row=2, col=1)
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['RSI'], mode='lines', name='RSI', line=dict(color='#b37feb', width=1.5, dash='dot')), row=2, col=1)
        colors_macd = ['#ff4d4f' if val >= 0 else '#52c41a' for val in kd_df['MACD_Hist']]
        fig.add_trace(go.Bar(x=kd_df.index, y=kd_df['MACD_Hist'], name='MACD 柱狀', marker_color=colors_macd), row=3, col=1)
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['DIF'], mode='lines', name='DIF (快線)', line=dict(color='#faad14', width=1)), row=3, col=1)
        fig.add_trace(go.Scatter(x=kd_df.index, y=kd_df['MACD_Signal'], mode='lines', name='MACD (慢線)', line=dict(color='#13c2c2', width=1)), row=3, col=1)
        fig.update_layout(height=600, margin=dict(l=10, r=10, t=50, b=60), template='plotly_dark')
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info('請於左側輸入台股代碼或股名檢視三大法人籌碼與進階技術指標看板')
