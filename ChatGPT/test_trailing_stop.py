import time
import logging
import os
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
from telegram_message import send_message_to_telegram

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BybitTrailingStopBot")

# Получение API-ключей
key = os.getenv("API_KEY")
secret = os.getenv("API_SECRET")

if not key or not secret:
    logger.error("API_KEY или API_SECRET не заданы. Проверьте файл .env.")
    exit(1)

# Создание сессии API
session = HTTP(api_key=key, api_secret=secret, testnet=False, recv_window=60000)


def get_current_price(symbol):
    """Получает текущую цену символа."""
    try:
        response = session.get_tickers(category="linear", symbol=symbol)
        if response.get("retCode") == 0:
            return float(response["result"]["list"][0]["lastPrice"])
    except Exception as e:
        logger.error(f"Ошибка получения цены {symbol}: {e}")
    return 0


def get_min_qty_and_step(symbol):
    """Получает минимальное количество и шаг изменения для символа."""
    try:
        response = session.get_instruments_info(category="linear", symbol=symbol)
        if response.get("retCode") == 0:
            instrument = response["result"]["list"][0]
            return float(instrument["lotSizeFilter"]["minOrderQty"]), float(instrument["lotSizeFilter"]["qtyStep"])
    except Exception as e:
        logger.error(f"Ошибка получения данных {symbol}: {e}")
    return 1, 1  # Значения по умолчанию


def round_qty(qty, step):
    """Округляет количество до ближайшего шага."""
    return round(qty - (qty % step), len(str(step).split('.')[1]))


def get_position(symbol):
    """Получает текущую открытую позицию и ждет обновления в API."""
    try:
        for _ in range(5):  # Пытаемся 5 раз получить данные (с задержкой)
            response = session.get_positions(category="linear", symbol=symbol)
            if response.get("retCode") == 0:
                positions = response["result"]["list"]
                for position in positions:
                    if float(position["size"]) > 0:
                        logger.info(f"Позиция найдена: {position}")
                        return position
            time.sleep(2)  # Ждем обновления API
    except Exception as e:
        logger.error(f"Ошибка получения позиции {symbol}: {e}")
    return None


def open_position_manage(symbol, side, dollar_value, trailing_stop_percent=2):
    """Открывает позицию с трейлинг-стопом."""
    try:
        entry_price = get_current_price(symbol)
        if entry_price <= 0:
            raise ValueError("Не удалось получить текущую цену.")

        min_qty, qty_step = get_min_qty_and_step(symbol)
        qty = round_qty(dollar_value / entry_price, qty_step)
        qty = max(qty, min_qty)

        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side.capitalize(),
            orderType="Market",
            qty=str(qty),
            timeInForce="IOC"
        )

        if response.get("retCode") == 0:
            logger.info(f"Открыта позиция {side} {qty} {symbol} по {entry_price}")
            send_message_to_telegram(f"Открыта позиция {side} {qty} {symbol} по {entry_price}")
            set_trailing_stop(symbol, side, entry_price, trailing_stop_percent)
        else:
            logger.error(f"Ошибка открытия позиции: {response.get('retMsg')}")
    except Exception as e:
        logger.error(f"Ошибка при открытии позиции: {e}")


def set_trailing_stop(symbol, side, entry_price, trailing_stop_percent):
    """Устанавливает трейлинг-стоп."""
    try:
        trailing_stop_value = entry_price * (trailing_stop_percent / 100)
        trigger_direction = 2 if side == "Buy" else 1

        response = session.set_trading_stop(
            category="linear",
            symbol=symbol,
            side=side.capitalize(),
            trailingStop=str(trailing_stop_value),
            triggerDirection=trigger_direction
        )

        if response.get("retCode") == 0:
            logger.info(f"Установлен трейлинг-стоп {trailing_stop_percent}% для {symbol}")
        else:
            logger.error(f"Ошибка установки трейлинг-стопа: {response.get('retMsg')}")
    except Exception as e:
        logger.error(f"Ошибка установки трейлинг-стопа: {e}")


