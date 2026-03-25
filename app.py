import streamlit as st
import pandas as pd
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone

# 1. Настройка внешнего вида сайта
st.set_page_config(page_title="AI Trading Terminal", layout="wide")
st.title("📈 Мой Биржевой Терминал")

# 2. Боковая панель для настроек
st.sidebar.header("Настройки доступа")
api_key = st.sidebar.text_input("Alpaca API Key", type="password")
secret_key = st.sidebar.text_input("Alpaca Secret Key", type="password")

index_choice = st.sidebar.selectbox("Что сканируем?", ["S&P 500", "NASDAQ 100"])
min_diff = st.sidebar.slider("Минимальное изменение цены (%)", 0.0, 5.0, 1.5)

# Функция для получения списка тикеров
@st.cache_data # Чтобы не качать список каждый раз заново
def get_tickers(choice):
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies" if choice == "S&P 500" else "https://en.wikipedia.org/wiki/Nasdaq-100#Components"
    tables = pd.read_html(url)
    df = tables[0]
    col = 'Symbol' if 'Symbol' in df.columns else 'Ticker'
    return df[col].tolist()

# 3. Основная логика
if api_key and secret_key:
    try:
        client = StockHistoricalDataClient(api_key, secret_key)
        
        if st.sidebar.button("🔍 Найти активные акции"):
            tickers = get_tickers(index_choice)[:100] # Берем первые 100 для скорости
            st.write(f"Сканирую рынок... ({len(tickers)} инструментов)")
            
            snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=tickers))
            results = []
            for s, res in snaps.items():
                if res.daily_bar:
                    change = ((res.latest_trade.price - res.daily_bar.open) / res.daily_bar.open) * 100
                    if abs(change) >= min_diff:
                        results.append({"Тикер": s, "Цена": res.latest_trade.price, "Изм %": round(change, 2), "Объем": res.daily_bar.volume})
            
            if results:
                st.subheader("Лидеры движения")
                st.dataframe(pd.DataFrame(results).sort_values("Изм %", ascending=False), use_container_width=True)
            else:
                st.info("Нет акций с таким изменением цены.")

        st.divider()
        
        # Блок подготовки данных для ИИ
        target = st.text_input("Введите тикер для анализа (например, NVDA):").upper()
        if target:
            now = datetime.now(timezone.utc)
            # Дневные данные
            d_req = StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Day, start=now-timedelta(days=30))
            d_bars = client.get_stock_bars(d_req).df
            # Минутные данные
            m_req = StockBarsRequest(symbol_or_symbols=target, timeframe=TimeFrame.Minute, start=now-timedelta(hours=8))
            m_bars = client.get_stock_bars(m_req).df

            if isinstance(d_bars.index, pd.MultiIndex): d_bars = d_bars.loc[target]
            if isinstance(m_bars.index, pd.MultiIndex): m_bars = m_bars.loc[target]

            st.subheader(f"Данные по {target}")
            c1, c2 = st.columns(2)
            c1.write("Дневной график (7 дней)")
            c1.table(d_bars[['open', 'high', 'low', 'close']].tail(7))
            c2.write("Минутный график (10 мин)")
            c2.table(m_bars[['open', 'close', 'volume']].tail(10))

            # Поле для копирования в чат ИИ
            ai_output = f"ДАННЫЕ ДЛЯ ИИ ПО {target}\n\nDAILY:\n{d_bars.tail(7).to_string()}\n\nMINUTE:\n{m_bars.tail(15).to_string()}"
            st.text_area("Скопируй это и отправь программисту-аналитику (мне):", ai_output, height=250)

    except Exception as e:
        st.error(f"Ошибка: {e}")
else:
    st.warning("👈 Введите API ключи в панели слева.")
