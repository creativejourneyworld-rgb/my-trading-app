import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas_ta as ta
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone
import re

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Eagle AI Turbo Terminal", layout="wide", page_icon="🦅")
st.title("🦅 Eagle AI Turbo Terminal v3.5")

# --- СТИЛИЗАЦИЯ ---
st.markdown("""<style> .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #2e7d32; color: white; } </style>""", unsafe_allow_html=True)

# --- ИНИЦИАЛИЗАЦИЯ SESSION STATE ---
if 'movers_df' not in st.session_state: st.session_state.movers_df = pd.DataFrame()
if 'api_key' not in st.session_state: st.session_state.api_key = st.secrets.get("ALPACA_API_KEY", "")
if 'api_secret' not in st.session_state: st.session_state.api_secret = st.secrets.get("ALPACA_SECRET_KEY", "")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def extract_tickers(text):
    """Извлечение тикеров из любого текста"""
    potential = re.findall(r'\b[A-Z]{1,5}\b', text)
    exclude = {'USD', 'VOL', 'LOW', 'HIGH', 'OPEN', 'CLOSE', 'P/E', 'EPS', 'CEO', 'NYSE', 'AMEX', 'NASD', 'BUY', 'SELL', 'DATE'}
    return sorted(list(set(t for t in potential if t not in exclude)))

def safe_get_df(df, ticker):
    """Безопасное извлечение данных из MultiIndex DataFrame Alpaca"""
    try:
        if isinstance(df.index, pd.MultiIndex):
            return df.loc[ticker].copy()
        return df.copy()
    except:
        return pd.DataFrame()

# --- ФУНКЦИИ ЗАГРУЗКИ ДАННЫХ ---

def fetch_bars(client, ticker, timeframe, days_back):
    """Универсальная функция получения баров"""
    now = datetime.now(timezone.utc)
    try:
        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=timeframe,
            start=now - timedelta(days=days_back),
            feed='iex' # Real-time для Free аккаунтов
        )
        data = client.get_stock_bars(req).df
        return safe_get_df(data, ticker)
    except:
        return pd.DataFrame()

# --- ТУРБО ГРАФИК ---

def draw_turbo_chart(df, ticker):
    """Создание проф. графика с RSI и SMA"""
    if df.empty or len(df) < 20: 
        st.warning("Недостаточно данных для построения проф. графика")
        return None
    
    # Расчет индикаторов
    df.ta.sma(length=20, append=True)
    df.ta.sma(length=50, append=True)
    df.ta.rsi(length=14, append=True)
    
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, 
                        subplot_titles=(f'{ticker} Price', 'Volume', 'RSI'),
                        row_width=[0.2, 0.2, 0.6])

    # Свечи
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Price'), row=1, col=1)
    if 'SMA_20' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], name='SMA 20', line=dict(color='yellow', width=1)), row=1, col=1)
    if 'SMA_50' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], name='SMA 50', line=dict(color='cyan', width=1)), row=1, col=1)
    
    # Объем
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker_color='white', opacity=0.5), row=2, col=1)
    
    # RSI
    if 'RSI_14' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI_14'], name='RSI', line=dict(color='magenta', width=1.5)), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

    fig.update_layout(height=800, template='plotly_dark', xaxis_rangeslider_visible=False)
    return fig

# --- ИНТЕРФЕЙС: БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("🔑 Авторизация")
    st.session_state.api_key = st.text_input("Alpaca API Key", value=st.session_state.api_key, type="password")
    st.session_state.api_secret = st.text_input("Alpaca Secret Key", value=st.session_state.api_secret, type="password")
    
    st.divider()
    st.header("🎯 Режим отбора")
    source = st.radio("Источник тикеров:", ["Умная вставка / Парсинг", "Индексы", "Свой список"])
    
    if source == "Умная вставка / Парсинг":
        raw_input = st.text_area("Вставь текст с Finviz/TV или оставь пустым для авто-парсинга:", height=100)
    elif source == "Индексы":
        idx = st.selectbox("Индекс", ["S&P 500", "NASDAQ 100"])

