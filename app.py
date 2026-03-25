import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.enums import DataFeed
from datetime import datetime, timedelta, timezone
import re

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(page_title="Eagle Real-Time Terminal", layout="wide")
st.title("🦅 Eagle AI Terminal: Real-Time (IEX) + Smart Batch")

# --- СИСТЕМНЫЕ ФУНКЦИИ ---

def extract_tickers(text):
    """ТРИЗ: Извлечение тикеров из любого мусора"""
    potential_tickers = re.findall(r'\b[A-Z]{1,5}\b', text)
    exclude = {'USD', 'VOL', 'LOW', 'HIGH', 'OPEN', 'CLOSE', 'P/E', 'EPS', 'CEO', 'NYSE', 'AMEX', 'NASD', 'DATE', 'TIME', 'BUY', 'SELL'}
    return sorted(list(set(t for t in potential_tickers if t not in exclude)))

def get_indices_stable(index_name):
    """Исправленный метод получения индексов (обходим 403 ошибку)"""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies" if index_name == "S&P 500" else "https://en.wikipedia.org/wiki/Nasdaq-100#Components"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        tables = pd.read_html(response.text)
        df = tables[0]
        col = 'Symbol' if 'Symbol' in df.columns else 'Ticker'
        return df[col].tolist()[:100] # Берем топ-100 для скорости
    except Exception as e:
        st.error(f"Ошибка доступа к Wiki: {e}")
        return []

def fetch_detailed_data(client, ticker):
    """Вспомогательная функция для сбора Daily + Minute данных"""
    now = datetime.now(timezone.utc)
    # Используем feed='iex' для Real-Time данных на бесплатном тарифе
    d_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Day, start=now-timedelta(days=30), feed='iex')).df
    m_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Minute, start=now-timedelta(hours=8), feed='iex')).df
    
    if isinstance(d_bars.index, pd.MultiIndex): d_bars = d_bars.loc[ticker]
    if isinstance(m_bars.index, pd.MultiIndex): m_bars = m_bars.loc[ticker]
    return d_bars, m_bars

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("🔐 Доступ Alpaca")
    default_key = st.secrets.get("ALPACA_API_KEY", "")
    default_secret = st.secrets.get("ALPACA_SECRET_KEY", "")
    api_key = st.text_input("API Key", value=default_key, type="password")
    secret_key = st.text_input("Secret Key", value=default_secret, type="password")
    
    st.divider()
    st.header("🎯 Источник")
    source_type = st.radio("Метод:", ["Умная вставка", "Индексы", "Свой список"])
    
    if source_type == "Индексы":
        category = st.selectbox("Индекс", ["S&P 500", "NASDAQ 100"])
    elif source_type == "Свой список":
        manual_tickers = st.text_area("Тикеры через пробел")

# --- ОСНОВНАЯ ЛОГИКА ---
if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    tab_scan, tab_analysis = st.tabs(["🔍 Поиск и Пул", "📊 Детальный Анализ"])

    with tab_scan:
        if source_type == "Умная вставка":
            raw_text = st.text_area("Вставь сюда текст с Finviz/TradingView:", height=150)
            if st.button("🚀 Извлечь и получить котировки (LIVE IEX)", use_container_width=True):
                st.session_state.target_tickers = extract_tickers(raw_text)
        elif source_type == "Индексы":
            if st.button("🚀 Загрузить индекс (LIVE IEX)", use_container_width=True):
                st.session_state.target_tickers = get_indices_stable(category)
        else:
            if st.button("🚀 Загрузить список", use_container_width=True):
                st.session_state.target_tickers = manual_tickers.upper().split()

        # Получение Snapshot (Живые цены)
        if 'target_tickers' in st.session_state and st.session_state.target_tickers:
            try:
                # ВАЖНО: feed='iex' дает 0 минут задержки для бесплатных ключей
                snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=st.session_state.target_tickers, feed='iex'))
                res_list = []
                for s, res in snaps.items():
                    if res.daily_bar:
                        change = ((res.latest_trade.price - res.daily_bar.open) / res.daily_bar.open) * 100
                        res_list.append({"Тикер": s, "Цена": res.latest_trade.price, "Изм %": round(change, 2), "Объем": res.daily_bar.volume})
                
                st.session_state.last_df = pd.DataFrame(res_list).sort_values("Изм %", ascending=False)
                st.dataframe(st.session_state.last_df, use_container_width=True)

                # КНОПКИ ДЕЙСТВИЙ С ПУЛОМ
                col_pool1, col_pool2 = st.columns(2)
                
                with col_pool1:
                    if st.button("📦 Сформировать ОТЧЕТ ПО ВСЕМУ ПУЛУ (Daily+Min)"):
                        with st.spinner("Сбор мега-отчета..."):
                            full_report = "--- МЕГА-ОТЧЕТ ПО ПУЛУ ДЛЯ ИИ ---\n\n"
                            for t in st.session_state.target_tickers[:10]: # Ограничение 10 для стабильности
                                try:
                                    d, m = fetch_detailed_data(client, t)
                                    full_report += f"=== {t} ===\nDAILY:\n{d.tail(5).to_string()}\nMINUTE:\n{m.tail(10).to_string()}\n\n"
                                except: continue
                            st.code(full_report)

                with col_pool2:
                    selected_from_list = st.selectbox("Выбрать для детального анализа:", st.session_state.target_tickers)
                    if st.button("🔎 Получить данные по акции"):
                        st.session_state.analysis_target = selected_from_list
                        st.info(f"Акция {selected_from_list} готова во второй вкладке!")

            except Exception as e:
                st.error(f"Ошибка Alpaca: {e}")

    with tab_analysis:
        # Либо вводим вручную, либо подхватываем из первой вкладки
        target = st.text_input("Тикер для анализа:", value=st.session_state.get('analysis_target', ""), key="analysis_field").upper()
        if target:
            try:
                d_bars, m_bars = fetch_detailed_data(client, target)
                st.subheader(f"Технический срез: {target} (REAL-TIME IEX)")
                c1, c2 = st.columns(2)
                c1.write("Daily (Last 7d)")
                c1.dataframe(d_bars[['open', 'high', 'low', 'close']].tail(7))
                c2.write("Minute (Last 15m)")
                c2.dataframe(m_bars[['open', 'close', 'volume']].tail(15))

                ai_final = f"ДАННЫЕ ПО {target} (REAL-TIME IEX)\n\nDaily:\n{d_bars.tail(7).to_string()}\n\nMinute:\n{m_bars.tail(15).to_string()}"
                st.code(ai_final, language="text")
            except Exception as e:
                st.error(f"Ошибка: {e}")
else:
    st.info("Введите API ключи Alpaca.")
