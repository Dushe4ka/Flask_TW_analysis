import time
from pybit.unified_trading import HTTP
from dotenv import load_dotenv
import logging
import os
from telegram_message import send_message_to_telegram

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BybitTest")

# Ваши ключи API
key = os.getenv("API_KEY")
secret = os.getenv("API_SECRET")

if not key or not secret:
    logger.error("API_KEY или API_SECRET не заданы. Проверьте файл .env.")
    exit(1)

# Создание сессии API с реальными ключами
session = HTTP(api_key=key, api_secret=secret, testnet=False, recv_window=60000)

# Функция для получения текущей цены монеты
def get_current_price(symbol):
    try:
        response = session.get_tickers(category="linear", symbol=symbol)
        if response.get("retCode") == 0:
            result = response.get("result", {}).get("list", [])
            for ticker in result:
                if ticker.get("symbol") == symbol:
                    price = float(ticker.get("lastPrice", 0))
                    logger.info(f"Текущая цена {symbol}: {price} USDT")
                    return price
            logger.error(f"Тикер для {symbol} не найден в ответе.")
            return 0
        else:
            logger.error(f"Ошибка получения цены {symbol}: {response.get('retMsg')}")
            return 0
    except Exception as e:
        logger.error(f"Ошибка при получении цены {symbol}: {e}")
        return 0

# Функция для получения минимального значения qty и шага qty
def get_qty_limits(symbol):
    try:
        response = session.get_instruments_info(category="linear")
        if response.get("retCode") == 0:
            instruments = response.get("result", {}).get("list", [])
            for instrument in instruments:
                if instrument.get("symbol") == symbol:
                    lot_size_filter = instrument.get("lotSizeFilter", {})
                    min_qty = float(lot_size_filter.get("minOrderQty", 1))
                    step_size = float(lot_size_filter.get("qtyStep", 1))
                    logger.info(f"Минимальное значение qty для {symbol}: {min_qty}, шаг qty: {step_size}")
                    return min_qty, step_size
        else:
            logger.error(f"Ошибка получения информации о символе {symbol}: {response.get('retMsg')}")
    except Exception as e:
        logger.error(f"Ошибка при получении ограничений qty для {symbol}: {e}")
    return 1, 1

# Функция округления qty до шага
def round_qty(qty, step_size):
    return round(qty - (qty % step_size), len(str(step_size).split('.')[1]))

# Функция для проверки, есть ли открытая позиция по символу
def is_position_open(symbol):
    try:
        response = session.get_positions(category="linear", symbol=symbol)
        if response.get("retCode") == 0:
            positions = response.get("result", {}).get("list", [])
            for position in positions:
                if position.get("symbol") == symbol and float(position.get("size", 0)) > 0:
                    logger.info(f"Позиция по {symbol} уже открыта.")
                    send_message_to_telegram(f"Позиция по {symbol} уже открыта.")
                    return True
            return False
        else:
            logger.error(f"Ошибка получения позиций для {symbol}: {response.get('retMsg')}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при проверке позиций для {symbol}: {e}")
        return False

