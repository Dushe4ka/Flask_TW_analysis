from pybit.unified_trading import HTTP
import time

# Настройки API
api_key = 'ВАШ_API_KEY'
api_secret = 'ВАШ_API_SECRET'
symbol = 'BTCUSDT'  # Торговая пара
leverage = 10  # Плечо
usdt_amount = 100  # Сумма в USDT для открытия позиции
trailing_stop_percent = 1  # Трейлинг-стоп в процентах

# Инициализация клиента Bybit
session = HTTP(
    endpoint="https://api.bybit.com",
    api_key=api_key,
    api_secret=api_secret
)

# Установка плеча
session.set_leverage(
    symbol=symbol,
    buy_leverage=leverage,
    sell_leverage=leverage
)

# Функция для получения текущей цены
def get_current_price():
    ticker = session.latest_information_for_symbol(symbol=symbol)
    return float(ticker['result'][0]['last_price'])

# Функция для расчета количества (quantity)
def calculate_quantity(usdt_amount, price):
    return usdt_amount / price

# Функция для открытия позиции
def open_position(side, quantity):
    order = session.place_active_order(
        symbol=symbol,
        side=side,
        order_type="Market",
        qty=quantity,
        time_in_force="GoodTillCancel",
        reduce_only=False,
        close_on_trigger=False
    )
    return order

# Функция для установки трейлинг-стопа
def set_trailing_stop(side):
    session.set_trading_stop(
        symbol=symbol,
        trailing_stop=trailing_stop_percent * 100,  # Bybit принимает значение в базисных пунктах
        position_idx=0 if side == "Buy" else 1
    )

# Функция для проверки позиции
def check_position():
    positions = session.my_position(symbol=symbol)
    for position in positions['result']:
        if position['size'] > 0:
            return position['side'], position['entry_price'], position['liq_price'], position['position_idx']
    return None, None, None, None

# Основной цикл
def main():
    # Получаем текущую цену
    current_price = get_current_price()
    print(f"Текущая цена {symbol}: {current_price}")

    # Рассчитываем количество (quantity)
    quantity = calculate_quantity(usdt_amount, current_price)
    print(f"Количество для открытия позиции: {quantity}")

    # Открываем длинную позицию
    order = open_position("Buy", quantity)
    print("Открыта длинная позиция:", order)

    # Устанавливаем трейлинг-стоп
    set_trailing_stop("Buy")

    # Проверяем позицию
    side, entry_price, liq_price, position_idx = check_position()
    if side:
        print(f"Текущая позиция: {side}, Цена входа: {entry_price}, Цена ликвидации: {liq_price}")

    # Ждем, пока позиция закроется по трейлинг-стопу
    print("Ожидание закрытия позиции по трейлинг-стопу...")
    while True:
        side, _, _, _ = check_position()
        if side is None:
            print("Позиция закрыта по трейлинг-стопу.")
            break
        time.sleep(1)  # Проверяем каждую секунду


if __name__ == "__main__":
    main()