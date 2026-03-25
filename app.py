import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone
import re

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="AI Alpha Terminal", layout="wide", page_icon="🦅")
st.title("🦅 AI Alpha Terminal v2.0")

# --- СТИЛИЗАЦИЯ ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .stDataFrame { border: 1px solid #333; }
    </style>
    """, unsafe_allow_html=True)

# --- ИНИЦИАЛИЗАЦИЯ SESSION STATE ---
if 'ticker_list' not in st.session_state: st.session_state.ticker_list = []
if 'movers_df' not in st.session_state: st.session_state.movers_df = pd.DataFrame()

# --- ФУНКЦИИ КОРРЕКТИРОВКИ ТИКЕРОВ ---
def clean_tickers(tickers):
    """Очистка тикеров для Alpaca (замена BRK.B на BRK/B и т.д.)"""
    cleaned = [str(t).strip().upper().replace('.', '/') for t in tickers if t]
    return [t for t in cleaned if re.match(r'^[A-Z0-9/]+$', t)]

# --- ПАРСЕРЫ ---
def fetch_finviz(signal_key):
    signals = {
        "Top Gainers": "ta_topgainers", "Top Losers": "ta_toplosers",
        "New High": "ta_newhigh", "Most Active": "ta_mostactive",
        "Overbought": "ta_overbought", "Oversold": "ta_oversold"
    }
    url = f"https://finviz.com/screener.ashx?v=111&s={signals[signal_key]}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        tickers = [a.text for a in soup.find_all('a', class_='screener-link-primary')]
        return clean_tickers(tickers)
    except Exception as e:
        st.error(f"Finviz Error: {e}")
        return []

def fetch_wikipedia(index_name):
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies" if index_name == "S&P 500" else "https://en.wikipedia.org/wiki/Nasdaq-100#Components"
    try:
        df = pd.read_html(url)[0]
        col = 'Symbol' if 'Symbol' in df.columns else 'Ticker'
        return clean_tickers(df[col].tolist())
    except Exception as e:
        st.error(f"Wiki Error: {e}")
        return []

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("🔑 Доступ")
    api_key = st.text_input("Alpaca Key", value=st.secrets.get("ALPACA_API_KEY", ""), type="password")
    secret_key = st.text_input("Alpaca Secret", value=st.secrets.get("ALPACA_SECRET_KEY", ""), type="password")
    
    st.divider()
    st.header("🔍 Настройка выборки")
    mode = st.radio("Источник:", ["Finviz", "Индексы", "Ручной ввод"])
    
    if mode == "Finviz":
        cat = st.selectbox("Категория:", ["Top Gainers", "Top Losers", "Most Active", "Oversold"])
    elif mode == "Индексы":
        cat = st.selectbox("Индекс:", ["S&P 500", "NASDAQ 100"])
    else:
        manual = st.text_area("Тикеры (через пробел):")

    if st.button("🚀 ШАГ 1: Загрузить список"):
        with st.spinner("Получение тикеров..."):
            if mode == "Finviz": st.session_state.ticker_list = fetch_finviz(cat)
            elif mode == "Индексы": st.session_state.ticker_list = fetch_wikipedia(cat)
            else: st.session_state.ticker_list = clean_tickers(manual.split())
        
        if st.session_state.ticker_list:
            st.success(f"Загружено {len(st.session_state.ticker_list)} тикеров")
        else:
            st.error("Список пуст. Проверьте источник.")

# --- ОСНОВНОЙ ЭКРАН ---
if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    tab_scan, tab_analysis = st.tabs(["🚀 Скринер цен", "🔬 ИИ Анализ"])

    with tab_scan:
        if not st.session_state.ticker_list:
            st.info("Сначала загрузите список тикеров в боковом меню 👈")
        else:
            if st.button("💰 ШАГ 2: Получить живые котировки"):
                with st.status("Запрос данных из Alpaca...") as status:
                    try:
                        # Берем первые 100 для стабильности
                        batch = st.session_state.ticker_list[:100]
                        status.update(label=f"Запрос цен для {len(batch)} акций...")
                        
                        snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=batch))
                        
                        rows = []
                        for s, res in snaps.items():
                            if res.daily_bar and res.latest_trade:
                                price = res.latest_trade.price
                                open_p = res.daily_bar.open
                                chg = ((price - open_p) / open_p) * 100
                                rows.append({
                                    "Ticker": s, "Price": price, 
                                    "Change %": round(chg, 2), "Volume": res.daily_bar.volume
                                })
                        
                        st.session_state.movers_df = pd.DataFrame(rows).sort_values("Change %", ascending=False)
                        status.update(label="Готово!", state="complete")
                    except Exception as e:
                        st.error(f"Alpaca API Error: {e}")

        if not st.session_state.movers_df.empty:
            st.dataframe(st.session_state.movers_df, use_container_width=True, height=400)
            
            # Генерация отчета для ИИ
            pool_report = f"MARKET SNAPSHOT ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
            pool_report += st.session_state.movers_df.to_string(index=False)
            st.subheader("📋 Данные пула для ИИ")
            st.code(pool_report)

    with tab_analysis:
        target = st.text_input("Введите тикер из списка выше для глубокого анализа:").upper()
        if target:
            try:
                with st.spinner("Загрузка графиков..."):
                    now = datetime.now(timezone.utc)
                    # Фикс для времени (Alpaca не любит будущее время)
                    start_d = now - timedelta(days=45)
                    
                    d_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Day, start=start_d)).df
                    m_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Minute, start=now-timedelta(hours=8))).df
                    
                    if isinstance(d_bars.index, pd.MultiIndex): d_bars = d_bars.loc[target]
                    if isinstance(m_bars.index, pd.MultiIndex): m_bars = m_bars.loc[target]

                    col1, col2 = st.columns(2)
                    col1.metric("Цена", f"${m_bars['close'].iloc[-1]}", f"{round(((m_bars['close'].iloc[-1]/d_bars['open'].iloc[-1])-1)*100, 2)}%")
                    
                    st.divider()
                    c1, c2 = st.columns(2)
                    c1.write("📅 Daily (10 days)")
                    c1.dataframe(d_bars[['open', 'high', 'low', 'close', 'volume']].tail(10))
                    c2.write("⏱️ Minute (15 min)")
                    c2.dataframe(m_bars[['open', 'high', 'low', 'close', 'volume']].tail(15))

                    final_txt = f"ANALYSIS FOR {target}\n\nDAILY:\n{d_bars.tail(7).to_string()}\n\nMINUTE:\n{m_bars.tail(15).to_string()}"
                    st.subheader("📋 Текст для чата с ИИ")
                    st.code(final_txt)
            except Exception as e:
                st.error(f"Данные по {target} временно недоступны. Попробуйте другой тикер.")
else:
    st.warning("👈 Введите ключи доступа Alpaca в боковой панели.")
