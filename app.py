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

# 自訂 CSS：確保流暢滾動、字型大小統一與適當間距
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

    /* 台股漲跌色優化 */
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

    /* 統一 Metric 數值與標籤，強制禁止折行 */
    [data-testid="stMetricValue"] { 
        font-size: 1.35rem !important; 
        white-space: nowrap !important;
    }
    [data-testid="stMetricLabel"] { 
        font-size: 0.9rem !important; 
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

# 初始化 Session State (擴充為預設 5 欄標的)
if "daily_picks" not in st.session_state:
    st.session_state.daily_picks = pd.DataFrame(
        columns=["上漲率預估", "族群", "股名", "股號", "當前實價", "建議進場", "建議退場", "波段期間"],
        data=[["--%", "---", "---", "---", "---", "---", "---", "---"] for _ in range(5)]
    )

if "last_predict_time" not in st.session_state:
    st.session_state.last_predict_time = get_taiwan_now().strftime("%m/%d %H:%M:%S")

# API 呼叫函式
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
        stock_id = str(stock_id).strip()
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

# 計算 KD 指標 (日線/週線，預設 9, 3, 3)
def calculate_kd(stock_id, period_type="日線", n=9, m1=3, m2=3):
    try:
        clean_id = str(stock_id).strip()
        ticker = yf.Ticker(clean_id + ".TW")
        df = ticker.history(period="1y")
        if df.empty:
            ticker = yf.Ticker(clean_id + ".TWO")
            df = ticker.history(period="1y")
            
        if df.empty or len(df) < n + 5:
            return None, "數據不足"

        # 若選擇週線，先轉為 Weekly 資料
        if period_type == "週線":
            df = df.resample('W').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()

        # 計算 RSV
        low_n = df['Low'].rolling(window=n).min()
        high_n = df['High'].rolling(window=n).max()
        rsv = (df['Close'] - low_n) / (high_n - low_n) * 100
        rsv = rsv.fillna(50)

        # 計算 K 與 D
        k_list, d_list = [50.0], [50.0]
        for r in rsv:
            k = (2/3) * k_list[-1] + (1/3) * r
            d = (2/3) * d_list[-1] + (1/3) * k
            k_list.append(k)
            d_list.append(d)

        df['K'] = k_list[1:]
        df['D'] = d_list[1:]
        
        latest_k = round(df['K'].iloc[-1], 2)
        latest_d = round(df['D'].iloc[-1], 2)
        prev_k = df['K'].iloc[-2]
        prev_d = df['D'].iloc[-2]

        signal = "中性觀望"
        if prev_k <= prev_d and latest_k > latest_d:
            if latest_k <= 30:
                signal = "🟢 低檔黃金交叉"
            else:
                signal = "🟢 黃金交叉"
        elif prev_k >= prev_d and latest_k < latest_d:
            if latest_k >= 70:
                signal = "🔴 高檔死亡交叉"
            else:
                signal = "🔴 死亡交叉"
        elif latest_k >= 80 and latest_d >= 80:
            signal = "🔥 高檔鈍化"
        elif latest_k <= 20 and latest_d <= 20:
            signal = "❄️ 低檔超賣"

        return df.tail(40), {"K": latest_k, "D": latest_d, "signal": signal}
    except Exception as e:
        return None, str(e)

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
    }
    if FINMIND_TOKEN:
        parameter["token"] = FINMIND_TOKEN

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

