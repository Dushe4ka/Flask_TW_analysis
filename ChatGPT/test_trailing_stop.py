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

# Ваши ключи API
key = os.getenv("API_KEY")
secret = os.getenv("API_SECRET")

if not key or not secret:
    logger.error("API_KEY или API_SECRET не заданы. Проверьте файл .env.")
    exit(1)

# Создание сессии API
session = HTTP(api_key=key, api_secret=secret, testnet=False, recv_window=60000)


def get_current_price(symbol):
    """Получение текущей цены символа."""
    try:
        response = session.get_tickers(category="linear", symbol=symbol)
        if response.get("retCode") == 0:
            result = response.get("result", {}).get("list", [])
            for ticker in result:
                if ticker.get("symbol") == symbol:
                    return float(ticker.get("lastPrice", 0))
        logger.error(f"Ошибка получения цены {symbol}: {response.get('retMsg')}")
    except Exception as e:
        logger.error(f"Ошибка при получении цены {symbol}: {e}")
    return 0


def is_position_open(symbol):
    """Проверка, есть ли открытая позиция по символу."""
    try:
        response = session.get_positions(category="linear", symbol=symbol)
        if response.get("retCode") == 0:
            positions = response.get("result", {}).get("list", [])
            for position in positions:
                if position.get("symbol") == symbol and float(position.get("size", 0)) > 0:
                    logger.info(f"Позиция по {symbol} уже открыта.")
                    return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке позиции по {symbol}: {e}")
        return False


def set_trailing_stop(symbol, side, qty, entry_price, retracement_percent):
    """Установка трейлинг-стопа с использованием встроенной логики Bybit."""
    try:
        # Расчет расстояния отката (Trailing Stop)
        trailing_stop_value = entry_price * (retracement_percent / 100)

        # Направление триггера
        if side == "Buy":
            trigger_direction = 2  # Триггер активируется при снижении цены
        elif side == "Sell":
            trigger_direction = 1  # Триггер активируется при росте цены
        else:
            raise ValueError(f"Некорректное значение side: {side}")

        # Установка трейлинг-стопа
        response = session.set_trading_stop(
            category="linear",
            symbol=symbol,
            side=side.capitalize(),
            trailingStop=str(trailing_stop_value),
            triggerDirection=trigger_direction
        )

        if response.get("retCode") == 0:
            logger.info(f"Трейлинг-стоп для {symbol} успешно установлен.")
            send_message_to_telegram(f"Трейлинг-стоп для {symbol} успешно установлен.")
        else:
            logger.error(f"Ошибка установки трейлинг-стопа: {response.get('retMsg')}")
            send_message_to_telegram(f"Ошибка установки трейлинг-стопа: {response.get('retMsg')}")
    except Exception as e:
        logger.error(f"Ошибка при установке трейлинг-стопа: {e}")
        send_message_to_telegram(f"Ошибка при установке трейлинг-стопа: {e}")


def get_min_qty_and_step(symbol):
    """Получение минимального количества и шага изменения для символа."""
    try:
        response = session.get_instruments_info(category="linear", symbol=symbol)
        if response.get("retCode") == 0:
            instruments = response.get("result", {}).get("list", [])
            for instrument in instruments:
                if instrument.get("symbol") == symbol:
                    lot_size_filter = instrument.get("lotSizeFilter", {})
                    min_qty = float(lot_size_filter.get("minOrderQty", 1))
                    qty_step = float(lot_size_filter.get("qtyStep", 1))
                    return min_qty, qty_step
        logger.error(f"Ошибка получения данных для {symbol}: {response.get('retMsg')}")
    except Exception as e:
        logger.error(f"Ошибка при получении данных для {symbol}: {e}")
    return 1, 1  # Значения по умолчанию

def round_qty_to_step(qty, step):
    """Округление количества до ближайшего кратного шага."""
    return round(qty - (qty % step), len(str(step).split('.')[1]))

def open_position_with_trailing_stop(symbol, side, dollar_value, retracement_percent):
    """Открытие позиции с установкой трейлинг-стопа."""
    try:
        if is_position_open(symbol):
            logger.warning(f"Позиция по {symbol} уже открыта. Новая позиция не будет открыта.")
            return

        # Получение текущей цены
        entry_price = get_current_price(symbol)
        if entry_price <= 0:
            raise ValueError("Не удалось получить текущую цену.")

        # Расчет количества
        qty = dollar_value / entry_price

        # Получение минимального количества и шага
        min_qty, qty_step = get_min_qty_and_step(symbol)

        # Проверка и корректировка количества
        if qty < min_qty:
            logger.warning(f"Рассчитанное количество {qty} меньше минимального {min_qty}. Корректируем.")
            qty = min_qty
        qty = round_qty_to_step(qty, qty_step)
        logger.info(f"Итоговое количество для {symbol}: {qty}")

        # Открытие рыночного ордера
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side.capitalize(),
            orderType="Market",
            qty=str(qty),
            timeInForce="IOC",
            reduceOnly=False
        )

        if response.get("retCode") == 0:
            logger.info(f"Позиция {side} для {symbol} успешно открыта.")
            send_message_to_telegram(f"Позиция {side} для {symbol} успешно открыта.")
            set_trailing_stop(symbol, side, qty, entry_price, retracement_percent)
        else:
            logger.error(f"Ошибка открытия позиции: {response.get('retMsg')}")
            send_message_to_telegram(f"Ошибка открытия позиции: {response.get('retMsg')}")
    except Exception as e:
        logger.error(f"Ошибка при открытии позиции: {e}")
        send_message_to_telegram(f"Ошибка при открытии позиции: {e}")


if __name__ == "__main__":
    # Параметры сделки
    symbol = "spellusdt".upper()
    side = "Buy"
    dollar_value = 6  # Сумма сделки
    retracement_percent = 3  # Процент отката

    logger.info(f"Запуск программы для открытия позиции {symbol}.")
    open_position_with_trailing_stop(symbol, side, dollar_value, retracement_percent)
