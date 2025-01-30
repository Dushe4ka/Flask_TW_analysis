import logging
import os
import time
from decimal import Decimal, ROUND_HALF_UP
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
from telegram_message import send_message_to_telegram

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmartTrailingStopBot")

key = os.getenv("API_KEY")
secret = os.getenv("API_SECRET")

session = HTTP(api_key=key, api_secret=secret, testnet=False)


class AdvancedTrailingManager:
    def __init__(self, symbol, side, entry_price,
                 activation_percent=1,
                 initial_stop_percent=2,
                 trailing_percent=1):
        self.symbol = symbol
        self.side = side
        self.entry_price = Decimal(str(entry_price))
        self.activation_percent = Decimal(str(activation_percent))
        self.initial_stop_percent = Decimal(str(initial_stop_percent))
        self.trailing_percent = Decimal(str(trailing_percent))
        self.activated = False
        self.best_price = self.entry_price
        self.current_stop = self._calculate_initial_stop()

    def _calculate_initial_stop(self):
        if self.side == "Buy":
            return self.entry_price * (1 - self.initial_stop_percent / 100)
        return self.entry_price * (1 + self.initial_stop_percent / 100)

    def _check_activation(self, current_price):
        if self.side == "Buy":
            return current_price >= self.entry_price * (1 + self.activation_percent / 100)
        return current_price <= self.entry_price * (1 - self.activation_percent / 100)

    def calculate_stop(self, current_price):
        current_price = Decimal(str(current_price))

        if not self.activated and self._check_activation(current_price):
            self.activated = True
            self.current_stop = self.entry_price  # Move to breakeven
            logger.info(f"Trailing activated! Stop moved to entry: {self.entry_price}")
            return float(self.current_stop)

        if self.activated:
            if (self.side == "Buy" and current_price > self.best_price) or \
                    (self.side == "Sell" and current_price < self.best_price):
                self.best_price = current_price
                new_stop = self._calculate_trailing_stop()
                if new_stop != self.current_stop:
                    self.current_stop = new_stop
                    logger.info(f"New trailing stop: {self.current_stop}")
                    return float(self.current_stop)
        elif current_price != self.best_price:
            self.best_price = current_price
            return float(self.current_stop)  # Return initial stop

        return None

    def _calculate_trailing_stop(self):
        if self.side == "Buy":
            return self.best_price * (1 - self.trailing_percent / 100)
        return self.best_price * (1 + self.trailing_percent / 100)


def monitor_and_update_stop(symbol, side, entry_price):
    manager = AdvancedTrailingManager(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        activation_percent=1,
        initial_stop_percent=2,
        trailing_percent=1
    )

    logger.info(f"Initial stop set at: {manager.current_stop}")
    send_message_to_telegram(f"🚀 Initial stop set at {manager.current_stop:.4f}")

    while True:
        position = get_position_info(symbol)
        if not position or float(position['size']) == 0:
            logger.info("Position closed, exiting monitoring")
            break

        current_price = Decimal(str(get_current_price(symbol)))
        new_stop = manager.calculate_stop(current_price)

        if new_stop:
            current_stop = Decimal(str(position.get('stopLoss', 0)))
            if Decimal(str(new_stop)) != current_stop:
                if update_stop_loss(symbol, new_stop):
                    send_message_to_telegram(
                        f"🔵 Stop updated: {new_stop:.4f} | "
                        f"Price: {current_price:.4f} | "
                        f"Profit: {(current_price - manager.entry_price) / manager.entry_price * 100:.2f}%"
                    )

        time.sleep(5)


def get_current_price(symbol):
    try:
        response = session.get_tickers(category="linear", symbol=symbol)
        return float(response['result']['list'][0]['lastPrice'])
    except Exception as e:
        logger.error(f"Price check error: {e}")
        return None


def get_position_info(symbol):
    try:
        response = session.get_positions(category="linear", symbol=symbol)
        positions = [p for p in response['result']['list'] if p['symbol'] == symbol]
        return positions[0] if positions else None
    except Exception as e:
        logger.error(f"Position check error: {e}")
        return None


def update_stop_loss(symbol, stop_price):
    try:
        position = get_position_info(symbol)
        if not position:
            return False

        params = {
            "category": "linear",
            "symbol": symbol,
            "stopLoss": str(round_float_to_precision(stop_price)),
            "positionIdx": position['positionIdx']
        }

        response = session.set_trading_stop(**params)
        if response['retCode'] == 0:
            return True
        logger.error(f"Stop update failed: {response['retMsg']}")
        return False
    except Exception as e:
        logger.error(f"Stop update error: {e}")
        return False


def round_float_to_precision(value, precision=4):
    return float(Decimal(str(value)).quantize(
        Decimal('1.' + '0' * precision),
        rounding=ROUND_HALF_UP
    ))


# Использование
def open_position(symbol, side, amount_usd):
    try:
        price = get_current_price(symbol)
        if not price:
            return False

        # Ваша логика открытия позиции
        # После успешного открытия:
        send_message_to_telegram(f"✅ Position opened at {price}")
        monitor_and_update_stop(symbol, side, price)
    except Exception as e:
        logger.error(f"Open position error: {e}")


signal = 'JASMYUSDT'

if __name__ == "__main__":
    open_position(signal.upper(), "Sell", 6)