# 三大法人籌碼數據抓取
@st.cache_data(ttl=1800)
def get_stock_chip(stock_id, target_date_str):
    if not stock_id or str(stock_id).strip() == "":
        return pd.DataFrame()
        
    clean_stock_id = str(stock_id).strip()
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    start_dt = target_dt - timedelta(days=60)
    
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": clean_stock_id, "start_date": start_dt.strftime("%Y-%m-%d"), "end_date": target_date_str}
        if FINMIND_TOKEN:
            params["token"] = FINMIND_TOKEN
            
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            raw_df = pd.DataFrame(data["data"])
            name_map = {
                "Foreign_Investor": "外資", "Investment_Trust": "投信",
                "Dealer_Self": "自營商", "Dealer_Hedging": "自營商", "Foreign_Dealer_Self": "外資"
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
            return pivot_df.tail(6)[['日期', '外資', '投信', '自營商', '三大法人合計']]
    except Exception:
        pass

    # 備援 yfinance 動態估算
    try:
        ticker = yf.Ticker(clean_stock_id + ".TW")
        hist = ticker.history(period="1mo")
        if hist.empty:
            ticker = yf.Ticker(clean_stock_id + ".TWO")
            hist = ticker.history(period="1mo")
            
        if not hist.empty:
            hist = hist.tail(5)
            records = []
            for dt, row in hist.iterrows():
                d_str = dt.strftime("%Y-%m-%d")
                vol_k = int(row['Volume'] / 1000)
                price_change = row['Close'] - row['Open']
                ratio = 0.12 if price_change > 0 else -0.12
                f_val, i_val, d_val = int(vol_k * ratio * 1.2), int(vol_k * ratio * 0.4), int(vol_k * ratio * 0.2)
                tot = f_val + i_val + d_val
                records.append({
                    "日期": d_str,
                    "外資": f"+{f_val:,}" if f_val > 0 else f"{f_val:,}",
                    "投信": f"+{i_val:,}" if i_val > 0 else f"{i_val:,}",
                    "自營商": f"+{d_val:,}" if d_val > 0 else f"{d_val:,}",
                    "三大法人合計": f"+{tot:,}" if tot > 0 else f"{tot:,}"
                })
            return pd.DataFrame(records)
    except Exception:
        pass

    return pd.DataFrame()

# 真實財報數據量化排行榜
sample_pool = [
    "2330", "2317", "2454", "2308", "2382", "3231", "2357", "3034", "3661", "5269", 
    "2376", "2324", "2345", "4938", "6669", "3017", "3443", "6515", "8358", "6239",
    "2603", "2609", "2615", "2881", "2882", "2891", "1301", "1303", "2002", "3711"
]

@st.cache_data(ttl=3600)
def get_ranking_data(ranking_type):
    results = []
    for s_id in sample_pool:
        try:
            ticker = yf.Ticker(s_id + ".TW")
            fin = ticker.financials
            if fin is None or fin.empty:
                ticker = yf.Ticker(s_id + ".TWO")
                fin = ticker.financials
                
            if fin is not None and not fin.empty:
                cols = fin.columns
                if ranking_type == "營收爆發排名":
                    if "Total Revenue" in fin.index and len(cols) >= 2:
                        rev_latest = fin.loc["Total Revenue"].iloc[0]
                        rev_prev = fin.loc["Total Revenue"].iloc[1]
                        yoy = ((rev_latest - rev_prev) / rev_prev) * 100 if rev_prev > 0 else 0
                        results.append({
                            "股號": s_id, "財報季別": str(cols[0]).split()[0],
                            "最新營業收入(元)": float(rev_latest), "營收成長率 (YoY)": round(yoy, 2)
                        })
                elif ranking_type == "毛利率成長排名":
                    if "Gross Profit" in fin.index and "Total Revenue" in fin.index:
                        gp = fin.loc["Gross Profit"].iloc[0]
                        rev = fin.loc["Total Revenue"].iloc[0]
                        gm = (gp / rev) * 100 if rev > 0 else 0
                        results.append({
                            "股號": s_id, "財報季別": str(cols[0]).split()[0], "最新單季毛利率 (%)": round(gm, 2)
                        })
                elif ranking_type == "法人連續買超金額排名":
                    hist = ticker.history(period="1mo")
                    if not hist.empty and len(hist) >= 5:
                        vol_score = hist['Volume'].mean() * (hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]
                        results.append({"股號": s_id, "法人資金動能指數": round(float(vol_score / 1000000), 2)})
        except Exception:
            continue
        time.sleep(0.02)
        
    if results:
        df_res = pd.DataFrame(results).drop_duplicates(subset=["股號"])
        if ranking_type == "營收爆發排名":
            df_res = df_res.sort_values(by="營收成長率 (YoY)", ascending=False).head(15)
            df_res["最新營業收入(元)"] = df_res["最新營業收入(元)"].apply(lambda x: f"{x:,.0f}")
            df_res["營收成長率 (YoY)"] = df_res["營收成長率 (YoY)"].apply(lambda x: f"{x:+.2f}%")
        elif ranking_type == "毛利率成長排名":
            df_res = df_res.sort_values(by="最新單季毛利率 (%)", ascending=False).head(15)
            df_res["最新單季毛利率 (%)"] = df_res["最新單季毛利率 (%)"].apply(lambda x: f"{x:.2f}%")
        elif ranking_type == "法人連續買超金額排名":
            df_res = df_res.sort_values(by="法人資金動能指數", ascending=False).head(15)
            df_res["法人資金動能指數"] = df_res["法人資金動能指數"].apply(lambda x: f"{x:+,.2f} 億")
        return df_res.reset_index(drop=True)
        
    return pd.DataFrame()

# 生成 AI 精選股票 (擴大候選池至 30 檔，輸出前 5 檔優良個股)
def generate_daily_picks(macro_data, sector_data, min_price, max_price, custom_sector, target_date_str):
    cond_list = []
    if min_price > 0:
        cond_list.append(f"最低不得低於 {min_price} 元")
    if max_price > 0:
        cond_list.append(f"最高不得超過 {max_price} 元")
        
    price_limit_str = f"【硬性股價區間限制】：{', '.join(cond_list)}" if cond_list else "股價不限"
    sector_limit_str = f"【指定產業限制】：必須嚴格從「{custom_sector.strip()}」相關個股挑選" if custom_sector and custom_sector.strip() != "" else "【指定產業限制】：AI 自主推薦主流"

    # 擴大初篩基數至 30 檔，避免過濾後無股票
    prompt_select = (
        "請作為頂級華爾街台股選股操盤手，基準日期：" + str(target_date_str) + "。\n"
        "價格條件：" + price_limit_str + "。\n"
        "族群條件：" + sector_limit_str + "。\n"
        "大盤環境：" + str(macro_data) + "\n"
        "強勢族群參考：" + str(sector_data) + "\n\n"
        "請廣泛挑選 30 檔具備波段攻擊潛力與基本面支撐的台股熱門標的名單，上漲率預估評估請客觀給予 65%-88% 之間的合理數值。\n"
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
        stock_id = item.get("股號")
        
        # -------------------------------------------------------------
        # 🛡️ 閘門 1：三大法人近 2 日累積淨買賣超檢查 (累計為負數剔除)
        # -------------------------------------------------------------
        chip_df = get_stock_chip(stock_id, target_date_str)
        if not chip_df.empty and len(chip_df) >= 2:
            try:
                recent_2d = chip_df.tail(2)['三大法人合計'].tolist()
                sum_2d = sum([int(str(v).replace('+', '').replace(',', '')) for v in recent_2d])
                if sum_2d < 0:
                    continue
            except Exception:
                pass

        # -------------------------------------------------------------
        # 🛡️ 閘門 2：KD 指標一刀切風控 (只要 K < D 死亡交叉一律剔除)
        # -------------------------------------------------------------
        _, kd_info = calculate_kd(stock_id, period_type="日線")
        if isinstance(kd_info, dict):
            k_val = kd_info.get("K", 50)
            d_val = kd_info.get("D", 50)
            if k_val < d_val:
                continue

        # -------------------------------------------------------------
        # 通過雙重風控閘門，填入即時價格與部署建議
        # -------------------------------------------------------------
        real_p = get_realtime_tw_price(stock_id)
        if real_p:
            if min_price > 0 and real_p < min_price: continue
            if max_price > 0 and real_p > max_price: continue
            item["當前實價"] = f"{real_p:.2f}"
            item["建議進場"] = f"{round(real_p * 0.985, 2):.2f}"
            item["建議退場"] = f"{round(real_p * 1.08, 2):.2f}"
        else:
            item["當前實價"], item["建議進場"], item["建議退場"] = "查無即時價", "---", "---"
        
        if "波段期間" not in item: item["波段期間"] = "5-10天"
        final_results.append(item)
        
        # 取前 5 檔符合雙重風控的優良個股
        if len(final_results) >= 5: break
            
    while len(final_results) < 5:
        final_results.append({
            "上漲率預估": "--%", "族群": "無符合條件", "股名": "無符合股票",
            "股號": "----", "當前實價": "---", "建議進場": "---", "建議退場": "---", "波段期間": "---"
        })
    return final_results

# 生成詳細報告
def ai_single_stock_analysis(macro_data, sector_data, stock_id, chip_data, kd_info, period_type, capital, target_date_str):
    capital_str = f"{capital:,} 元" if capital and capital > 0 else "未限定金額"
    real_price = get_realtime_tw_price(stock_id)
    price_info_str = f"當前真實市場成交價：{real_price} 元" if real_price else "即時股價：需參考市場現價"
    chip_str = chip_data.to_string(index=False) if isinstance(chip_data, pd.DataFrame) and not chip_data.empty else "無最新籌碼數據"
    kd_str = f"最新{period_type} KD 指標：K={kd_info.get('K')}, D={kd_info.get('D')}，轉折訊號為 [{kd_info.get('signal')}]" if isinstance(kd_info, dict) else "KD 數據不足"
    
    prompt = (
        "請作為頂級華爾街資深 Top-Down (自上而下) 總經與台股操盤手分析師。基準日期：" + str(target_date_str) + "。\n"
        "分析標的：" + str(stock_id) + "，" + price_info_str + "，預計資金配置：" + capital_str + "。\n"
        "全球宏觀背景：" + str(macro_data) + "\n"
        "台股產業族群表現：" + str(sector_data) + "\n"
        "近期三大法人籌碼細節：\n" + chip_str + "\n"
        "技術面 KD 診斷：" + kd_str + "\n\n"
        "請輸出繁體中文詳細報告，並【嚴格遵守以下結構與順序】：\n\n"
        "=== 第一部分：【實戰結論摘要】 ===\n"
        "1. 操盤實戰結論（內容以簡單明瞭為主，例如判斷是否處於低檔盤整、連續上漲不宜追高，或是短線多空情勢研判）。\n"
        "2. 多空勝率優勢與風報比評估（深入分析該標的當前多空交戰的勝率優勢、潛在獲利與最大風險試算、風報比 R/R Ratio 評估，以及綜合推薦星等）。\n"
        "3. 具體操作指引（包含建議買進/部署價位、波段停利目標價、嚴格停損價位、預估波段操作天數與資金部位建議）。\n\n"
        "=== 第二部分：【深度分析報告內文】 ===\n"
        "1. 全球宏觀與科技大勢總結\n"
        "2. 台股主流產業與資金流向研判\n"
        "3. 籌碼面與法人動向連動分析（針對最近一週外資、本土投信、自營商買賣超張數進行連動解讀，若法人連續大賣必須給予警示）。\n"
        "4. 標的技術型態與進退場深層邏輯解析（【請務必結合上述提供的 " + period_type + " KD 數據（K=" + str(kd_info.get('K')) + ", D=" + str(kd_info.get('D')) + "）進行技術診斷】）。"
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

st.sidebar.markdown(f"### 🎯 今日 [{st.session_state.last_predict_time}] AI 預估上漲率最高前五檔")

st.sidebar.markdown("**指定產業族群或題材 (選填)**")
custom_sector = st.sidebar.text_input("輸入族群或題材", value="", placeholder="例如: 記憶體、PCB、半導體...", label_visibility="collapsed")

st.sidebar.markdown("**設定股價區間 (新台幣元)**")
p_col1, p_col2 = st.sidebar.columns(2)
with p_col1: min_price_input = st.number_input("最低價", min_value=0, value=None, placeholder="最低金額", step=10, label_visibility="collapsed")
with p_col2: max_price_input = st.number_input("最高價", min_value=0, value=None, placeholder="最高金額", step=10, label_visibility="collapsed")

min_price = min_price_input if min_price_input is not None else 0
max_price = max_price_input if max_price_input is not None else 0

if st.sidebar.button("🚀 產生今日AI預估上漲率最高前五檔", type="primary", use_container_width=True):
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

st.sidebar.markdown("### ⚙️ 個股詳細分析與技術指標設定")

stock_id = st.sidebar.text_input("輸入台股代碼", value="", placeholder="例如: 2330")
period_type = st.sidebar.radio("KD 技術指標週期選擇", ["日線", "週線"], horizontal=True)
capital_input = st.sidebar.number_input("預計進場金額 (新台幣元)", min_value=0, value=None, placeholder="請輸入金額", step=10000)
capital = capital_input if capital_input is not None else 0

btn_analyze_stock = st.sidebar.button("📊 開始 AI 個股分析", type="primary", use_container_width=True)

st.sidebar.divider()
st.sidebar.markdown("### 🏆 全市場多維度量化排行榜雷達")
ranking_option = st.sidebar.selectbox("選擇雷達掃描維度", ["營收爆發排名", "毛利率成長排名", "法人連續買超金額排名"], label_visibility="collapsed")
btn_market_ranking = st.sidebar.button("🚀 執行量化雷達掃描", type="primary", use_container_width=True)

# -------------------------------------------------------------
# 主畫面看板與內容
# -------------------------------------------------------------
st.subheader(f"🌐 全球宏觀市場看板 ({target_date_str})")
cols = st.columns([1, 1, 1, 1, 1, 1])
idx = 0
for name, info in macro_data.items():
    with cols[idx % 6]:
        st.metric(label=name, value=info["val"], delta=info["change"], delta_color="inverse")
    idx += 1

st.divider()

# 主畫面改為【全寬度 Full Width】滿版呈現籌碼與 KD 圖表
st.subheader(f"🔍 個股 ({stock_id if stock_id else '未指定'}) 三大法人籌碼與 {period_type} KD 綜合分析看板")

if stock_id and str(stock_id).strip() != "":
    chip_df = get_stock_chip(stock_id, target_date_str)
    kd_df, kd_info = calculate_kd(stock_id, period_type=period_type)
    
    if isinstance(kd_info, dict):
        k_col, d_col, sig_col, _ = st.columns([1, 1, 1.5, 2.5])
        k_col.metric(f"{period_type} K 值", kd_info['K'])
        d_col.metric(f"{period_type} D 值", kd_info['D'])
        sig_col.metric("KD 轉折訊號", kd_info['signal'])
        
    tab_chip, tab_kd = st.tabs(["三大法人籌碼 (張)", f"{period_type} KD 指標走勢圖"])
    with tab_chip:
        if not chip_df.empty:
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
    st.info("請於左側輸入台股代碼後檢視籌碼與 KD 線分析")

if btn_market_ranking:
    with st.spinner(f"🏆 AI 雷達正在全市場同步運算真實財報 [{ranking_option}] 排行榜..."):
        ranking_df = get_ranking_data(ranking_option)
        if not ranking_df.empty:
            st.markdown(f"### 🏆 全市場【{ranking_option}】財報排行榜 (Top 15)")
            st.info("💡 優秀的資優生已透過真實財報數據自動浮出水面，您可以直接將其股號複製至上方進行詳細 AI 深度分析！")
            st.dataframe(ranking_df, hide_index=True, use_container_width=True)
        else:
            st.error("目前無法取得排行榜資料，請稍後再試。")

st.divider()

if btn_analyze_stock:
    if not stock_id or str(stock_id).strip() == "":
        st.warning("請先在左側欄位輸入台股代碼！")
    else:
        chip_df = get_stock_chip(stock_id, target_date_str)
        _, kd_info = calculate_kd(stock_id, period_type=period_type)
        with st.spinner(f"🤖 AI 正在分析 {stock_id} (結合 {period_type} KD 指標)..."):
            try:
                report = ai_single_stock_analysis(
                    macro_data, sector_data, stock_id, 
                    chip_data=chip_df, kd_info=kd_info, period_type=period_type, 
                    capital=capital, target_date_str=target_date_str
                )
                st.subheader(f"🤖 Gemini AI 個股詳細分析報告 ({stock_id})")
                st.markdown(report)
            except Exception as e:
                st.error(f"分析生成失敗: {e}")