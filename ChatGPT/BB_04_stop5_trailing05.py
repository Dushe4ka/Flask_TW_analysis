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
logger = logging.getLogger("BybitStopLossTrailingBot")

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
    precision = len(str(step).split('.')[1]) if '.' in str(step) else 0
    return round(qty - (qty % step), precision)


def get_position(symbol):
    """Получает текущую открытую позицию."""
    try:
        response = session.get_positions(category="linear", symbol=symbol)
        if response.get("retCode") == 0:
            for position in response["result"]["list"]:
                if float(position["size"]) > 0:
                    return position
    except Exception as e:
        logger.error(f"Ошибка получения позиции {symbol}: {e}")
    return None


def open_position_with_stop(symbol, side, dollar_value, stop_loss_percent=5):
    """Открывает позицию с изначальным стоп-лоссом."""
    try:
        entry_price = get_current_price(symbol)
        if entry_price <= 0:
            raise ValueError("Не удалось получить текущую цену.")

        min_qty, qty_step = get_min_qty_and_step(symbol)
        qty = round_qty(dollar_value / entry_price, qty_step)
        qty = max(qty, min_qty)

        # Размещаем рыночный ордер
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

            # Установка первоначального стоп-лосса
            stop_loss_price = entry_price * (1 - stop_loss_percent / 100) if side == "Buy" else \
                entry_price * (1 + stop_loss_percent / 100)

            response = session.set_trading_stop(
                category="linear",
                symbol=symbol,
                stopLoss=str(stop_loss_price),
                side=side.capitalize()
            )

            if response.get("retCode") == 0:
                logger.info(f"Установлен стоп-лосс {stop_loss_percent}% для {symbol}")
                monitor_position(symbol, entry_price, side)
            else:
                logger.error(f"Ошибка установки стоп-лосса: {response.get('retMsg')}")
        else:
            logger.error(f"Ошибка открытия позиции: {response.get('retMsg')}")

    except Exception as e:
        logger.error(f"Ошибка при открытии позиции: {e}")


def monitor_position(symbol, entry_price, side, move_to_entry_at=1.2, stop_profit_percent=1, trailing_stop_percent=0.5):
    """Мониторинг позиции и установка динамических стопов."""
    try:
        while True:
            position = get_position(symbol)
            if not position:
                logger.info(f"Позиция {symbol} закрыта. Завершаем мониторинг.")
                break

            current_price = get_current_price(symbol)
            if current_price <= 0:
                continue

            # Вычисление прибыли в процентах
            profit_percent = ((current_price - entry_price) / entry_price) * 100 if side == "Buy" else \
                             ((entry_price - current_price) / entry_price) * 100

            # Если достигнута цель 1.2%, ставим стоп-лосс на 1% прибыли и трейлинг-стоп 0.5%
            if profit_percent >= move_to_entry_at:
                new_stop_loss_price = entry_price * (1 + stop_profit_percent / 100) if side == "Buy" else \
                                      entry_price * (1 - stop_profit_percent / 100)

                trailing_stop_value = entry_price * (trailing_stop_percent / 100)

                response = session.set_trading_stop(
                    category="linear",
                    symbol=symbol,
                    stopLoss=str(new_stop_loss_price),
                    trailingStop=str(trailing_stop_value),
                    side=side.capitalize()
                )

                if response.get("retCode") == 0:
                    logger.info(f"Обновлен стоп-лосс {symbol} на {stop_profit_percent}% прибыли и трейлинг-стоп {trailing_stop_percent}%")
                    send_message_to_telegram(f"Обновлен стоп-лосс {symbol} на {stop_profit_percent}% прибыли и трейлинг-стоп {trailing_stop_percent}%")
                    break
                else:
                    logger.error(f"Ошибка обновления стопов: {response.get('retMsg')}")

            time.sleep(2)  # Пауза перед следующей проверкой

    except Exception as e:
        logger.error(f"Ошибка мониторинга позиции: {e}")


if __name__ == "__main__":
    symbol = "ACTUSDT".upper()
    side = "Sell"  # Или "Sell"
    dollar_value = 21  # Сумма сделки
    stop_loss_percent = 5  # Первичный стоп-лосс

    open_position_with_stop(symbol, side, dollar_value, stop_loss_percent)
