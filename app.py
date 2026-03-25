import streamlit as st
import pandas as pd
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone

# Настройка страницы
st.set_page_config(page_title="Pro AI Terminal", layout="wide")
st.title("🦅 Торговый терминал с ИИ-аналитиком")

# --- Инициализация ключей в Session State ---
if 'movers_df' not in st.session_state:
    st.session_state.movers_df = None

# Боковая панель
st.sidebar.header("🔑 Авторизация")
api_key = st.sidebar.text_input("Alpaca API Key", type="password")
secret_key = st.sidebar.text_input("Alpaca Secret Key", type="password")

index_choice = st.sidebar.selectbox("Индекс для поиска", ["S&P 500", "NASDAQ 100"])
min_diff = st.sidebar.slider("Минимальное движение (%)", 0.0, 5.0, 1.5)

# Функция загрузки тикеров
@st.cache_data
def get_tickers(choice):
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies" if choice == "S&P 500" else "https://en.wikipedia.org/wiki/Nasdaq-100#Components"
    tables = pd.read_html(url)
    df = tables[0]
    col = 'Symbol' if 'Symbol' in df.columns else 'Ticker'
    return df[col].tolist()

# Проверка ключей
if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    
    # Создаем две вкладки
    tab_scan, tab_analysis = st.tabs(["🔍 Скринер рынка", "📊 Глубокий анализ для ИИ"])

    # --- ВКЛАДКА 1: СКРИНЕР ---
    with tab_scan:
        if st.button("🚀 Найти активные акции", use_container_width=True):
            with st.spinner('Сканирую рынок...'):
                try:
                    all_tickers = get_tickers(index_choice)[:150] # Лимит для скорости
                    snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=all_tickers))
                    
                    results = []
                    for s, res in snaps.items():
                        if res.daily_bar:
                            change = ((res.latest_trade.price - res.daily_bar.open) / res.daily_bar.open) * 100
                            if abs(change) >= min_diff:
                                results.append({
                                    "Тикер": s, 
                                    "Цена": res.latest_trade.price, 
                                    "Изм %": round(change, 2), 
                                    "Объем": res.daily_bar.volume
                                })
                    st.session_state.movers_df = pd.DataFrame(results).sort_values("Изм %", ascending=False)
                except Exception as e:
                    st.error(f"Ошибка скринера: {e}")

        if st.session_state.movers_df is not None:
            st.dataframe(st.session_state.movers_df, use_container_width=True, height=400)

    # --- ВКЛАДКА 2: АНАЛИЗ ---
    with tab_analysis:
        st.subheader("Подготовка данных для отправки ИИ")
        # Постоянная строка ввода
        target = st.text_input("Введите тикер (например: NVDA, TSLA, AAPL):", key="target_input").upper()
        
        if target:
            with st.spinner(f'Собираю данные по {target}...'):
                try:
                    now = datetime.now(timezone.utc)
                    # Данные для графиков
                    d_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Day, start=now-timedelta(days=30))).df
                    m_bars = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Minute, start=now-timedelta(hours=8))).df

                    if isinstance(d_bars.index, pd.MultiIndex): d_bars = d_bars.loc[target]
                    if isinstance(m_bars.index, pd.MultiIndex): m_bars = m_bars.loc[target]

                    # Визуализация данных
                    c1, c2 = st.columns(2)
                    c1.markdown("**Дневной контекст (7 дней)**")
                    c1.table(d_bars[['open', 'high', 'low', 'close']].tail(7))
                    
                    c2.markdown("**Интрадей (15 минут)**")
                    c2.table(m_bars[['open', 'close', 'volume']].tail(15))

                    # Формирование текста для копирования
                    ai_text = f"АКЦИЯ: {target}\n"
                    ai_text += f"DAILY DATA (Last 7d):\n{d_bars.tail(7).to_string()}\n\n"
                    ai_text += f"MINUTE DATA (Last 15m):\n{m_bars.tail(15).to_string()}"

                    st.divider()
                    st.subheader("📋 Данные для копирования в чат")
                    # Кнопка копирования (встроенный виджет Streamlit)
                    st.code(ai_text, language="text")
                    st.info("💡 Нажми на иконку копирования в правом верхнем углу блока выше и вставь данные в чат к ИИ.")

                except Exception as e:
                    st.error(f"Не удалось найти данные по тикеру {target}. Проверьте правильность написания.")
        else:
            st.info("Введите тикер выше, чтобы получить данные для анализа.")

else:
    st.warning("👈 Введите ваши API ключи Alpaca в боковой панели слева для начала работы.")
