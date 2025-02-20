from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP
from dotenv import load_dotenv
from pyngrok import ngrok
import requests
import logging
import os
import time
from threading import Thread
from datetime import datetime, timedelta

# Загрузка переменных окружения
load_dotenv()

# Настройка приложения Flask
app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram токен из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не задан. Проверьте файл .env.")
    exit(1)

# Жестко заданный список chat_id
CHAT_IDS = [1395854084, 525006772]

# Ваши ключи API
key = os.getenv("API_KEY")
secret = os.getenv("API_SECRET")

if not key or not secret:
    logger.error("API_KEY или API_SECRET не заданы. Проверьте файл .env.")
    exit(1)

# Создание сессии API с увеличением recv_window
session = HTTP(api_key=key, api_secret=secret, testnet=False, recv_window=10000)

# Функция отправки сообщений в Telegram
def send_message_to_telegram(message):
    for chat_id in CHAT_IDS:
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {'chat_id': chat_id, 'text': message}
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Сообщение отправлено в чат {chat_id}")
        except requests.RequestException as e:
            logger.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")

# Форматирование книги ордеров
def format_order_book(response):
    bids = response.get('b')
    asks = response.get('a')
    return bids, asks

# Функция анализа книги ордеров
def analyze_order_book(symbol):
    end_time = datetime.now() + timedelta(hours=1)
    logger.info(f"Начат анализ для символа {symbol}. Время окончания: {end_time}")
    send_message_to_telegram(f"Начат анализ для монеты {symbol}. Время окончания: {end_time.strftime('%H:%M:%S')}")

    try:
        while datetime.now() < end_time:
            response = session.get_orderbook(
                category="linear",
                symbol=symbol,
                limit=50
            ).get('result')

            if not response:
                raise ValueError(f"Нет данных для символа {symbol}.")

            bids, asks = format_order_book(response)

            # Извлечение объемов
            bid_volumes = [float(bid[1]) for bid in bids if len(bid) > 1]
            ask_volumes = [float(ask[1]) for ask in asks if len(ask) > 1]

            total_bid_volume = sum(bid_volumes)
            total_ask_volume = sum(ask_volumes)

            # Расчет процентов бидов и асков
            bid_percentage = (total_bid_volume / (total_bid_volume + total_ask_volume)) * 100 if total_bid_volume + total_ask_volume > 0 else 0
            ask_percentage = (total_ask_volume / (total_bid_volume + total_ask_volume)) * 100 if total_bid_volume + total_ask_volume > 0 else 0

            # Логирование текущих данных
            logger.info(
                f"Символ: {symbol}, Биды: {bid_percentage:.2f}%, Аски: {ask_percentage:.2f}%."
            )

            # Проверка условия для открытия позиции
            if bid_percentage > 85:
                send_message_to_telegram(f"Биды превышают 85% для {symbol}. Открытие позиции SELL.")
                open_position(symbol, "SELL")
                return
            elif ask_percentage > 85:
                send_message_to_telegram(f"Аски превышают 85% для {symbol}. Открытие позиции BUY.")
                open_position(symbol, "BUY")
                return

            time.sleep(10)

        logger.info(f"Анализ для символа {symbol} завершен. Условия не выполнены.")
        send_message_to_telegram(f"Анализ для монеты {symbol} завершен. Условия не выполнены.")

    except Exception as e:
        error_message = f"Ошибка при анализе книги ордеров для {symbol}: {e}"
        logger.error(error_message)
        send_message_to_telegram(error_message)

# Функция открытия позиции
def open_position(symbol, side):
    try:
        # Получение серверного времени
        server_time = int(time.time() * 1000)

        # Настройка параметров заказа
        order_params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": "1",
            "timeInForce": "IOC",
            "reduceOnly": False,
            "positionIdx": 0,
            "timestamp": server_time
        }

        # Отправка запроса на размещение ордера
        response = session.place_order(**order_params)
        if response.get("retCode") == 0:
            logger.info(f"Открыта позиция {side} для {symbol}. Ответ API: {response}")
            send_message_to_telegram(f"Открыта позиция {side} для {symbol}.")
            manage_position(symbol, side)
        else:
            error_msg = f"Ошибка открытия позиции {side} для {symbol}: {response.get('retMsg')}"
            logger.error(error_msg)
            send_message_to_telegram(error_msg)

    except Exception as e:
        logger.error(f"Ошибка при открытии позиции для {symbol}: {e}")
        send_message_to_telegram(f"Ошибка при открытии позиции для {symbol}: {e}")

# Функция управления позицией
def manage_position(symbol, side):
    try:
        response = session.set_trading_stop(
            category="linear",
            symbol=symbol,
            side=side,
            stop_loss=3,  # Стоп-лосс 3%
            trailing_stop=1  # Трейлинг-стоп 1%
        )
        logger.info(f"Установлен трейлинг-стоп и стоп-лосс для {symbol}. Ответ API: {response}")
        send_message_to_telegram(f"Управление позицией для {symbol} установлено: трейлинг-стоп 1%, стоп-лосс 3%.")
    except Exception as e:
        logger.error(f"Ошибка при управлении позицией для {symbol}: {e}")
        send_message_to_telegram(f"Ошибка при управлении позицией для {symbol}: {e}")

# Вебхук для получения символа
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.data.decode('utf-8').strip()

        if not data:
            logger.error("Пустое сообщение из вебхука.")
            return jsonify({'error': 'Пустое сообщение'}), 400

        symbol = data.upper()
        logger.info(f'Получен символ из вебхука: {symbol}')

        # Запускаем анализ в отдельном потоке
        Thread(target=analyze_order_book, args=(symbol,)).start()

        return jsonify({'status': 'success', 'symbol': symbol}), 200
    except Exception as e:
        logger.error(f"Ошибка в обработке вебхука: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    public_url = ngrok.connect(5000, bind_tls=True).public_url
    webhook_url = f"{public_url}/webhook"
    logger.info(f"Публичный URL вебхука: {webhook_url}")

    send_message_to_telegram(f"Сервер доступен по адресу: {webhook_url}")

    app.run(host="0.0.0.0", port=5000)