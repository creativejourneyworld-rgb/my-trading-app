import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas_ta as ta # Библиотека для тех-анализа
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(page_title="Turbo AI Terminal", layout="wide")
st.title("🦅 Eagle Turbo Terminal v3.0")

# --- СИСТЕМНЫЕ ФУНКЦИИ ---

def fetch_turbo_data(client, ticker):
    """Сбор МАКСИМАЛЬНОЙ информации по тикеру за 1 год"""
    now = datetime.now(timezone.utc)
    start_year = now - timedelta(days=365)
    
    # Словари для хранения данных
    tf_data = {}
    
    # Список таймфреймов для запроса
    # Примечание: Alpaca Free Tier ограничивает глубину минутных данных (обычно до нескольких недель/месяцев)
    frames = {
        "Month": TimeFrame.Month,
        "Day": TimeFrame.Day,
        "Hour": TimeFrame.Hour,
        "5 Min": TimeFrame.Minute * 5,
        "1 Min": TimeFrame.Minute
    }
    
    with st.spinner("Загрузка Турбо-пакета данных..."):
        for label, tf in frames.items():
            try:
                # Для минутных данных берем чуть меньше, чтобы не превысить лимиты API за раз
                start_time = start_year if "Min" not in label else now - timedelta(days=30)
                
                req = StockBarsRequest(
                    symbol_or_symbols=ticker,
                    timeframe=tf,
                    start=start_time,
                    feed='iex'
                )
                df = client.get_stock_bars(req).df
                if isinstance(df.index, pd.MultiIndex): df = df.loc[ticker]
                tf_data[label] = df
            except:
                tf_data[label] = pd.DataFrame()
    return tf_data

def create_tv_chart(df, ticker):
    """Создание интерактивного графика как в TradingView (по статье с Habr)"""
    # Расчет индикаторов
    df['SMA20'] = ta.sma(df['close'], length=20)
    df['SMA50'] = ta.sma(df['close'], length=50)
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # Создание фигуры с подграфиками (Цена + Объем + RSI)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f'{ticker} Live Chart', 'Volume', 'RSI'), 
                        row_width=[0.2, 0.2, 0.6])

    # 1. Свечной график
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close',], name='Candlestick'
    ), row=1, col=1)
    
    # Добавляем скользящие средние
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='blue', width=1), name='SMA 20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA50'], line=dict(color='orange', width=1), name='SMA 50'), row=1, col=1)

    # 2. Объем
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker_color='gray'), row=2, col=1)

    # 3. RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=1), name='RSI'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

    # Настройка стиля
    fig.update_layout(height=800, template='plotly_dark', xaxis_rangeslider_visible=False)
    return fig

# --- ИНТЕРФЕЙС ---
with st.sidebar:
    st.header("🔐 Настройки")
    api_key = st.text_input("Alpaca API Key", value=st.secrets.get("ALPACA_API_KEY", ""), type="password")
    secret_key = st.text_input("Alpaca Secret Key", value=st.secrets.get("ALPACA_SECRET_KEY", ""), type="password")
    st.divider()
    target_ticker = st.text_input("🚀 ТИ КЕР ДЛЯ ТУРБО-АНАЛИЗА", value="NVDA").upper()

if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    tab_turbo, tab_standard = st.tabs(["🚀 ТУРБО-РЕЖИМ (Habr Style)", "📊 Стандартный Пул"])

    with tab_turbo:
        if st.button(f"🔥 ЗАПУСТИТЬ ТУРБО-АНАЛИЗ {target_ticker}"):
            data_package = fetch_turbo_data(client, target_ticker)
            
            # Верхняя панель метрик
            latest_price = data_package['1 Min']['close'].iloc[-1]
            prev_close = data_package['Day']['close'].iloc[-2]
            chg = ((latest_price / prev_close) - 1) * 100
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Цена (Real-time IEX)", f"${latest_price}", f"{round(chg, 2)}%")
            m2.metric("High за день", f"${data_package['Day']['high'].iloc[-1]}")
            m3.metric("Low за день", f"${data_package['Day']['low'].iloc[-1]}")
            m4.metric("Объем дня", f"{int(data_package['Day']['volume'].iloc[-1])}")

            # ИНТЕРАКТИВНЫЙ ГРАФИК
            st.divider()
            st.subheader("Интерактивный график (TradingView Style)")
            # Используем часовой график для основного вида, так как он за год
            fig = create_tv_chart(data_package['Hour'], target_ticker)
            st.plotly_chart(fig, use_container_width=True)

            # ТУРБО-ОТЧЕТ ДЛЯ ИИ
            st.divider()
            st.subheader("📋 Турбо-отчет для ИИ (Максимальная глубина)")
            
            # Собираем данные в один блок
            turbo_report = f"--- TURBO DEEP ANALYSIS: {target_ticker} ---\n"
            turbo_report += f"REAL-TIME PRICE: ${latest_price}\n\n"
            for label, df in data_package.items():
                turbo_report += f"[{label} Data - Last 5 rows]:\n{df.tail(5).to_string()}\n\n"
            
            st.code(turbo_report)

    with tab_standard:
        st.write("Тут остается логика твоего стандартного пула и анализа.")

else:
    st.info("Введите ключи доступа в боковой панели.")
