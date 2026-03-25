import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone
import re

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(page_title="Ultra AI Terminal", layout="wide")
st.title("🦅 Ultra Trading Terminal: Alpaca + Smart Analytics")

# --- СИСТЕМНЫЕ ФУНКЦИИ ---

def extract_tickers(text):
    """ТРИЗ-РЕШЕНИЕ: Извлекает тикеры из любого текста (даже если там мусор)"""
    # Ищем слова из 1-5 заглавных букв
    potential_tickers = re.findall(r'\b[A-Z]{1,5}\b', text)
    # Список слов-исключений, которые могут быть похожи на тикеры
    exclude = {'USD', 'VOL', 'LOW', 'HIGH', 'OPEN', 'CLOSE', 'P/E', 'EPS', 'CEO', 'NYSE', 'AMEX', 'NASD', 'DATE', 'TIME'}
    return sorted(list(set(t for t in potential_tickers if t not in exclude)))

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
    """Парсинг тикеров с Finviz (если сайт не блокирует сервер)"""
    signal_value = FINVIZ_SIGNALS[signal_key]
    url = f"https://finviz.com/screener.ashx?v=111&s={signal_value}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.content, 'html.parser')
        tickers = [link.text for link in soup.find_all('a', class_='screener-link-primary')]
        return list(set(tickers))
    except:
        return []

# --- БОКОВАЯ ПАНЕЛЬ (КЛЮЧИ И НАСТРОЙКИ) ---
with st.sidebar:
    st.header("🔐 Доступ")
    default_key = st.secrets.get("ALPACA_API_KEY", "")
    default_secret = st.secrets.get("ALPACA_SECRET_KEY", "")
    
    api_key = st.text_input("Alpaca Key", value=default_key, type="password")
    secret_key = st.text_input("Alpaca Secret", value=default_secret, type="password")
    
    st.divider()
    st.header("🎯 Источник данных")
    source_type = st.radio("Метод отбора:", ["Умная вставка (Ctrl+V)", "Finviz Signals", "Индексы", "Свой список"])
    
    if source_type == "Finviz Signals":
        category = st.selectbox("Категория Finviz", list(FINVIZ_SIGNALS.keys()))
    elif source_type == "Индексы":
        category = st.selectbox("Индекс", ["S&P 500", "NASDAQ 100"])
    elif source_type == "Свой список":
        manual_tickers = st.text_area("Тикеры через пробел")

# --- ОСНОВНАЯ ЛОГИКА ---
if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    tab_scan, tab_analysis = st.tabs(["🔍 Поиск инструментов", "📊 Анализ для ИИ"])

    # ВКЛАДКА 1: ПОИСК
    with tab_scan:
        if source_type == "Умная вставка (Ctrl+V)":
            raw_text = st.text_area("Вставь сюда любой текст/таблицу с любого сайта (Finviz, TradingView и др.):", height=150)
            if st.button("🚀 Извлечь тикеры и получить цены", use_container_width=True):
                tickers = extract_tickers(raw_text)
                st.session_state.target_tickers = tickers
        else:
            if st.button("🚀 Получить актуальный список и цены", use_container_width=True):
                with st.spinner('Синхронизация...'):
                    if source_type == "Finviz Signals":
                        tickers = get_finviz_tickers(category)
                        if not tickers: st.warning("Finviz заблокировал автоматический запрос. Используй 'Умную вставку'.")
                    elif source_type == "Индексы":
                        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies" if category == "S&P 500" else "https://en.wikipedia.org/wiki/Nasdaq-100#Components"
                        tickers = pd.read_html(url)[0]['Symbol' if 'Symbol' in pd.read_html(url)[0].columns else 'Ticker'].tolist()[:100]
                    else:
                        tickers = manual_tickers.upper().split()
                    st.session_state.target_tickers = tickers

        # Получение данных Alpaca для выбранных тикеров
        if 'target_tickers' in st.session_state and st.session_state.target_tickers:
            with st.spinner('Загрузка котировок...'):
                try:
                    snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=st.session_state.target_tickers))
                    res_list = []
                    for s, res in snaps.items():
                        if res.daily_bar:
                            change = ((res.latest_trade.price - res.daily_bar.open) / res.daily_bar.open) * 100
                            res_list.append({"Тикер": s, "Цена": res.latest_trade.price, "Изм %": round(change, 2), "Объем": res.daily_bar.volume})
                    
                    st.session_state.last_df = pd.DataFrame(res_list).sort_values("Изм %", ascending=False)
                    st.success(f"Обработано инструментов: {len(st.session_state.target_tickers)}")
                except Exception as e:
                    st.error(f"Ошибка API: {e}")

        if 'last_df' in st.session_state:
            st.dataframe(st.session_state.last_df, use_container_width=True)
            
            # Кнопка анализа всего ПУЛА
            pool_text = "АНАЛИЗ ПУЛА АКЦИЙ:\n" + st.session_state.last_df.to_string()
            st.subheader("📋 Отчет по всему списку для ИИ")
            st.code(pool_text, language="text")

    # ВКЛАДКА 2: АНАЛИЗ КОНКРЕТНОГО ТИКЕРА
    with tab_analysis:
        target = st.text_input("Введите тикер из списка выше:", key="analysis_target").upper()
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
