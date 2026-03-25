import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(page_title="Ultra AI Terminal", layout="wide")
st.title("🦅 Ultra Trading Terminal: Alpaca + Finviz")

# --- ФУНКЦИИ ПАРСИНГА FINVIZ ---
FINVIZ_SIGNALS = {
    "Top Gainers": "ta_topgainers",
    "Top Losers": "ta_toplosers",
    "New High": "ta_newhigh",
    "New Low": "ta_newlow",
    "Most Volatile": "ta_mostvolatile",
    "Most Active": "ta_mostactive",
    "Overbought": "ta_overbought",
    "Oversold": "ta_oversold"
}

def get_finviz_tickers(signal_key):
    """Парсинг тикеров с Finviz по выбранному сигналу"""
    signal_value = FINVIZ_SIGNALS[signal_key]
    url = f"https://finviz.com/screener.ashx?v=111&s={signal_value}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        # Ищем таблицу с тикерами. На Finviz тикеры обычно в ссылках с классом screener-link-primary
        tickers = []
        links = soup.find_all('a', class_='screener-link-primary')
        for link in links:
            tickers.append(link.text)
        return list(set(tickers)) # Убираем дубликаты
    except Exception as e:
        st.error(f"Ошибка парсинга Finviz: {e}")
        return []

# --- БОКОВАЯ ПАНЕЛЬ (КЛЮЧИ И НАСТРОЙКИ) ---
with st.sidebar:
    st.header("🔐 Доступ")
    # Пробуем взять из Secrets, если нет - просим ввести
    default_key = st.secrets.get("ALPACA_API_KEY", "")
    default_secret = st.secrets.get("ALPACA_SECRET_KEY", "")
    
    api_key = st.text_input("Alpaca Key", value=default_key, type="password")
    secret_key = st.text_input("Alpaca Secret", value=default_secret, type="password")
    
    st.divider()
    st.header("🎯 Источник данных")
    source_type = st.radio("Выбрать акции из:", ["Finviz Signals", "Индексы", "Свой список"])
    
    if source_type == "Finviz Signals":
        category = st.selectbox("Категория Finviz", list(FINVIZ_SIGNALS.keys()))
    elif source_type == "Индексы":
        category = st.selectbox("Индекс", ["S&P 500", "NASDAQ 100"])
    else:
        manual_tickers = st.text_area("Введите тикеры (через пробел)")

# --- ОСНОВНАЯ ЛОГИКА ---
if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    tab_scan, tab_analysis = st.tabs(["🔍 Поиск инструментов", "📊 Анализ для ИИ"])

    # ВКЛАДКА 1: ПОИСК
    with tab_scan:
        if st.button("🚀 Получить актуальный список и цены", use_container_width=True):
            with st.spinner('Синхронизация с рынком...'):
                # Определяем список тикеров
                if source_type == "Finviz Signals":
                    tickers = get_finviz_tickers(category)
                elif source_type == "Индексы":
                    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies" if category == "S&P 500" else "https://en.wikipedia.org/wiki/Nasdaq-100#Components"
                    tickers = pd.read_html(url)[0]['Symbol' if 'Symbol' in pd.read_html(url)[0].columns else 'Ticker'].tolist()[:100]
                else:
                    tickers = manual_tickers.upper().split()

                if tickers:
                    # Получаем Snapshot
                    snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=tickers))
                    res_list = []
                    for s, res in snaps.items():
                        if res.daily_bar:
                            change = ((res.latest_trade.price - res.daily_bar.open) / res.daily_bar.open) * 100
                            res_list.append({"Тикер": s, "Цена": res.latest_trade.price, "Изм %": round(change, 2), "Объем": res.daily_bar.volume})
                    
                    st.session_state.last_df = pd.DataFrame(res_list).sort_values("Изм %", ascending=False)
                    st.success(f"Найдено {len(tickers)} акций в категории {category if source_type != 'Свой список' else ''}")
                else:
                    st.warning("Тикеры не найдены.")

        if 'last_df' in st.session_state:
            st.dataframe(st.session_state.last_df, use_container_width=True)
            
            # Кнопка анализа всего ПУЛА
            pool_text = "АНАЛИЗ ПУЛА АКЦИЙ:\n" + st.session_state.last_df.to_string()
            st.subheader("📋 Отчет по всему списку для ИИ")
            st.code(pool_text, language="text")

    # ВКЛАДКА 2: АНАЛИЗ КОНКРЕТНОГО ТИКЕРА
    with tab_analysis:
        target = st.text_input("Введите конкретный тикер из списка выше:", key="analysis_target").upper()
        if target:
            try:
                now = datetime.now(timezone.utc)
                d_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Day, start=now-timedelta(days=30))).df
                m_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Minute, start=now-timedelta(hours=8))).df
                
                if isinstance(d_bars.index, pd.MultiIndex): d_bars = d_bars.loc[target]
                if isinstance(m_bars.index, pd.MultiIndex): m_bars = m_bars.loc[target]

                st.subheader(f"Технический срез: {target}")
                col1, col2 = st.columns(2)
                col1.write("Daily (Last 7d)")
                col1.dataframe(d_bars[['open', 'high', 'low', 'close']].tail(7))
                col2.write("Minute (Last 15m)")
                col2.dataframe(m_bars[['open', 'close', 'volume']].tail(15))

                ai_final = f"ДАННЫЕ ПО {target}\n\nDaily:\n{d_bars.tail(7).to_string()}\n\nMinute:\n{m_bars.tail(15).to_string()}"
                st.subheader("📋 Данные для копирования (Индивидуально)")
                st.code(ai_final, language="text")
            except Exception as e:
                st.error(f"Ошибка сбора данных по {target}: {e}")

else:
    st.info("Введите API ключи слева или настройте Secrets в Streamlit Cloud.")
