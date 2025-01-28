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
# from open_order_tekprofit_stoploss import open_position_with_protection
from ChatGPT.test_trailing_stop import open_position_with_trailing_stop

# Параметры для открытия ордера
dollar_value = 10
retracement_percent = 2
# stop_loss_percent = 1
# take_profit_percent = 1

# Загрузка переменных окружения
load_dotenv()

# Настройка приложения Flask
app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram токен
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не задан. Проверьте файл .env.")
    exit(1)

# Список chat_id
CHAT_IDS = [1395854084, 525006772]

# API-ключи
key = os.getenv("API_KEY")
secret = os.getenv("API_SECRET")

if not key or not secret:
    logger.error("API_KEY или API_SECRET не заданы. Проверьте файл .env.")
    exit(1)

# Сессия API
session = HTTP(api_key=key, api_secret=secret, testnet=False, recv_window=10000)

# Глобальный флаг состояния сделки
is_trade_open = False


# Функция отправки сообщений в Telegram
def send_message_to_telegram(message):
    for chat_id in CHAT_IDS:
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {'chat_id': chat_id, 'text': message}
        try:
            requests.post(url, json=payload).raise_for_status()
            logger.info(f"Сообщение отправлено в чат {chat_id}")
        except requests.RequestException as e:
            logger.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")


# Форматирование книги ордеров
def format_order_book(response):
    bids = response.get('b', [])
    asks = response.get('a', [])
    return bids, asks


# Функция проверки закрытия позиции
def is_position_closed(symbol):
    global is_trade_open
    try:
        # Получаем позиции через API
        response = session.get_positions(
            category="linear",
            symbol=symbol
        )

        # Проверка, является ли ответ корректным
        if not response or 'result' not in response:
            logger.error(f"Некорректный ответ от API при проверке позиции для {symbol}: {response}")
            return False

        positions = response['result'].get('list', [])  # Извлекаем список позиций

        if isinstance(positions, list):  # Если позиции представлены списком
            for position in positions:
                if position.get('symbol') == symbol and float(position.get('size', 0)) > 0:
                    logger.info(f"Позиция для {symbol} все еще открыта: {position}")
                    return False  # Позиция все еще открыта
        else:
            logger.error(f"Неверный формат данных позиций: {positions}")

        # Если позиции не найдены или их размер равен нулю
        logger.info(f"Позиция для {symbol} закрыта.")
        return True

    except Exception as e:
        logger.error(f"Ошибка при проверке позиции для {symbol}: {e}")
        return False


# Основной анализ
def analyze_order_book(symbol):
    global is_trade_open
    end_time = datetime.now() + timedelta(hours=1)
    logger.info(f"Начат анализ для символа {symbol}. Время окончания: {end_time}")
    send_message_to_telegram(f"Начат анализ для монеты {symbol}. Время окончания: {end_time.strftime('%H:%M:%S')}")

    try:
        while datetime.now() < end_time:
            if is_trade_open:
                logger.info("Ожидание закрытия позиции.")
                while not is_position_closed(symbol):
                    time.sleep(10)  # Ждём 10 секунд перед повторной проверкой
                is_trade_open = False
                logger.info("Позиция закрыта. Анализ продолжается.")

            response = session.get_orderbook(
                category="linear",
                symbol=symbol,
                limit=50
            ).get('result')

            if not response:
                raise ValueError(f"Нет данных для символа {symbol}.")

            bids, asks = format_order_book(response)

            bid_volumes = [float(bid[1]) for bid in bids if len(bid) > 1]
            ask_volumes = [float(ask[1]) for ask in asks if len(ask) > 1]

            total_bid_volume = sum(bid_volumes)
            total_ask_volume = sum(ask_volumes)

            bid_percentage = (total_bid_volume / (
                        total_bid_volume + total_ask_volume)) * 100 if total_bid_volume + total_ask_volume > 0 else 0
            ask_percentage = (total_ask_volume / (
                        total_bid_volume + total_ask_volume)) * 100 if total_bid_volume + total_ask_volume > 0 else 0

            logger.info(f"Символ: {symbol}, Биды: {bid_percentage:.2f}%, Аски: {ask_percentage:.2f}%.")

            if bid_percentage > 85:
                send_message_to_telegram(f"Биды превышают 85% для {symbol}. Открытие позиции SELL.")
                open_position(symbol, "Sell")
                is_trade_open = True
            elif ask_percentage > 85:
                send_message_to_telegram(f"Аски превышают 85% для {symbol}. Открытие позиции BUY.")
                open_position(symbol, "Buy")
                is_trade_open = True

            time.sleep(10)

        logger.info(f"Анализ для символа {symbol} завершен. Условия не выполнены.")
        send_message_to_telegram(f"Анализ для монеты {symbol} завершен. Условия не выполнены.")

    except Exception as e:
        logger.error(f"Ошибка при анализе книги ордеров для {symbol}: {e}")
        send_message_to_telegram(f"Ошибка при анализе книги ордеров для {symbol}: {e}")


# Функция открытия позиции
def open_position(symbol, side):
    try:
        open_position_with_trailing_stop(symbol, side, dollar_value, retracement_percent)
        logger.info(f"Позиция {side} для {symbol} успешно открыта.")
    except Exception as e:
        logger.error(f"Ошибка при открытии позиции для {symbol}: {e}")


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
