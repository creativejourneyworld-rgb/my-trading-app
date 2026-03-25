import streamlit as st
import pandas as pd
import yfinance as yf
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone
import re

# --- НАСТРОЙКИ ТЕРМИНАЛА ---
st.set_page_config(page_title="Eagle Eye Terminal", layout="wide", page_icon="🦅")
st.title("🦅 Eagle Eye: Универсальный ИИ-Терминал")

# --- СИСТЕМНЫЙ ФУНКЦИОНАЛ ---

def extract_tickers(text):
    """ТРИЗ-РЕШЕНИЕ: Извлекает тикеры из любого текстового мусора"""
    # Ищем слова из 1-5 заглавных букв
    potential_tickers = re.findall(r'\b[A-Z]{1,5}\b', text)
    # Исключаем общие слова
    exclude = {'USD', 'VOL', 'LOW', 'HIGH', 'OPEN', 'CLOSE', 'P/E', 'EPS', 'CEO', 'NYSE', 'AMEX', 'NASD'}
    return sorted(list(set(t for t in potential_tickers if t not in exclude)))

@st.cache_data(ttl=60) # Кэшируем на 1 минуту для скорости
def get_realtime_data(tickers):
    """Получение мгновенных данных через Yahoo Finance Bridge"""
    data = []
    if not tickers: return pd.DataFrame()
    
    # Запрос сразу пачкой (намного быстрее)
    tickers_str = " ".join(tickers)
    try:
        stocks = yf.download(tickers_str, period="1d", interval="1m", group_by='ticker', prepost=True, threads=True)
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    last_price = stocks['Close'].iloc[-1]
                    open_price = stocks['Open'].iloc[0]
                else:
                    last_price = stocks[ticker]['Close'].iloc[-1]
                    open_price = stocks[ticker]['Open'].iloc[0]
                
                chg = ((last_price - open_price) / open_price) * 100
                data.append({"Тикер": ticker, "Live Price": round(last_price, 2), "Day Chg %": round(chg, 2)})
            except: continue
    except: pass
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС: БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("🔑 Доступы")
    a_key = st.text_input("Alpaca Key", value=st.secrets.get("ALPACA_API_KEY", ""), type="password")
    a_sec = st.text_input("Alpaca Secret", value=st.secrets.get("ALPACA_SECRET_KEY", ""), type="password")
    
    st.divider()
    st.header("⚙️ Режим отбора")
    mode = st.radio("Как загрузить акции?", ["Умная вставка (Finviz/TV)", "Ручной ввод"])

# --- ГЛАВНЫЙ ИНТЕРФЕЙС ---
if a_key and a_sec:
    client = StockHistoricalDataClient(a_key, a_sec)
    tab1, tab2 = st.tabs(["🎯 Шаг 1: Отбор и Скринер", "🔬 Шаг 2: ИИ Анализ"])

    with tab1:
        st.subheader("Загрузка инструментов")
        if mode == "Умная вставка (Finviz/TV)":
            raw_text = st.text_area("Скопируйте всё (Ctrl+A -> Ctrl+V) с Finviz или любого сайта сюда:", height=150)
            target_tickers = extract_tickers(raw_text)
        else:
            target_tickers = st.text_input("Введите тикеры через пробел:").upper().split()

        if target_tickers:
            st.success(f"Обнаружено тикеров: {len(target_tickers)}")
            
            if st.button("⚡ ПОЛУЧИТЬ LIVE-КОТИРОВКИ (0 мин задержки)"):
                with st.spinner("Связь с биржей..."):
                    df_live = get_realtime_data(target_tickers)
                    if not df_live.empty:
                        st.session_state.current_pool = df_live
                    else:
                        st.error("Не удалось получить данные. Проверьте тикеры.")

        if 'current_pool' in st.session_state:
            st.dataframe(st.session_state.current_pool, use_container_width=True)
            
            # Отчет по пулу
            pool_report = "LIVE MARKET REPORT:\n" + st.session_state.current_pool.to_string(index=False)
            st.code(pool_report)

    with tab2:
        target = st.text_input("Тикер для глубокого анализа:").upper()
        if target:
            try:
                # Получаем данные
                with st.spinner("Загрузка структуры графика..."):
                    now = datetime.now(timezone.utc)
                    # Alpaca для структуры (она надежнее для истории)
                    d_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Day, start=now-timedelta(days=30))).df
                    m_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Minute, start=now-timedelta(hours=6))).df
                    
                    if isinstance(d_bars.index, pd.MultiIndex): d_bars = d_bars.loc[target]
                    if isinstance(m_bars.index, pd.MultiIndex): m_bars = m_bars.loc[target]

                    # Получаем Real-time хвост через Yahoo
                    yt = yf.Ticker(target)
                    rt_price = yt.fast_info.last_price

                    st.metric(f"Цена {target} (REAL-TIME)", f"${round(rt_price, 2)}", f"{round(((rt_price/d_bars['close'].iloc[-2])-1)*100, 2)}%")

                    c1, c2 = st.columns(2)
                    c1.write("📅 Дневные свечи")
                    c1.table(d_bars[['open', 'high', 'low', 'close']].tail(7))
                    c2.write("⏱️ Минутки (Delayed)")
                    c2.table(m_bars[['open', 'close', 'volume']].tail(10))

                    # Генерируем финальный отчет для ИИ
                    ai_final = f"AI ANALYSIS: {target}\nREAL-TIME PRICE: {round(rt_price, 2)}\n\n"
                    ai_final += f"HISTORICAL DAILY:\n{d_bars.tail(7).to_string()}\n\n"
                    ai_final += f"RECENT MINUTES:\n{m_bars.tail(15).to_string()}"
                    st.code(ai_final)
            except Exception as e:
                st.error(f"Ошибка: {e}")
else:
    st.info("Введите ключи в боковой панели.")
