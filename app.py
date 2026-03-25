
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.historical import StockHistoricalDataClient
from datetime import datetime, timedelta, timezone
import re

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(page_title="Eagle Turbo AI Terminal", layout="wide", page_icon="🚀")
st.title("🦅 Eagle AI Terminal: Turbo v5.0")

# --- СИСТЕМНЫЕ ФУНКЦИИ ---

def extract_tickers(text):
    """ТРИЗ: Извлечение тикеров из любого мусора (Finviz, TV, News)"""
    potential = re.findall(r'\b[A-Z]{1,5}\b', text)
    exclude = {'USD', 'VOL', 'LOW', 'HIGH', 'OPEN', 'CLOSE', 'P/E', 'EPS', 'CEO', 'NYSE', 'AMEX', 'NASD', 'DATE', 'TIME', 'BUY', 'SELL', 'DIV'}
    return sorted(list(set(t for t in potential if t not in exclude)))

def get_indices_stable(index_name):
    """Получение составов индексов с обходом блокировок"""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies" if index_name == "S&P 500" else "https://en.wikipedia.org/wiki/Nasdaq-100#Components"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        tables = pd.read_html(response.text)
        df = tables[0]
        col = 'Symbol' if 'Symbol' in df.columns else 'Ticker'
        return df[col].tolist()[:100]
    except Exception as e:
        st.error(f"Wiki Access Error: {e}")
        return []

def safe_get_bars(client, ticker, timeframe, start_time):
    """Надежный сбор баров (IEX Real-time)"""
    try:
        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=timeframe,
            start=start_time,
            feed='iex' # 0 минут задержки на бесплатном тарифе
        )
        data = client.get_stock_bars(req)
        if not data or data.df.empty: return pd.DataFrame()
        df = data.df
        return df.loc[ticker] if isinstance(df.index, pd.MultiIndex) else df
    except:
        return pd.DataFrame()

def fetch_turbo_package(client, ticker):
    """Сбор МАКСИМАЛЬНЫХ данных по 5 таймфреймам"""
    now = datetime.now(timezone.utc)
    with st.spinner(f"🚀 Турбо-двигатель собирает историю {ticker}..."):
        packages = {
            "MONTHLY (2Y)": {"tf": TimeFrame.Month, "days": 730},
            "DAILY (1Y)": {"tf": TimeFrame.Day, "days": 365},
            "HOURLY (2M)": {"tf": TimeFrame.Hour, "days": 60},
            "5-MINUTE (2W)": {"tf": TimeFrame(5, TimeFrameUnit.Minute), "days": 14},
            "1-MINUTE (3D)": {"tf": TimeFrame.Minute, "days": 3}
        }
        results = {}
        for label, p in packages.items():
            results[label] = safe_get_bars(client, ticker, p["tf"], now - timedelta(days=p["days"]))
        return results

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("🔐 Доступ Alpaca")
    api_key = st.text_input("API Key", value=st.secrets.get("ALPACA_API_KEY", ""), type="password")
    secret_key = st.text_input("Secret Key", value=st.secrets.get("ALPACA_SECRET_KEY", ""), type="password")
    
    st.divider()
    source_type = st.radio("Источник:", ["Умная вставка", "Индексы", "Свой список"])
    if source_type == "Индексы":
        idx_name = st.selectbox("Индекс", ["S&P 500", "NASDAQ 100"])

