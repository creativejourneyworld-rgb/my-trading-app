import streamlit as st

# Проверка импортов (диагностика)
try:
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
except ImportError as e:
    st.error(f"❌ Ошибка установки библиотек: {e}")
    st.info("Пожалуйста, проверьте requirements.txt и сделайте 'Reboot App' в панели управления Streamlit.")
    st.stop()

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(page_title="Eagle AI Turbo Terminal", layout="wide", page_icon="🦅")
st.title("🦅 Eagle AI Turbo Terminal v3.7")

# --- ИНИЦИАЛИЗАЦИЯ SESSION STATE ---
if 'movers_df' not in st.session_state: st.session_state.movers_df = pd.DataFrame()
if 'api_key' not in st.session_state: st.session_state.api_key = st.secrets.get("ALPACA_API_KEY", "")
if 'api_secret' not in st.session_state: st.session_state.api_secret = st.secrets.get("ALPACA_SECRET_KEY", "")

# --- ФУНКЦИИ ---

def extract_tickers(text):
    potential = re.findall(r'\b[A-Z]{1,5}\b', text)
    exclude = {'USD', 'VOL', 'LOW', 'HIGH', 'OPEN', 'CLOSE', 'P/E', 'EPS', 'CEO', 'NYSE', 'AMEX', 'NASD', 'BUY', 'SELL', 'DATE'}
    return sorted(list(set(t for t in potential if t not in exclude)))

def safe_get_df(df, ticker):
    try:
        if isinstance(df.index, pd.MultiIndex):
            return df.loc[ticker].copy()
        return df.copy()
    except:
        return pd.DataFrame()

def fetch_bars(client, ticker, timeframe, days_back):
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

def draw_turbo_chart(df, ticker):
    if df.empty or len(df) < 20: 
        st.warning("Недостаточно данных для графика.")
        return None
    
    # Расчет индикаторов
    df['SMA_20'] = ta.sma(df['close'], length=20)
    df['SMA_50'] = ta.sma(df['close'], length=50)
    df['RSI_14'] = ta.rsi(df['close'], length=14)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, 
                        subplot_titles=(f'{ticker} Цена', 'Объем', 'RSI'),
                        row_width=[0.2, 0.2, 0.6])

    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Цена'), row=1, col=1)
    if 'SMA_20' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], name='SMA 20', line=dict(color='yellow', width=1)), row=1, col=1)
    if 'SMA_50' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], name='SMA 50', line=dict(color='cyan', width=1)), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Объем', marker_color='white', opacity=0.5), row=2, col=1)
    
    if 'RSI_14' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI_14'], name='RSI', line=dict(color='magenta', width=1.5)), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

    fig.update_layout(height=700, template='plotly_dark', xaxis_rangeslider_visible=False)
    return fig

# --- ИНТЕРФЕЙС ---
with st.sidebar:
    st.header("🔐 Ключи")
    st.session_state.api_key = st.text_input("Alpaca API Key", value=st.session_state.api_key, type="password")
    st.session_state.api_secret = st.text_input("Alpaca Secret Key", value=st.session_state.api_secret, type="password")
    
    st.divider()
    source = st.radio("Источник:", ["Умная вставка", "Индексы (Wiki)"])
    if source == "Умная вставка":
        raw_input = st.text_area("Вставь текст сюда:", height=100)

if st.session_state.api_key and st.session_state.api_secret:
    try:
        client = StockHistoricalDataClient(st.session_state.api_key, st.session_state.api_secret)
        t_scan, t_turbo = st.tabs(["🔍 Скринер", "🚀 ТУРБО"])

        with t_scan:
            if st.button("▶️ СКАНИРОВАТЬ"):
                tickers = []
                if source == "Умная вставка" and raw_input:
                    tickers = extract_tickers(raw_input)
                else:
                    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    resp = requests.get(url, headers=headers)
                    tickers = pd.read_html(resp.text, flavor='html.parser')[0]['Symbol'].tolist()[:50]

                if tickers:
                    snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=tickers, feed='iex'))
                    rows = []
                    for s, res in snaps.items():
                        if res.daily_bar:
                            chg = ((res.latest_trade.price / res.daily_bar.open) - 1) * 100
                            rows.append({"Тикер": s, "Цена": res.latest_trade.price, "Изм %": round(chg, 2), "Объем": res.daily_bar.volume})
                    st.session_state.movers_df = pd.DataFrame(rows).sort_values("Изм %", ascending=False)
                    st.dataframe(st.session_state.movers_df, use_container_width=True)

        with t_turbo:
            target = st.text_input("Тикер для ТУРБО:", value="NVDA").upper()
            if st.button("🔥 ТУРБО СТАРТ"):
                d = fetch_bars(client, target, TimeFrame.Day, 365)
                h = fetch_bars(client, target, TimeFrame.Hour, 100)
                m = fetch_bars(client, target, TimeFrame.Minute, 1)
                
                if not d.empty:
                    st.metric("Цена", f"${d['close'].iloc[-1]}")
                    fig = draw_turbo_chart(d, target)
                    if fig: st.plotly_chart(fig, use_container_width=True)
                    st.code(f"AI DATA:\n{d.tail(5).to_string()}\n\n{m.tail(5).to_string()}")

    except Exception as e:
        st.error(f"Ошибка: {e}")
else:
    st.info("Введите ключи слева.")
