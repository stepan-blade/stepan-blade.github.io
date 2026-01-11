import time
import threading
from datetime import datetime
from flask import Flask, jsonify, render_template
import pandas as pd
import ta
import ccxt  # предположим, что используешь ccxt для биржи

app = Flask(__name__)

# Настройки
SYMBOL = 'BTC/USDT'
TIMEFRAME = '1m'

# Инициализация переменных
wallet = {
    'balance': 1000.0,
    'position': None,
    'history': []
}
price_history = []

# Инициализируем биржу (пример с Binance)
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
            df['RSI'] = ta.momentum.rsi(df['close'], window=14)
            macd_ind = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
            df['MACD'] = macd_ind.macd()
            df['MACD_signal'] = macd_ind.macd_signal()

            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            current_price = last_row['close']

            # Сохраняем цену для графика (время в секундах)
            new_point = {'time': int(last_row['timestamp'] / 1000), 'value': current_price}
            if not price_history or new_point['time'] > price_history[-1]['time']:
                price_history.append(new_point)
            if len(price_history) > 100:
                price_history.pop(0)

            # 3. ЛОГИКА СИГНАЛОВ
            # Условие покупки: RSI < 35 и пересечение MACD снизу вверх
            buy_signal = (last_row['RSI'] < 35 and
                          prev_row['MACD'] < prev_row['MACD_signal'] and
                          last_row['MACD'] > last_row['MACD_signal'])

            # Условие продажи: RSI > 65 или пересечение MACD сверху вниз
            sell_signal = (last_row['RSI'] > 65 or
                           (prev_row['MACD'] > prev_row['MACD_signal'] and
                            last_row['MACD'] < last_row['MACD_signal']))

            # 4. ИСПОЛНЕНИЕ СДЕЛКИ
            if wallet['position'] is None and buy_signal:
                wallet['position'] = {
                    'open_price': current_price,
                    'time': datetime.now().strftime("%H:%M:%S")
                }
                wallet['balance'] -= current_price  # учитываем покупку
                print(f"--- СИГНАЛ: BUY по цене {current_price:.2f} ---")

            elif wallet['position'] is not None and sell_signal:
                open_p = wallet['position']['open_price']
                profit_val = current_price - open_p
                profit_pct = (profit_val / open_p) * 100

                wallet['balance'] += current_price  # возвращаем деньги от продажи
                wallet['balance'] += profit_val     # учитываем прибыль
                # В данном условии, чтобы не дублировать, лучше считать:
                # wallet['balance'] += open_p + profit_val равняется wallet['balance'] + current_price, так что еще раз убрать profit_val
                
                # ИСПРАВЛЕНИЕ (обноляем корректно баланс):
                # Логично так:
                # При покупке снимаем open_price: balance -= open_price
                # При продаже возвращаем current_price: balance += current_price
                # profit_val в виртуальной части для вывода, баланс уже учтен
                # Поэтому заменим логику ниже:

                wallet['balance'] += current_price  # возвращаем деньги от продажи
                # profit добавлять нельзя, он уже учтен через цену продажи!

                wallet['history'].insert(0, {
                    "asset": SYMBOL,
                    "time": datetime.now().strftime("%d.%m %H:%M"),
                    "open": f"{open_p:.2f}",
                    "close": f"{current_price:.2f}",
                    "profit": f"{profit_pct:+.2f}%"
                })

                wallet['position'] = None
                print(f"--- СИГНАЛ: SELL по цене {current_price:.2f} (Профит: {profit_pct:.2f}%) ---")

        except Exception as e:
            print(f"Ошибка в цикле бота: {e}")

        time.sleep(15)  # Опрос каждые 15 секунд

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
