import os
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# Загрузка переменных из файла .env
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

if not API_KEY or not API_SECRET:
    raise ValueError("API_KEY или API_SECRET отсутствуют в .env файле")

# Инициализация сессии
session = HTTP(
    testnet=False,  # False для боевого режима
    api_key=API_KEY,
    api_secret=API_SECRET,
    recv_window=15000  # Увеличенное окно времени
)

# Параметры торговли
USDT_AMOUNT = 10  # Сумма в USDT для открытия позиции
TRAILING_STOP_TYPE = "percent"  # Тип трейлинг-стопа: "percent" или "distance"
TRAILING_STOP_VALUE = 3  # Процент отката (3%) или расстояние (например, 0.5 USDT)
ACTIVATION_PRICE = None  # Цена активации трейлинг-стопа (опционально)
SYMBOL = "ADAUSDT"  # Торговая пара
POSITION_SIDE = "Buy"  # Покупка (лонг) или Продажа (шорт)
HEDGE_MODE = False  # Установите True, если включён режим хеджирования

try:
    # Получение информации о символе
    instruments_info = session.get_instruments_info(category="linear", symbol=SYMBOL)
    min_order_qty = float(instruments_info["result"]["list"][0]["lotSizeFilter"]["minOrderQty"])
    print(f"Минимальный объем контракта для {SYMBOL}: {min_order_qty}")

    # Получение текущей рыночной цены
    tickers_response = session.get_tickers(category="linear")
    market_price = next(
        (float(ticker["lastPrice"]) for ticker in tickers_response["result"]["list"] if ticker["symbol"] == SYMBOL),
        None
    )
    if market_price is None:
        raise ValueError(f"Цена для символа {SYMBOL} не найдена.")
    print(f"Текущая рыночная цена: {market_price}")

    # Расчёт количества контрактов
    qty = USDT_AMOUNT / market_price
    if qty < min_order_qty:
        raise ValueError(f"Рассчитанное количество ({qty}) меньше минимально допустимого ({min_order_qty}). Увеличьте сумму USDT_AMOUNT.")
    qty = round(qty, 3)
    print(f"Количество контрактов для открытия: {qty}")

    # Установка индекса позиции
    position_idx = 1 if HEDGE_MODE and POSITION_SIDE == "Buy" else 2 if HEDGE_MODE and POSITION_SIDE == "Sell" else 0

    # Открытие позиции
    order_params = {
        "category": "linear",
        "symbol": SYMBOL,
        "side": POSITION_SIDE,
        "orderType": "Market",
        "qty": str(qty),
        "timeInForce": "IOC",
        "reduceOnly": False,
    }
    if HEDGE_MODE:
        order_params["positionIdx"] = position_idx

    order_response = session.place_order(**order_params)
    print("Позиция открыта:", order_response)

    # Установка трейлинг-стопа
    if TRAILING_STOP_TYPE == "percent":
        trailing_stop_param = TRAILING_STOP_VALUE  # Значение в процентах
    elif TRAILING_STOP_TYPE == "distance":
        trailing_stop_param = TRAILING_STOP_VALUE / market_price * 100  # Перевод расстояния в проценты
    else:
        raise ValueError("Тип трейлинг-стопа должен быть 'percent' или 'distance'.")

    trailing_stop_params = {
        "category": "linear",
        "symbol": SYMBOL,
        "trailingStop": str(round(trailing_stop_param, 2)),
    }
    if HEDGE_MODE:
        trailing_stop_params["positionIdx"] = position_idx
    if ACTIVATION_PRICE:
        trailing_stop_params["triggerPrice"] = str(ACTIVATION_PRICE)

    trailing_stop_response = session.set_trading_stop(**trailing_stop_params)
    print("Трейлинг-стоп установлен:", trailing_stop_response)

except ValueError as e:
    print("Ошибка:", e)
except Exception as e:
    print("Общая ошибка:", e)
