from flask import Flask, request, jsonify
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

# Bybit API URL
BASE_URL = "https://api.bybit.com"

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

# Функция для получения времени с сервера Bybit
def get_server_time():
    try:
        url = f"{BASE_URL}/v3/public/time"
        response = requests.get(url)
        response.raise_for_status()
        server_time = response.json().get("time", 0)
        return int(server_time)
    except Exception as e:
        logger.error(f"Ошибка при запросе времени сервера Bybit: {e}")
        send_message_to_telegram(f"Ошибка при запросе времени сервера Bybit: {e}")
        return 0

# Функция для отправки запросов к Bybit API
def send_request(endpoint, payload):
    try:
        url = f"{BASE_URL}{endpoint}"
        headers = {
            "X-BYBIT-API-KEY": key
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Ошибка при выполнении запроса к Bybit API: {e}")
        send_message_to_telegram(f"Ошибка при выполнении запроса к Bybit API: {e}")
        return None

# Функция открытия позиции
def open_position(symbol, side):
    try:
        # Получение серверного времени для выполнения запроса
        server_time = get_server_time()
        if server_time == 0:
            raise ValueError("Не удалось получить серверное время.")

        # Параметры запроса
        payload = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "order_type": "Market",
            "qty": "1",  # Пример количества контракта
            "reduce_only": False,
            "timestamp": server_time
        }

        # Отправка запроса на создание ордера
        response = send_request("/v5/order/create", payload)
        if response:
            logger.info(f"Открыта позиция {side} для {symbol}. Ответ API: {response}")
            send_message_to_telegram(f"Открыта позиция {side} для {symbol}.")
        else:
            raise ValueError("Не удалось открыть позицию.")

    except Exception as e:
        logger.error(f"Ошибка при открытии позиции для {symbol}: {e}")
        send_message_to_telegram(f"Ошибка при открытии позиции для {symbol}: {e}")

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
        Thread(target=open_position, args=(symbol, "BUY")).start()

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
