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

# Ваши ключи API из переменных окружения
key = os.getenv("API_KEY")
secret = os.getenv("API_SECRET")

if not key or not secret:
    logger.error("API_KEY или API_SECRET не заданы. Проверьте файл .env.")
    exit(1)

# Создание сессии API
session = HTTP(api_key=key, api_secret=secret, testnet=False)

# Функция отправки сообщений в Telegram
def send_message_to_telegram(message):
    success = True
    for chat_id in CHAT_IDS:
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {'chat_id': chat_id, 'text': message}
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Сообщение отправлено в чат {chat_id}")
        except requests.RequestException as e:
            logger.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")
            success = False
    return success

# Функция проверки корректности символа
def is_symbol_valid(symbol):
    try:
        # Проверяем, доступна ли книга ордеров для символа
        response = session.get_orderbook(
            category="linear",
            symbol=symbol,
            limit=1
        )
        if 'result' in response and response['result']:
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке символа {symbol}: {e}")
        return False

# Форматирование книги ордеров
def format_order_book(response):
    bids = response.get('b', [])
    asks = response.get('a', [])
    return bids, asks

# Функция открытия фьючерсной позиции
def open_futures_position(symbol, side):
    try:
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=1  # Пример количества, уточните по вашим требованиям
        )
        logger.info(f"Открыта позиция: {side} для {symbol}. Ответ API: {response}")
        send_message_to_telegram(f"Успешно открыта позиция: {side} для монеты {symbol}.")
    except Exception as e:
        logger.error(f"Ошибка при открытии позиции для {symbol}: {e}")
        send_message_to_telegram(f"Ошибка при открытии позиции для монеты {symbol}: {e}")

# Функция анализа книги ордеров
def analyze_order_book(symbol):
    end_time = datetime.now() + timedelta(hours=1)
    logger.info(f"Начат анализ для символа {symbol}. Время окончания: {end_time}")

    send_message_to_telegram(f"Начат анализ для монеты {symbol}. Время окончания: {end_time.strftime('%H:%M:%S')}")

    while datetime.now() < end_time:
        try:
            response = session.get_orderbook(
                category="spot",
                symbol=symbol,
                limit=50
            ).get('result')

            if not response:
                logger.warning(f'Нет данных для символа {symbol}. Пропуск анализа.')
                time.sleep(5)
                continue

            bids, asks = format_order_book(response)

            bid_volumes = [float(bid[1]) for bid in bids if bid[1] != '0']
            ask_volumes = [float(ask[1]) for ask in asks if ask[1] != '0']

            total_bid_volume = sum(bid_volumes)
            total_ask_volume = sum(ask_volumes)

            if total_bid_volume + total_ask_volume == 0:
                logger.info(f'Объем ордеров для символа {symbol} равен нулю. Пропуск анализа.')
                time.sleep(5)
                continue

            bid_percentage = (total_bid_volume / (total_bid_volume + total_ask_volume)) * 100
            ask_percentage = (total_ask_volume / (total_bid_volume + total_ask_volume)) * 100

            logger.info(
                f"Символ: {symbol}, Биды: {bid_percentage:.2f}%, Аски: {ask_percentage:.2f}%."
            )

            # Условия для открытия позиции
            if bid_percentage > 85:
                open_futures_position(symbol, "BUY")
                return
            elif ask_percentage > 85:
                open_futures_position(symbol, "SELL")
                return

        except Exception as e:
            logger.error(f"Ошибка при анализе книги ордеров для {symbol}: {e}")

        time.sleep(5)

    # Завершение анализа без выполнения условий
    logger.info(f"Анализ для символа {symbol} завершен. Условия не выполнены.")
    send_message_to_telegram(f"Анализ для монеты {symbol} завершен. Условия не выполнены.")

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

        # Проверяем валидность символа
        if not is_symbol_valid(symbol):
            logger.error(f"Неверное название монеты: {symbol}")
            send_message_to_telegram(f"Неверное название монеты: {symbol}. Анализ не начат.")
            return jsonify({'error': f'Неверное название монеты: {symbol}'}), 400

        # Запускаем анализ в отдельном потоке
        Thread(target=analyze_order_book, args=(symbol,)).start()

        return jsonify({'status': 'success', 'symbol': symbol}), 200
    except Exception as e:
        logger.error(f"Ошибка в обработке вебхука: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    # Запуск ngrok туннеля
    public_url = ngrok.connect(5000, bind_tls=True).public_url
    webhook_url = f"{public_url}/webhook"
    logger.info(f"Публичный URL вебхука: {webhook_url}")

    # Отправка URL в Telegram
    message = f"Сервер доступен по адресу: {webhook_url}"
    send_message_to_telegram(message)

    # Запуск Flask сервера
    app.run(host="0.0.0.0", port=5000)
