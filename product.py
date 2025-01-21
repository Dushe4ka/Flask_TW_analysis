from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP
from dotenv import load_dotenv
from pyngrok import ngrok
import requests
import os
import logging

# Загрузка переменных окружения
load_dotenv()

# Настройка приложения Flask
app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram токен и chat_id из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
    logger.error("TELEGRAM_BOT_TOKEN или CHAT_ID не заданы. Проверьте файл .env.")
    exit(1)

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
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {'chat_id': CHAT_ID, 'text': message}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.ok
    except requests.RequestException as e:
        logger.error(f"Ошибка при отправке сообщения в Telegram: {e}")
        return False

# Форматирование книги ордеров
def format_order_book(response):
    bids = response.get('b', [])
    asks = response.get('a', [])
    return bids, asks

# Проверка объемов бидов и асков
def check_order_book(symbol):
    try:
        if not symbol:
            logger.error("Символ не задан.")
            return

        logger.info(f'Проверка книги ордеров для символа: {symbol}')
        response = session.get_orderbook(
            category="spot",
            symbol=symbol,
            limit=50
        ).get('result')

        if not response:
            logger.warning(f'Нет данных для символа {symbol}.')
            return

        bids, asks = format_order_book(response)

        # Извлекаем объемы бидов и асков
        bid_volumes = [float(bid[1]) for bid in bids if bid[1] != '0']
        ask_volumes = [float(ask[1]) for ask in asks if ask[1] != '0']

        total_bid_volume = sum(bid_volumes)
        total_ask_volume = sum(ask_volumes)

        if total_bid_volume + total_ask_volume == 0:
            logger.info(f'Объем ордеров для символа {symbol} равен нулю.')
            return

        # Рассчитываем проценты
        bid_percentage = (total_bid_volume / (total_bid_volume + total_ask_volume)) * 100
        ask_percentage = (total_ask_volume / (total_bid_volume + total_ask_volume)) * 100

        # Логируем проценты бидов и асков
        logger.info(f'Для символа {symbol}: объем бидов {bid_percentage:.2f}%, объем асков {ask_percentage:.2f}%.')

        # Отправляем уведомление в Telegram
        if bid_percentage > 85:
            message = f"Для символа {symbol} объем бидов превышает 85% ({bid_percentage:.2f}%)."
            logger.info(message)
            send_message_to_telegram(message)
        elif ask_percentage > 85:
            message = f"Для символа {symbol} объем асков превышает 85% ({ask_percentage:.2f}%)."
            logger.info(message)
            send_message_to_telegram(message)

    except Exception as e:
        logger.error(f"Ошибка при проверке книги ордеров для {symbol}: {e}")

# Вебхук для получения символов
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Получаем сообщение в сыром формате
        data = request.data.decode('utf-8').strip()

        if not data:
            logger.error("Пустое сообщение из вебхука.")
            return jsonify({'error': 'Пустое сообщение'}), 400

        # Преобразуем сообщение в верхний регистр
        symbol = data.upper()
        logger.info(f'Получен символ из вебхука: {symbol}')

        # Проверяем книгу ордеров для указанного символа
        check_order_book(symbol)

        return jsonify({'status': 'success'}), 200
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
