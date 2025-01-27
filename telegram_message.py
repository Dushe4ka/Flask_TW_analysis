import requests
import os
from dotenv import load_dotenv
import logging
# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Telegram токен из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Жестко заданный список chat_id
CHAT_IDS = [1395854084, 525006772]


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