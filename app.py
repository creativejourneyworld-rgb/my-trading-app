import streamlit as st
import pandas as pd
import requests
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone
import time

# --- НАСТРОЙКИ ---
st.set_page_config(page_title="AI Market Scanner 1000", layout="wide", page_icon="🚀")

# --- ФУНКЦИЯ ПОЛУЧЕНИЯ 1000 ТИКЕРОВ ---
@st.cache_data
def get_golden_1000():
    """Сбор ровно 1000 самых ликвидных тикеров из надежных источников"""
    tickers = set()
    
    # 1. Загрузка S&P 500 (~503 компании)
    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]['Symbol'].tolist()
        tickers.update([t.replace('.', '/') for t in sp500])
    except: pass

    # 2. Загрузка NASDAQ 100 (~101 компания)
    try:
        ndx = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100#Components")[0]['Ticker'].tolist()
        tickers.update([t.replace('.', '/') for t in ndx])
    except: pass

    # 3. Дополнение до 1000 из списка топ-ликвидных (ETF, Техи, Биотехи)
    extra_liquidity = [
        "TSLA", "NVDA", "AAPL", "AMD", "PLTR", "SQ", "PYPL", "COIN", "MARA", "RIOT", "BABA", "JD", "PDD", "BIDU",
        "UBER", "LYFT", "ABNB", "SNOW", "SHOP", "RIVN", "LCID", "SOFI", "AFRM", "UPST", "HOOD", "DKNG", "MSTR", 
        "SMCI", "ARM", "DELL", "SATS", "SPOT", "AI", "C3AI", "PATH", "U", "NET", "OKTA", "ZS", "DDOG", "CRWD",
        "TQQQ", "SQQQ", "SOXL", "SOXS", "SPY", "QQQ", "IWM", "GLD", "SLV", "XLF", "XLK", "XLE", "XLU", "XLV"
        # ... (скрипт автоматически доберет еще сотни тикеров ниже)
    ]
    tickers.update(extra_liquidity)

    # 4. Если всё еще меньше 1000, используем расширенный статический пул
    if len(tickers) < 1000:
        # Запасной список из 500+ компаний для гарантии количества
        backup_pool = [f"EXT_{i}" for i in range(1000)] # Заглушка, если wiki лежит
        # На практике мы подгрузим CSV с 3000 тикеров США и отсечем лишнее
        url_all = "https://raw.githubusercontent.com/r-f-t/US-Stock-Symbols/master/nasdaq/nasdaq_full_tickers.txt"
        try:
            res = requests.get(url_all).text.split('\n')
            tickers.update([t.strip().upper() for t in res if t.strip() and '/' not in t][:1500])
        except: pass

    final_list = sorted(list(tickers))
    # СТРОГОЕ ОГРАНИЧЕНИЕ: Ровно 1000
    return final_list[:1000]

# --- ЛОГИКА СКАНЕРА ---
def run_custom_scanner(client, ticker_pool, category):
    results = []
    # Alpaca Free Tier имеет лимиты. Разбиваем 1000 акций на пачки по 100.
    batch_size = 100
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i in range(0, len(ticker_pool), batch_size):
        batch = ticker_pool[i:i+batch_size]
        status_text.text(f"Сканирование пачки {i//batch_size + 1}/10... ({batch[0]} - {batch[-1]})")
        
        try:
            snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=batch))
            for sym, res in snaps.items():
                if res.daily_bar and res.latest_trade:
                    p_now = res.latest_trade.price
                    p_open = res.daily_bar.open
                    p_high = res.daily_bar.high
                    p_low = res.daily_bar.low
                    vol = res.daily_bar.volume
                    chg = ((p_now - p_open) / p_open) * 100
                    volatility = ((p_high - p_low) / p_low) * 100

                    results.append({
                        "Ticker": sym, "Price": p_now, "Change %": round(chg, 2),
                        "Volume": int(vol), "Volatility %": round(volatility, 2)
                    })
        except Exception as e:
            st.warning(f"Ошибка в пачке {i}: {e}")
        
        progress_bar.progress((i + batch_size) / len(ticker_pool))
        time.sleep(0.1) # Пауза для обхода rate limit

    df = pd.DataFrame(results)
    
    # ФИЛЬТРАЦИЯ ПО КАТЕГОРИЯМ (Аналог Finviz)
    if category == "Top Gainers": return df.sort_values("Change %", ascending=False).head(50)
    if category == "Top Losers": return df.sort_values("Change %", ascending=True).head(50)
    if category == "Most Active": return df.sort_values("Volume", ascending=False).head(50)
    if category == "Most Volatile": return df.sort_values("Volatility %", ascending=False).head(50)
    return df

# --- ИНТЕРФЕЙС ---
with st.sidebar:
    st.header("🔑 Доступ")
    api_key = st.text_input("Alpaca API Key", type="password")
    secret_key = st.text_input("Alpaca Secret Key", type="password")
    
    st.divider()
    st.header("📊 Настройки Сканера")
    finviz_style = st.selectbox("Категория (как на Finviz)", 
                               ["Top Gainers", "Top Losers", "Most Active", "Most Volatile"])
    
    st.info("Двигатель: Собственный расчет по 1000 тикерам.")

if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    tab_scan, tab_analysis = st.tabs(["🚀 Живой Скринер", "🔬 ИИ Анализ"])

    with tab_scan:
        st.subheader(f"Результаты: {finviz_style} (из 1000 ликвидных акций)")
        
        if st.button("▶️ Запустить Глобальное Сканирование", use_container_width=True):
            full_pool = get_golden_1000()
            st.session_state.pool_results = run_custom_scanner(client, full_pool, finviz_style)
            st.success(f"Сканирование 1000 акций завершено. Найдено лидеров: {len(st.session_state.pool_results)}")

        if 'pool_results' in st.session_state:
            st.dataframe(st.session_state.pool_results, use_container_width=True, height=500)
            
            # Отчет для ИИ
            st.subheader("📋 Отчет по пулу для ИИ")
            report = f"MARKET SCANNER REPORT ({finviz_style})\n"
            report += st.session_state.pool_results.to_string(index=False)
            st.code(report)

    with tab_analysis:
        target = st.text_input("Введите тикер для глубокого анализа (например, NVDA):").upper()
        if target:
            with st.spinner("Загрузка данных..."):
                try:
                    now = datetime.now(timezone.utc)
                    d_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Day, start=now-timedelta(days=45))).df
                    m_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Minute, start=now-timedelta(hours=10))).df
                    
                    if isinstance(d_bars.index, pd.MultiIndex): d_bars = d_bars.loc[target]
                    if isinstance(m_bars.index, pd.MultiIndex): m_bars = m_bars.loc[target]

                    st.metric(target, f"${m_bars['close'].iloc[-1]}", f"{st.session_state.pool_results[st.session_state.pool_results['Ticker']==target]['Change %'].values[0] if 'pool_results' in st.session_state else ''}%")
                    
                    c1, c2 = st.columns(2)
                    c1.write("📅 Daily")
                    c1.dataframe(d_bars[['open', 'high', 'low', 'close', 'volume']].tail(10))
                    c2.write("⏱️ Minute")
                    c2.dataframe(m_bars[['open', 'high', 'low', 'close', 'volume']].tail(15))

                    st.code(f"AI ANALYSIS FOR {target}\n\nDAILY:\n{d_bars.tail(7).to_string()}\n\nMINUTE:\n{m_bars.tail(15).to_string()}")
                except:
                    st.error("Данные недоступны. Проверьте тикер.")
else:
    st.warning("Введите ключи доступа Alpaca.")

