import gspread
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from datetime import datetime
import json
import os
from google.oauth2.service_account import Credentials

# === НАСТРОЙКИ ===
BOT_TOKEN = "8444538558:AAF3vHHUC4YZb6BZUfzGVETjVFTzXDSedis"
GOOGLE_SHEET_NAME = "Жизни учеников"
ADMIN_USERNAME = "niinaaaa"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_google_sheets_client():
    """Универсальная функция для получения клиента Google Sheets"""
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    
    if creds_json:
        try:
            logger.info("✅ Используем GOOGLE_CREDENTIALS из переменных окружения")
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(creds_dict)
            client = gspread.authorize(credentials)
            logger.info("✅ Успешная авторизация в Google Sheets")
            return client
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            raise
    else:
        if os.path.exists('credentials.json'):
            logger.info("✅ Используем credentials.json из файла")
            return gspread.service_account(filename='credentials.json')
        else:
            raise FileNotFoundError("❌ Не найдены credentials")

class GoogleSheetsManager:
    def __init__(self):
        try:
            self.gc = get_google_sheets_client()
            self.sheet = self.gc.open(GOOGLE_SHEET_NAME).sheet1
            logger.info("✅ Успешно подключились к Google Таблице")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Таблице: {e}")
            raise

    def find_user_row(self, user_id):
        try:
            all_records = self.sheet.get_all_records()
            for i, record in enumerate(all_records, start=2):
                if str(record.get('Telegram ID', '')) == str(user_id):
                    return i
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя {user_id}: {e}")
            return None

    def get_user_balance(self, user_id):
        row = self.find_user_row(user_id)
        if row:
            try:
                balance = self.sheet.cell(row, 4).value
                return int(balance) if balance else 0
            except:
                return 0
        return None

    def register_user(self, user_id, username, full_name):
        if self.find_user_row(user_id):
            return False, "Пользователь уже существует"

        try:
            new_row = [
                str(user_id),
                f"@{username}" if username else "без username", 
                full_name,
                3,  # Начальный баланс
                3,  # Последний баланс
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            self.sheet.append_row(new_row)
            logger.info(f"✅ Зарегистрирован новый пользователь: {full_name} (ID: {user_id})")
            return True, "Успешная регистрация"
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации: {e}")
            return False, f"Ошибка регистрации: {e}"

def start_command(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = user.id
    
    try:
        sheets = GoogleSheetsManager()
        balance = sheets.get_user_balance(user_id)

        if balance is None:
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            success, message = sheets.register_user(user_id, user.username, full_name)
            if success:
                update.message.reply_text(
                    f"🎉 Добро пожаловать, {user.first_name}!\n\n"
                    f"✅ Ты успешно зарегистрирован в системе!\n"
                    f"💫 Начальный баланс: 3 жизни\n\n"
                    f"📊 Команды:\n"
                    f"/balance - Узнать баланс\n"
                    f"/help - Помощь"
                )
            else:
                update.message.reply_text(f"❌ Ошибка регистрации: {message}")
        else:
            update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"💫 Твой текущий баланс: {balance} жизней"
            )
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /start: {e}")
        update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

def balance_command(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = user.id
    
    try:
        sheets = GoogleSheetsManager()
        balance = sheets.get_user_balance(user_id)

        if balance is None:
            update.message.reply_text("❌ Ты не зарегистрирован! Напиши /start")
            return

        if balance >= 3:
            emoji = "🎉"
            status = "Отлично! Так держать!"
        elif balance == 2:
            emoji = "⚠️"
            status = "Хорошо, но будь внимателен!"
        elif balance == 1:
            emoji = "🔔"
            status = "Внимание! Осталась 1 жизнь!"
        else:
            emoji = "🚨"
            status = "Срочно нужно исправлять!"

        message = f"""
{emoji} Твой баланс жизней

💫 Осталось жизней: {balance}
📝 Статус: {status}
        """
        update.message.reply_text(message)
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /balance: {e}")
        update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

def help_command(update: Update, context: CallbackContext):
    help_text = """
📖 Справка по системе жизней

💫 Что такое жизни?
- 3 жизни в начале месяца
- Просрочка ДЗ = -1 жизнь
- 3 просрочки = созвон

🎯 Команды:
/start - Регистрация
/balance - Баланс
/help - Справка
    """
    update.message.reply_text(help_text)

def handle_message(update: Update, context: CallbackContext):
    update.message.reply_text("🤖 Используй команды: /start, /balance, /help")

def main():
    logger.info("🚀 Запуск Math Life Bot...")
    
    try:
        # Используем Updater для версии 13.15
        updater = Updater(BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher
        
        # Добавляем обработчики
        dispatcher.add_handler(CommandHandler("start", start_command))
        dispatcher.add_handler(CommandHandler("balance", balance_command))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
        
        logger.info("✅ Бот успешно запущен и готов к работе!")
        print("🤖 MATH LIFE BOT ЗАПУЩЕН!")
        
        # Запускаем бота
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()
