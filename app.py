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

st.set_page_config(page_title='全球總經與台股資金流 AI 矩陣分析系統', layout='wide')

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
[data-testid='stMetricDelta']:has(svg[data-testid='stMetricDeltaIcon-Down']) { color: #52c41a !important; }
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
            elif is_points: fmt_val, chg_str = f'{int(p_val):,}', f'{chg_str:+.0f} 點'
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
                # 歸一化百分比走勢 (以第一天基期為 0%)
                norm_series = ((hist / hist.iloc[0]) - 1) * 100
                df_all[name] = norm_series
        except Exception: pass
    return df_all.dropna(how='all')
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
st.title('📈 全球總經與台股資金流 AI 矩陣分析系統')
taiwan_now = get_taiwan_now()
target_date_str, display_date_str = taiwan_now.strftime('%Y-%m-%d'), taiwan_now.strftime('%Y / %m / %d')
st.sidebar.markdown(f'''<div style="font-size: 0.9rem; font-weight: bold; margin-bottom: 12px;">市場看板基準日期 <span style="color: #ff4d4f;">{display_date_str}</span></div>''', unsafe_allow_html=True)
macro_data = st.session_state.macro_cache or force_refresh_all_macro_data()
# ------------------------------------------------------------------------------
# 📈 頂部卡片 + 4 大抽屜面板
# ------------------------------------------------------------------------------
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
# ------------------------------------------------------------------------------
# 📊 恢復：全球關鍵總經與三大指數 30 日連動走勢折線圖看板
# ------------------------------------------------------------------------------
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
st.info('請於左側輸入台股代碼或股名檢視三大法人籌碼與進階技術指標看板')
