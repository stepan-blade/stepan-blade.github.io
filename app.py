import ccxt
import pandas as pd
import pandas_ta as ta
from flask import Flask, jsonify, render_template
import threading
import time
from datetime import datetime

app = Flask(__name__)

# --- НАСТРОЙКИ ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '1m'  # Анализируем поминутно для наглядности
INITIAL_BALANCE = 10000.0

# --- СОСТОЯНИЕ БОТА (В реальном проекте это хранится в БД) ---
wallet = {
    "balance": INITIAL_BALANCE,
    "position": None,  # Данные об открытой сделке
    "history": []      # Список закрытых сделок
}
price_history = []     # Для отображения графика на сайте

# Инициализация биржи (только для чтения данных)
exchange = ccxt.binance()

def trading_logic():
    """Фоновый поток: анализ и совершение виртуальных сделок"""
    global wallet, price_history
    print(f"Запуск торгового модуля для {SYMBOL}...")

    while True:
        try:
            # 1. Получаем свечи
            bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # 2. Расчет индикаторов
            df['RSI'] = ta.rsi(df['close'], length=14)
            macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
            df = pd.concat([df, macd], axis=1)
            
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            current_price = last_row['close']

            # Сохраняем цену для графика (время в секундах)
            new_point = {'time': int(last_row['timestamp'] / 1000), 'value': current_price}
            if not price_history or new_point['time'] > price_history[-1]['time']:
                price_history.append(new_point)
            if len(price_history) > 100: price_history.pop(0)

            # 3. ЛОГИКА СИГНАЛОВ
            # Условие покупки: RSI < 35 и пересечение MACD снизу вверх
            buy_signal = (last_row['RSI'] < 35 and 
                          prev_row['MACD_12_26_9'] < prev_row['MACDs_12_26_9'] and 
                          last_row['MACD_12_26_9'] > last_row['MACDs_12_26_9'])

            # Условие продажи: RSI > 65 или пересечение MACD сверху вниз
            sell_signal = (last_row['RSI'] > 65 or 
                           (prev_row['MACD_12_26_9'] > prev_row['MACDs_12_26_9'] and 
                            last_row['MACD_12_26_9'] < last_row['MACDs_12_26_9']))

            # 4. ИСПОЛНЕНИЕ СДЕЛКИ
            if wallet['position'] is None and buy_signal:
                # Входим в сделку всем балансом (условно 1 лот)
                wallet['position'] = {
                    'open_price': current_price,
                    'time': datetime.now().strftime("%H:%M:%S")
                }
                print(f"--- СИГНАЛ: BUY по цене {current_price} ---")

            elif wallet['position'] is not None and sell_signal:
                open_p = wallet['position']['open_price']
                profit_val = current_price - open_p
                profit_pct = (profit_val / open_p) * 100
                
                # Обновляем баланс
                wallet['balance'] += profit_val 
                
                # Сохраняем в историю
                wallet['history'].insert(0, {
                    "asset": SYMBOL,
                    "time": datetime.now().strftime("%d.%m %H:%M"),
                    "open": f"{open_p:.2f}",
                    "close": f"{current_price:.2f}",
                    "profit": f"{profit_pct:+.2f}%"
                })
                
                wallet['position'] = None
                print(f"--- СИГНАЛ: SELL по цене {current_price} (Профит: {profit_pct:.2f}%) ---")

        except Exception as e:
            print(f"Ошибка в цикле бота: {e}")
        
        time.sleep(15) # Опрос каждые 15 секунд

# --- МАРШРУТЫ FLASK ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    return jsonify({
        "balance": f"{wallet['balance']:.2f}",
        "status": "В сделке" if wallet['position'] else "Поиск сигнала",
        "history": wallet['history'],
        "chart_data": price_history
    })

if __name__ == '__main__':
    # Запуск торгового бота в фоновом потоке
    threading.Thread(target=trading_logic, daemon=True).start()
    # Запуск веб-сервера
    app.run(host='0.0.0.0', port=5000, debug=False)
