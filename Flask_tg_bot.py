from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

# Замените на ваш токен бота и chat_id
TELEGRAM_BOT_TOKEN = '7642372695:AAHhFAydBvPUyplplcMfPa9U_nh0CWVLyy8'
CHAT_ID = '1395854084'


def send_message_to_telegram(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': CHAT_ID,
        'text': message
    }
    response = requests.post(url, json=payload)
    return response.ok


@app.route('/webhook', methods=['POST'])
def webhook():
    # Получаем данные из запроса
    data = request.json
    if data:
        # Преобразование данных в строку JSON для отправки и вывода в консоль
        json_message = json.dumps(data, indent=4)

        # Выводим сообщение в консоль
        print("Received webhook:")
        print(json_message)

        # Отправляем сообщение в Telegram
        if send_message_to_telegram(json_message):
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'failed to send message'}), 500

    return jsonify({'status': 'no data'}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)