# --- ЛОГИКА И ИНТЕРФЕЙС ---
if api_key and secret_key:
    client = StockHistoricalDataClient(api_key, secret_key)
    tab_scan, tab_analysis, tab_turbo = st.tabs(["🔍 Скринер Лидеров", "📊 Базовый Анализ", "🚀 ТУРБО-РЕЖИМ"])

    # 1. ВКЛАДКА СКРИНЕРА
    with tab_scan:
        if source_type == "Умная вставка":
            raw_text = st.text_area("Вставь текст с Finviz/TV сюда (Ctrl+V):", height=150)
            if st.button("🚀 Извлечь тикеры и котировки"):
                st.session_state.target_tickers = extract_tickers(raw_text)
        elif source_type == "Индексы":
            if st.button("🚀 Загрузить индекс"):
                st.session_state.target_tickers = get_indices_stable(idx_name)
        
        if 'target_tickers' in st.session_state and st.session_state.target_tickers:
            snaps = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=st.session_state.target_tickers, feed='iex'))
            res_list = []
            for s, res in snaps.items():
                if res.daily_bar:
                    chg = ((res.latest_trade.price - res.daily_bar.open) / res.daily_bar.open) * 100
                    res_list.append({"Тикер": s, "Цена": res.latest_trade.price, "Изм %": round(chg, 2), "Объем": res.daily_bar.volume})
            
            st.session_state.last_df = pd.DataFrame(res_list).sort_values("Изм %", ascending=False)
            st.dataframe(st.session_state.last_df, use_container_width=True)
            
            if st.button("📦 Сформировать МЕГА-ОТЧЕТ ПО ПУЛУ"):
                report = "--- BATCH REPORT (Daily+Min) ---\n\n"
                for t in st.session_state.target_tickers[:10]:
                    d = safe_get_bars(client, t, TimeFrame.Day, datetime.now(timezone.utc)-timedelta(days=30))
                    report += f"[{t}]\n{d.tail(10).to_string()}\n\n"
                st.code(report)

    # 2. ВКЛАДКА БАЗОВОГО АНАЛИЗА
    with tab_analysis:
        target = st.text_input("Быстрый тикер:", key="base_t").upper()
        if target:
            d = safe_get_bars(client, target, TimeFrame.Day, datetime.now(timezone.utc)-timedelta(days=30))
            st.write(f"Последние данные по {target}")
            st.dataframe(d.tail(10))

    # 3. ВКЛАДКА ТУРБО-РЕЖИМ (САМАЯ МОЩНАЯ)
    with tab_turbo:
        st.subheader("🔥 Глубокий анализ (1 год истории + 5 таймфреймов)")
        t_target = st.text_input("Введите тикер для ТУРБО-СБОРА:", key="turbo_t").upper()
        
        if st.button("🚀 ЗАПУСТИТЬ ТУРБО-АНАЛИЗ", use_container_width=True):
            if t_target:
                data = fetch_turbo_package(client, t_target)
                inv_link = f"https://www.investing.com/search/?q={t_target}"
                
                # Построение ТУРБО-ОТЧЕТА
                turbo_report = f"--- TURBO DATA PACKAGE: {t_target} ---\n"
                turbo_report += f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                turbo_report += f"Visual Link: {inv_link}\n\n"
                
                for label, df in data.items():
                    with st.expander(f"Детали {label}"):
                        st.dataframe(df.tail(15), use_container_width=True)
                    turbo_report += f"[{label}]\n{df.tail(10).to_string()}\n\n"
                
                # ВЫВОД ДЛЯ ИИ
                st.divider()
                st.subheader("📋 ШАГ 1: Скопируй Турбо-Данные")
                st.code(turbo_report, language="text")
                
                st.subheader("📋 ШАГ 2: Скопируй Промпт для Аналитика")
                ai_prompt = f"""
РОЛЬ: Ты Senior Quant & Portfolio Manager.
ЗАДАНИЕ: Проанализируй тикер {t_target} на основе приложенных TURBO-данных.
1. Фрактальный анализ: Сопоставь тренды Monthly -> Daily -> Minute. Где точки разворота?
2. Внешние факторы: Учти корреляцию с SPY/QQQ и последние новости по {t_target}.
3. Паттерны: Перейди по ссылке {inv_link} и проверь наличие фигур 'Голова-Плечи', 'Флаг' или 'Треугольник'.
4. План: Дай Sentiment, Точку входа (Limit), Стоп-лосс и Тейк-профит.
                """
                st.code(ai_prompt, language="text")
                
                st.markdown(f"🔗 **[Открыть график {t_target} на Investing.com]({inv_link})**")
            else:
                st.warning("Введите тикер.")
else:
    st.info("Введите API ключи Alpaca.")