# Функция для установки стоп-лосса и тейк-профита
def set_stop_loss_and_take_profit(symbol, qty, entry_price, side, stop_loss_percent, take_profit_percent):
    try:
        if side == "Buy":  # Логика для Long
            stop_loss_price = entry_price * (1 - (stop_loss_percent / 100))
            take_profit_price = entry_price * (1 + (take_profit_percent / 100))
        elif side == "Sell":  # Логика для Short
            stop_loss_price = entry_price * (1 + (stop_loss_percent / 100))
            take_profit_price = entry_price * (1 - (take_profit_percent / 100))
        else:
            raise ValueError(f"Некорректное значение side: {side}")

        # Установка стоп-лосса
        stop_loss_response = session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell" if side == "Buy" else "Buy",  # Закрытие позиции
            orderType="Market",
            qty=str(qty),
            triggerBy="LastPrice",
            reduceOnly=True,
            closeOnTrigger=True,
            triggerPrice=str(stop_loss_price),
            triggerDirection=2 if side == "Buy" else 1  # Направление триггера
        )
        if stop_loss_response.get("retCode") == 0:
            logger.info(f"Успешно установлен стоп-лосс для {symbol} на {stop_loss_price} USDT.")
            send_message_to_telegram(f"Успешно установлен стоп-лосс для {symbol} на {stop_loss_price} USDT.")
        else:
            logger.error(f"Ошибка установки стоп-лосса: {stop_loss_response.get('retMsg')}")

        # Установка тейк-профита
        take_profit_response = session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell" if side == "Buy" else "Buy",  # Закрытие позиции
            orderType="Market",
            qty=str(qty),
            triggerBy="LastPrice",
            reduceOnly=True,
            closeOnTrigger=True,
            triggerPrice=str(take_profit_price),
            triggerDirection=1 if side == "Buy" else 2  # Направление триггера
        )
        if take_profit_response.get("retCode") == 0:
            logger.info(f"Успешно установлен тейк-профит для {symbol} на {take_profit_price} USDT.")
            send_message_to_telegram(f"Успешно установлен тейк-профит для {symbol} на {take_profit_price} USDT.")
        else:
            logger.error(f"Ошибка установки тейк-профита: {take_profit_response.get('retMsg')}")

    except Exception as e:
        logger.error(f"Ошибка при установке защитных ордеров: {e}")

# Функция для открытия позиции
def open_position_with_protection(symbol, side, dollar_value, stop_loss_percent, take_profit_percent):
    try:
        # Проверка, есть ли уже открытая позиция по символу
        if is_position_open(symbol):
            logger.warning(f"Позиция по {symbol} уже открыта. Новая позиция не будет открыта.")
            send_message_to_telegram(f"Позиция по {symbol} уже открыта. Новая позиция не будет открыта.")
            return

        side = side.capitalize()
        if side not in ["Buy", "Sell"]:
            raise ValueError(f"Некорректное значение side: {side}")

        # Получение текущей цены символа
        entry_price = get_current_price(symbol)
        if entry_price <= 0:
            raise ValueError("Не удалось получить цену символа для расчёта qty.")

        # Расчёт количества
        qty = dollar_value / entry_price
        min_qty, step_size = get_qty_limits(symbol)

        # Проверка и округление qty
        if qty < min_qty:
            qty = min_qty
            logger.warning(f"Количество скорректировано до минимального значения: {qty}")
        qty = round_qty(qty, step_size)
        logger.info(f"Рассчитанное и округлённое количество для {symbol}: {qty}")

        # Размещение ордера
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            timeInForce="IOC",
            reduceOnly=False
        )
        if response.get("retCode") == 0:
            logger.info(f"Успешно открыта позиция {side} для {symbol}. Ответ API: {response}")
            send_message_to_telegram(f"Успешно открыта позиция {side} для {symbol}. Ответ API: {response}")
            set_stop_loss_and_take_profit(symbol, qty, entry_price, side, stop_loss_percent, take_profit_percent)
        else:
            logger.error(f"Ошибка открытия позиции {side} для {symbol}: {response.get('retMsg')}")
            send_message_to_telegram(f"Ошибка открытия позиции {side} для {symbol}: {response.get('retMsg')}")

    except Exception as e:
        logger.error(f"Ошибка при открытии позиции для {symbol}: {e}")


# Основной тест программы
if __name__ == "__main__":
    symbol = "1000TOSHIUSDT"          # Символ
    side = "Sell"                # Сторона сделки
    dollar_value = 10            # Сумма сделки в долларах
    stop_loss_percent = 1       # Процент для стоп-лосса
    take_profit_percent = 1     # Процент для тейк-профита

    logger.info(f"Открытие позиции на {dollar_value} USD для {symbol} с защитными ордерами.")
    open_position_with_protection(symbol, side, dollar_value, stop_loss_percent, take_profit_percent)
