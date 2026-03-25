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

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(page_title="Eagle AI Turbo Terminal", layout="wide", page_icon="🦅")
st.title("🦅 Eagle AI Turbo Terminal v3.6")

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

def fetch_bars(client, ticker, timeframe, days_back):
    """Универсальная функция получения баров"""
    now = datetime.now(timezone.utc)
    try:
        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=timeframe,
            start=now - timedelta(days=days_back),
            feed='iex'
        )
        data = client.get_stock_bars(req).df
        return safe_get_df(data, ticker)
    except:
        return pd.DataFrame()

# --- ТУРБО ГРАФИК ---

def draw_turbo_chart(df, ticker):
    """Создание проф. графика с RSI и SMA"""
    if df.empty or len(df) < 20: 
        st.warning("Недостаточно данных для построения проф. графика. Попробуйте другой тикер.")
        return None
    
    # Расчет индикаторов через pandas_ta
    try:
        df['SMA_20'] = ta.sma(df['close'], length=20)
        df['SMA_50'] = ta.sma(df['close'], length=50)
        df['RSI_14'] = ta.rsi(df['close'], length=14)
    except Exception as e:
        st.error(f"Ошибка расчета индикаторов: {e}")

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, 
                        subplot_titles=(f'{ticker} Price', 'Volume', 'RSI'),
                        row_width=[0.2, 0.2, 0.6])

    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Price'), row=1, col=1)
    
    if 'SMA_20' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], name='SMA 20', line=dict(color='yellow', width=1)), row=1, col=1)
    if 'SMA_50' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], name='SMA 50', line=dict(color='cyan', width=1)), row=1, col=1)
    
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker_color='white', opacity=0.5), row=2, col=1)
    
    if 'RSI_14' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI_14'], name='RSI', line=dict(color='magenta', width=1.5)), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

    fig.update_layout(height=700, template='plotly_dark', xaxis_rangeslider_visible=False)
    return fig

# --- ИНТЕРФЕЙС: БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("🔑 Авторизация")
    st.session_state.api_key = st.text_input("Alpaca API Key", value=st.session_state.api_key, type="password")
    st.session_state.api_secret = st.text_input("Alpaca Secret Key", value=st.session_state.api_secret, type="password")
    
    st.divider()
    st.header("🎯 Режим отбора")
    source = st.radio("Источник тикеров:", ["Умная вставка", "Индексы (Wiki)"])
    
    if source == "Умная вставка":
        raw_input = st.text_area("Вставь текст с Finviz/TV сюда:", height=100)
    elif source == "Индексы (Wiki)":
        idx_choice = st.selectbox("Индекс", ["S&P 500", "NASDAQ 100"])

# --- ГЛАВНАЯ ЛОГИКА ---
if st.session_state.api_key and st.session_state.api_secret:
    client = StockHistoricalDataClient(st.session_state.api_key, st.session_state.api_secret)
    tab_scan, tab_turbo = st.tabs(["🔍 Скринер Лидеров", "🚀 ТУРБО-АНАЛИЗ"])

    with tab_scan:
        if st.button("▶️ ЗАПУСТИТЬ СКАНЕР", use_container_width=True):
            with st.spinner("Сбор тикеров..."):
                tickers = []
                if source == "Умная вставка" and raw_input:
                    tickers = extract_tickers(raw_input)
                else:
                    # Википедия через встроенный html-парсер (без lxml)
                    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    try:
                        resp = requests.get(url, headers=headers)
                        # Используем 'html.parser' вместо 'lxml'
                        tables = pd.read_html(resp.text, flavor='html.parser')
                        tickers = tables[0]['Symbol'].tolist()[:50]
                    except Exception as e: 
                        st.error(f"Ошибка Wiki: {e}")
                        tickers = ["AAPL", "NVDA", "TSLA", "AMD", "MSFT"]

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
            if st.button("📦 Сформировать ОТЧЕТ ДЛЯ ИИ"):
                report = "--- МЕГА-ОТЧЕТ ПО ПУЛУ ---\n\n"
                for t in st.session_state.movers_df['Тикер'].tolist()[:10]:
                    d = fetch_bars(client, t, TimeFrame.Day, 30)
                    m = fetch_bars(client, t, TimeFrame.Minute, 1)
                    report += f"=== {t} ===\nDAILY:\n{d.tail(5).to_string()}\nMINUTE:\n{m.tail(10).to_string()}\n\n"
                st.code(report)

    with tab_turbo:
        target = st.text_input("Введите тикер для ТУРБО-АНАЛИЗА:", value="NVDA").upper()
        if st.button(f"🔥 ЗАПУСТИТЬ ТУРБО {target}", use_container_width=True):
            with st.spinner("Сбор данных..."):
                data = {
                    "Day": fetch_bars(client, target, TimeFrame.Day, 365),
                    "Hour": fetch_bars(client, target, TimeFrame.Hour, 100),
                    "1Min": fetch_bars(client, target, TimeFrame.Minute, 5)
                }

                if not data["Day"].empty:
                    m1, m2 = st.columns(2)
                    cur_p = data["1Min"]['close'].iloc[-1] if not data["1Min"].empty else data["Day"]['close'].iloc[-1]
                    m1.metric("Текущая цена", f"${cur_p}")
                    m2.metric("Объем дня", f"{int(data['Day']['volume'].iloc[-1])}")

                    fig = draw_turbo_chart(data["Day"], target)
                    if fig: st.plotly_chart(fig, use_container_width=True)

                    st.subheader("📋 Турбо-отчет для ИИ")
                    turbo_txt = f"--- TURBO DEEP ANALYSIS: {target} ---\n"
                    for k, v in data.items():
                        turbo_txt += f"[{k} DATA]:\n{v.tail(5).to_string()}\n\n"
                    st.code(turbo_txt)
                else:
                    st.error("Данные по тикеру не найдены. Проверьте тикер (США).")
else:
    st.info("👈 Введите ваши API ключи в боковой панели.")
