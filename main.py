from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Замените 'YOUR_TOKEN' на ваш токен бота
TOKEN = '7642372695:AAHhFAydBvPUyplplcMfPa9U_nh0CWVLyy8'
# Замените 'USER_ID' на ID пользователя, которому нужно дублировать сообщения
USER_ID = '1395854084'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Бот запущен!')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Дублируем сообщение пользователю с заданным ID
    await context.bot.send_message(chat_id=USER_ID, text=update.message.text)

def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    application.run_polling()

if __name__ == '__main__':
    main()