from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import logging

# Замените 'YOUR_TOKEN' на ваш токен бота
TOKEN = '7642372695:AAHhFAydBvPUyplplcMfPa9U_nh0CWVLyy8'
# Замените 'USER_ID' на ID пользователя, которому нужно дублировать сообщения
USER_ID = '1395854084'

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Бот запущен!')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Выводим полученное сообщение в консоль
        logger.info(f"Получено сообщение: {update.message.text}")

        # Дублируем сообщение пользователю с заданным ID
        await context.bot.send_message(chat_id=USER_ID, text=update.message.text)
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")

def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    try:
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()