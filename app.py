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
st.set_page_config(page_title="Eagle Turbo AI Terminal", layout="wide", page_icon="🚀")
st.title("🦅 Eagle AI Terminal: Turbo Mode v4.0")

# --- СИСТЕМНЫЕ ФУНКЦИИ ---

def extract_tickers(text):
    """Извлечение тикеров из любого текста"""
    potential = re.findall(r'\b[A-Z]{1,5}\b', text)
    exclude = {'USD', 'VOL', 'LOW', 'HIGH', 'OPEN', 'CLOSE', 'P/E', 'EPS', 'CEO', 'NYSE', 'AMEX', 'NASD', 'DATE', 'TIME', 'BUY', 'SELL'}
    return sorted(list(set(t for t in potential if t not in exclude)))

def get_indices_stable(index_name):
    """Получение индексов через Wikipedia (с обходом 403)"""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies" if index_name == "S&P 500" else "https://en.wikipedia.org/wiki/Nasdaq-100#Components"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        tables = pd.read_html(response.text)
        df = tables[0]
        col = 'Symbol' if 'Symbol' in df.columns else 'Ticker'
        return df[col].tolist()[:100]
    except Exception as e:
        st.error(f"Ошибка доступа к Wiki: {e}")
        return []

def safe_get_bars(client, ticker, timeframe, start_time):
    """Безопасное получение баров с обработкой MultiIndex"""
    try:
        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=timeframe,
            start=start_time,
            feed='iex'
        )
        df = client.get_stock_bars(req).df
        if isinstance(df.index, pd.MultiIndex):
            return df.loc[ticker]
        return df
    except:
        return pd.DataFrame()

# --- ТУРБО ФУНКЦИЯ ---

def fetch_turbo_package(client, ticker):
    """Сбор МАКСИМАЛЬНОЙ информации по тикеру по всем таймфреймам"""
    now = datetime.now(timezone.utc)
    
    with st.spinner(f"🚀 Запуск Турбо-двигателя для {ticker}..."):
        # Определяем горизонты
        packages = {
            "MONTHLY (2Y)": {"tf": TimeFrame.Month, "days": 730},
            "DAILY (1Y)": {"tf": TimeFrame.Day, "days": 365},
            "HOURLY (2M)": {"tf": TimeFrame.Hour, "days": 60},
            "5-MINUTE (2W)": {"tf": TimeFrame.Minute * 5, "days": 14},
            "1-MINUTE (3D)": {"tf": TimeFrame.Minute, "days": 3}
        }
        
        turbo_data = {}
        for label, params in packages.items():
            start = now - timedelta(days=params["days"])
            df = safe_get_bars(client, ticker, params["tf"], start)
            turbo_data[label] = df
            
        return turbo_data

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("🔐 Ключи Alpaca")
    api_key = st.text_input("API Key", value=st.secrets.get("ALPACA_API_KEY", ""), type="password")
    secret_key = st.text_input("Secret Key", value=st.secrets.get("ALPACA_SECRET_KEY", ""), type="password")
    
    st.divider()
    source_type = st.radio("Метод выбора:", ["Умная вставка", "Индексы", "Свой список"])
    if source_type == "Индексы":
        category = st.selectbox("Индекс", ["S&P 500", "NASDAQ 100"])

# --- ЛОГИКА ---
if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    tab_scan, tab_analysis, tab_turbo = st.tabs(["🔍 Скринер", "📊 Анализ", "🚀 ТУРБО"])

    # ВКЛАДКА 1: СКРИНЕР
    with tab_scan:
        if source_type == "Умная вставка":
            raw_text = st.text_area("Вставь текст (Finviz/TV):", height=150)
            if st.button("🚀 Получить котировки (Real-Time IEX)"):
                st.session_state.target_tickers = extract_tickers(raw_text)
        elif source_type == "Индексы":
            if st.button("🚀 Загрузить Индекс"):
                st.session_state.target_tickers = get_indices_stable(category)
        
        if 'target_tickers' in st.session_state and st.session_state.target_tickers:
            snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=st.session_state.target_tickers, feed='iex'))
            rows = []
            for s, res in snaps.items():
                if res.daily_bar:
                    chg = ((res.latest_trade.price - res.daily_bar.open) / res.daily_bar.open) * 100
                    rows.append({"Тикер": s, "Цена": res.latest_trade.price, "Изм %": round(chg, 2), "Объем": res.daily_bar.volume})
            st.session_state.last_df = pd.DataFrame(rows).sort_values("Изм %", ascending=False)
            st.dataframe(st.session_state.last_df, use_container_width=True)

    # ВКЛАДКА 2: ОБЫЧНЫЙ АНАЛИЗ
    with tab_analysis:
        target = st.text_input("Тикер для быстрого анализа:", key="quick").upper()
        if target:
            try:
                now = datetime.now(timezone.utc)
                d_bars = safe_get_bars(client, target, TimeFrame.Day, now - timedelta(days=30))
                m_bars = safe_get_bars(client, target, TimeFrame.Minute, now - timedelta(hours=8))
                st.subheader(f"Срез по {target}")
                col1, col2 = st.columns(2)
                col1.dataframe(d_bars.tail(7))
                col2.dataframe(m_bars.tail(15))
            except: st.error("Ошибка получения данных")

    # ВКЛАДКА 3: ТУРБО-РЕЖИМ
    with tab_turbo:
        st.subheader("🔥 Максимально глубокий сбор данных (1 год + все ТФ)")
        t_target = st.text_input("Введите тикер для ТУРБО-АНАЛИЗА:", key="turbo_t").upper()
        
        if st.button("🚀 ЗАПУСТИТЬ ТУРБО-СБОР", use_container_width=True):
            if t_target:
                data_package = fetch_turbo_package(client, t_target)
                
                # Отображение данных в интерфейсе
                st.success(f"Данные по {t_target} успешно собраны!")
                
                # Создаем компактный отчет для копирования
                full_turbo_report = f"--- TURBO DATA PACKAGE: {t_target} ---\n"
                full_turbo_report += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                
                for label, df in data_package.items():
                    with st.expander(f"Просмотр {label}"):
                        st.dataframe(df.tail(20), use_container_width=True)
                    
                    # Добавляем в текстовый отчет (последние срезы для ИИ)
                    full_turbo_report += f"[{label}]\n{df.tail(10).to_string()}\n\n"
                
                st.divider()
                st.subheader("📋 КОПИРОВАТЬ ДЛЯ ИИ (TURBO REPORT)")
                st.code(full_turbo_report, language="text")
            else:
                st.warning("Сначала введите тикер.")

else:
    st.info("Введите API ключи Alpaca в боковой панели.")