def update_trailing_stop(symbol, move_to_entry_at=1, follow_distance=1):
    """Обновляет трейлинг-стоп только при росте прибыли на 1% и корректно работает для Buy и Sell."""
    try:
        time.sleep(2)  # Ждем обновления позиции в API
        position = get_position(symbol)
        if not position:
            logger.warning(f"Нет открытой позиции по {symbol}, трейлинг-стоп не обновляется.")
            return

        entry_price = float(position.get("avgPrice", 0))
        if entry_price == 0:
            logger.error(f"API не вернул avgPrice (цену входа) для {symbol}")
            return

        side = position["side"]
        highest_price = entry_price  # Для Buy — максимальная достигнутая цена
        lowest_price = entry_price  # Для Sell — минимальная достигнутая цена
        last_stop_price = None  # Изначально нет стоп-цены

        logger.info(f"Мониторинг трейлинг-стопа {symbol}, вход: {entry_price}")

        while True:
            position = get_position(symbol)  # Проверяем, открыта ли позиция
            if not position:
                logger.info(f"Позиция {symbol} закрыта. Остановка трейлинг-стопа.")
                break  # Выход из цикла, если позиция закрыта

            current_price = get_current_price(symbol)
            if current_price <= 0:
                logger.warning(f"Не удалось получить цену {symbol}")
                continue

            # Вычисляем процент прибыли
            profit_percent = ((current_price - entry_price) / entry_price) * 100 if side == "Buy" else ((entry_price - current_price) / entry_price) * 100

            if profit_percent >= move_to_entry_at:
                # Логика для Buy и Sell:
                if side == "Buy":
                    highest_price = max(highest_price, current_price)  # Фиксируем новый максимум
                    new_stop_price = highest_price * (1 - follow_distance / 100)  # Стоп-лосс идет вверх

                elif side == "Sell":
                    lowest_price = min(lowest_price, current_price)  # Фиксируем новый минимум
                    new_stop_price = lowest_price * (1 + follow_distance / 100)  # Стоп-лосс идет вниз

                # Проверка, что новый стоп-лосс выше текущего (для Buy) или ниже (для Sell)
                if last_stop_price is not None:
                    if side == "Buy" and new_stop_price <= last_stop_price:
                        logger.warning(f"Пропущено обновление трейлинг-стопа: {new_stop_price} ниже предыдущего {last_stop_price}")
                        continue
                    if side == "Sell" and new_stop_price >= last_stop_price:
                        logger.warning(f"Пропущено обновление трейлинг-стопа: {new_stop_price} выше предыдущего {last_stop_price}")
                        continue

                # Устанавливаем трейлинг-стоп
                response = session.set_trading_stop(
                    category="linear",
                    symbol=symbol,
                    stopLoss=str(new_stop_price),
                    side=side.capitalize()
                )

                if response.get("retCode") == 0:
                    logger.info(f"Обновлен трейлинг-стоп {symbol} на {new_stop_price}")
                    last_stop_price = new_stop_price  # Обновляем стоп-цену
                else:
                    logger.error(f"Ошибка обновления стоп-лосса: {response.get('retMsg')}")

            time.sleep(5)  # Пауза перед повторной проверкой

    except Exception as e:
        logger.error(f"Ошибка обновления трейлинг-стопа: {e}")


if __name__ == "__main__":
    symbol = "Jasmyusdt".upper()
    side = "Sell"
    dollar_value = 6  # Сумма сделки
    trailing_stop_percent = 1  # Изначальный трейлинг-стоп 2%

    open_position_manage(symbol, side, dollar_value, trailing_stop_percent)

    # Начинаем мониторинг цены и динамически обновляем стоп-лосс
    update_trailing_stop(symbol, move_to_entry_at=1, follow_distance=1)