# --- ГЛАВНАЯ ЛОГИКА ---
if st.session_state.api_key and st.session_state.api_secret:
    client = StockHistoricalDataClient(st.session_state.api_key, st.session_state.api_secret)
    tab_scan, tab_turbo = st.tabs(["🔍 Скринер Лидеров", "🚀 ТУРБО-АНАЛИЗ (Habr)"])

    # ВКЛАДКА 1: СКРИНЕР
    with tab_scan:
        if st.button("▶️ ЗАПУСТИТЬ СКАНЕР", use_container_width=True):
            with st.spinner("Синхронизация с рынком..."):
                tickers = []
                # Логика получения тикеров
                if source == "Умная вставка / Парсинг" and raw_input:
                    tickers = extract_tickers(raw_input)
                else:
                    # Попытка парсинга (с обходом 403)
                    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    try:
                        resp = requests.get(url, headers=headers)
                        tickers = pd.read_html(resp.text)[0]['Symbol'].tolist()[:50]
                    except: tickers = ["AAPL", "NVDA", "TSLA", "AMD", "MSFT", "META", "AMZN", "NFLX"]

                if tickers:
                    try:
                        snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=tickers, feed='iex'))
                        rows = []
                        for s, res in snaps.items():
                            if res.daily_bar:
                                chg = ((res.latest_trade.price / res.daily_bar.open) - 1) * 100
                                rows.append({"Тикер": s, "Цена": res.latest_trade.price, "Изм %": round(chg, 2), "Объем": res.daily_bar.volume})
                        st.session_state.movers_df = pd.DataFrame(rows).sort_values("Изм %", ascending=False)
                    except Exception as e: st.error(f"API Error: {e}")

        if not st.session_state.movers_df.empty:
            st.dataframe(st.session_state.movers_df, use_container_width=True)
            
            # Кнопка мега-отчета
            if st.button("📦 Сформировать МЕГА-ОТЧЕТ ПО ПУЛУ"):
                report = "--- МЕГА-ОТЧЕТ ПО ПУЛУ ДЛЯ ИИ ---\n\n"
                for t in st.session_state.movers_df['Тикер'].tolist()[:10]:
                    d = fetch_bars(client, t, TimeFrame.Day, 30)
                    m = fetch_bars(client, t, TimeFrame.Minute, 1)
                    report += f"=== {t} ===\nDAILY:\n{d.tail(5).to_string()}\nMINUTE:\n{m.tail(10).to_string()}\n\n"
                st.code(report)

    # ВКЛАДКА 2: ТУРБО
    with tab_turbo:
        target = st.text_input("Введите тикер для ТУРБО-АНАЛИЗА (1 год + все ТФ):", value="NVDA").upper()
        if st.button(f"🔥 ЗАПУСТИТЬ ТУРБО {target}", use_container_width=True):
            with st.spinner("Сбор данных по 5 таймфреймам..."):
                # Собираем ТФ
                data = {
                    "Month": fetch_bars(client, target, TimeFrame.Month, 365),
                    "Day": fetch_bars(client, target, TimeFrame.Day, 365),
                    "Hour": fetch_bars(client, target, TimeFrame.Hour, 180),
                    "5Min": fetch_bars(client, target, TimeFrame.Minute*5, 30),
                    "1Min": fetch_bars(client, target, TimeFrame.Minute, 7)
                }

                if not data["Day"].empty:
                    # Метрики
                    m1, m2, m3 = st.columns(3)
                    cur_p = data["1Min"]['close'].iloc[-1] if not data["1Min"].empty else data["Day"]['close'].iloc[-1]
                    m1.metric("Текущая цена", f"${cur_p}")
                    m2.metric("RSI (14)", f"{round(ta.rsi(data['Day']['close']).iloc[-1], 2)}")
                    m3.metric("Объем дня", f"{int(data['Day']['volume'].iloc[-1])}")

                    # График
                    st.divider()
                    fig = draw_turbo_chart(data["Hour"], target)
                    if fig: st.plotly_chart(fig, use_container_width=True)

                    # Отчет для ИИ
                    st.divider()
                    st.subheader("📋 Турбо-отчет для ИИ")
                    turbo_txt = f"--- TURBO DEEP ANALYSIS: {target} ---\n"
                    for k, v in data.items():
                        turbo_txt += f"[{k} DATA]:\n{v.tail(5).to_string()}\n\n"
                    st.code(turbo_txt)
                else:
                    st.error("Данные по тикеру не найдены. Проверьте правильность (только акции США).")
else:
    st.info("👈 Введите ваши API ключи в боковой панели, чтобы начать.")

