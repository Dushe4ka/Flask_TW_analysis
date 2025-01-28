import os
import logging
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

def calculate_activation_price(entry_price, retracement_percent, side):
    """Расчет динамической цены активации на основе процента отката."""
    if side == "Buy":
        return entry_price * (1 + retracement_percent / 100)
    elif side == "Sell":
        return entry_price * (1 - retracement_percent / 100)
    else:
        raise ValueError(f"Некорректное значение side: {side}")

def set_trailing_stop_by_percentage(symbol, side, qty, entry_price, retracement_percent):
    """Установка трейлинг-стопа с учетом направления позиции (Buy/Sell)."""
    try:
        # Получение текущей рыночной цены
        current_price = get_current_price(symbol)
        if current_price <= 0:
            raise ValueError("Не удалось получить текущую цену для трейлинг-стопа.")

        # Расчет расстояния отката
        retracement_distance = current_price * (retracement_percent / 100)

        # Логика для шорт-позиции (Sell) и лонг-позиции (Buy)
        if side == "Buy":
            trigger_price = current_price - retracement_distance
            trigger_direction = 2  # Триггер срабатывает при падении цены
        elif side == "Sell":
            trigger_price = current_price + retracement_distance
            trigger_direction = 1  # Триггер срабатывает при росте цены
        else:
            raise ValueError(f"Некорректное значение side: {side}")

        # Проверка триггерной цены
        if (side == "Sell" and trigger_price <= current_price) or (side == "Buy" and trigger_price >= current_price):
            raise ValueError(
                f"Некорректная триггерная цена {trigger_price} для {side}-позиции при текущей цене {current_price}."
            )

        # Размещение трейлинг-стопа
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell" if side == "Buy" else "Buy",  # Закрытие позиции
            orderType="Market",
            qty=str(qty),
            triggerBy="LastPrice",
            reduceOnly=True,
            closeOnTrigger=True,
            triggerPrice=str(trigger_price),
            trailingStop=str(retracement_distance),
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
    """Получение минимального количества и шага количества для символа."""
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
    """Округление количества до ближайшего допустимого шага."""
    return round(qty - (qty % step), len(str(step).split('.')[1]))

def open_position_with_trailing_stop(symbol, side, dollar_value, retracement_percent):
    """Открытие позиции с динамической ценой активации и установкой трейлинг-стопа."""
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

            # Динамический расчет цены активации
            activation_price = calculate_activation_price(entry_price, retracement_percent, side)
            logger.info(f"Цена активации для {symbol}: {activation_price}")

            # Установка трейлинг-стопа
            set_trailing_stop_by_percentage(symbol, side, qty, activation_price, retracement_percent)
        else:
            logger.error(f"Ошибка открытия позиции: {response.get('retMsg')}")
            send_message_to_telegram(f"Ошибка открытия позиции: {response.get('retMsg')}")
    except Exception as e:
        logger.error(f"Ошибка при открытии позиции: {e}")
        send_message_to_telegram(f"Ошибка при открытии позиции: {e}")


if __name__ == "__main__":
    # Параметры сделки
    symbol = "ACHUSDT"
    side = "Buy"
    dollar_value = 6
    retracement_percent = 2 # Опционально

    logger.info(f"Запуск программы для открытия позиции {symbol}.")
    open_position_with_trailing_stop(symbol, side, dollar_value, retracement_percent)
