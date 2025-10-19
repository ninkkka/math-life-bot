import gspread
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import json
import os
import time
from threading import Thread
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
        # Production: используем переменную окружения
        try:
            logger.info("✅ Используем GOOGLE_CREDENTIALS из переменных окружения")
            creds_dict = json.loads(creds_json)
            
            # Указываем правильные scopes для Google Sheets API
            SCOPES = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            client = gspread.authorize(credentials)
            logger.info("✅ Успешная авторизация в Google Sheets")
            return client
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга GOOGLE_CREDENTIALS: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            raise
    else:
        # Development: используем файл
        logger.info("ℹ️ GOOGLE_CREDENTIALS не найдена, пробуем credentials.json")
        if os.path.exists('credentials.json'):
            logger.info("✅ Используем credentials.json из файла")
            return gspread.service_account(filename='credentials.json')
        else:
            logger.error("❌ credentials.json не найден и GOOGLE_CREDENTIALS не установлена")
            raise FileNotFoundError("❌ Не найдены credentials ни в переменных окружения, ни в файле")


# === РАБОТА С GOOGLE TABLES ===
class GoogleSheetsManager:
    def __init__(self):
        try:
            # Используем нашу универсальную функцию
            self.gc = get_google_sheets_client()
            self.sheet = self.gc.open(GOOGLE_SHEET_NAME).sheet1
            logger.info("✅ Успешно подключились к Google Таблице")
            
            # Проверяем доступ простым запросом
            test_value = self.sheet.acell('A1').value
            logger.info(f"✅ Тестовый запрос выполнен успешно. A1: {test_value}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Таблице: {e}")
            raise


    def find_user_row(self, user_id):
        """Найти строку пользователя по ID"""
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
        """Получить баланс пользователя"""
        row = self.find_user_row(user_id)
        if row:
            try:
                balance = self.sheet.cell(row, 4).value
                return int(balance) if balance else 0
            except:
                return 0
        return None

    def register_user(self, user_id, username, full_name):
        """Зарегистрировать нового пользователя"""
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

    def update_balance(self, user_id, new_balance, reason=""):
        """Обновить баланс пользователя"""
        row = self.find_user_row(user_id)
        if not row:
            return False, "Пользователь не найден"

        try:
            self.sheet.update_cell(row, 4, new_balance)
            self.sheet.update_cell(row, 5, new_balance)
            self.sheet.update_cell(row, 6, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logger.info(f"✅ Баланс пользователя {user_id} изменен на {new_balance}. Причина: {reason}")
            return True, "Баланс обновлен"
        except Exception as e:
            logger.error(f"❌ Ошибка обновления баланса: {e}")
            return False, f"Ошибка обновления: {e}"


# === СИСТЕМА УВЕДОМЛЕНИЙ ===
class BalanceNotifier:
    def __init__(self, bot):
        self.bot = bot
        self.last_balances = {}

    def initialize_balances(self):
        """Инициализируем начальные балансы"""
        try:
            all_records = self.bot.sheets.sheet.get_all_records()
            for record in all_records:
                user_id = record.get('Telegram ID')
                balance = record.get('Баланс', 0)
                if user_id:
                    self.last_balances[int(user_id)] = balance
            logger.info(f"✅ Инициализированы балансы для {len(self.last_balances)} пользователей")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации балансов: {e}")

    async def check_balance_changes(self):
        """Проверяем изменения балансов и отправляем уведомления"""
        try:
            all_records = self.bot.sheets.sheet.get_all_records()

            for record in all_records:
                user_id = record.get('Telegram ID')
                current_balance = record.get('Баланс', 0)

                if user_id:
                    user_id = int(user_id)
                    last_balance = self.last_balances.get(user_id)

                    if last_balance is not None and current_balance != last_balance:
                        reason = "📈 Баланс увеличен" if current_balance > last_balance else "📉 Баланс уменьшен"

                        try:
                            await self.bot.application.bot.send_message(
                                chat_id=user_id,
                                text=f"💫 Изменение баланса!\n\n"
                                     f"🔄 {reason}\n"
                                     f"💫 Новый баланс: {current_balance} жизней\n\n"
                                     f"💡 Проверь детали: /balance"
                            )
                            logger.info(f"✅ Уведомление отправлено пользователю {user_id}")
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось отправить уведомление {user_id}")

                    self.last_balances[user_id] = current_balance

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке изменений баланса: {e}")


# === TELEGRAM BOT ===
class MathLifeBot:
    def __init__(self):
        self.sheets = GoogleSheetsManager()
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.notifier = BalanceNotifier(self)
        self._setup_handlers()

    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("balance", self.balance_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("id", self.id_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.message.from_user
        user_id = user.id

        balance = self.sheets.get_user_balance(user_id)

        if balance is None:
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            success, message = self.sheets.register_user(user_id, user.username, full_name)

            if success:
                welcome_text = f"""
🎉 Добро пожаловать, {user.first_name}!

✅ Ты успешно зарегистрирован в системе!
💫 Начальный баланс: 3 жизни

📊 Команды:
/balance - Узнать баланс
/id - Мой ID для преподавателя
/help - Помощь
                """
            else:
                welcome_text = f"❌ Ошибка регистрации: {message}"
        else:
            welcome_text = f"""
👋 С возвращением, {user.first_name}!

💫 Твой текущий баланс: {balance} жизней
            """

        await update.message.reply_text(welcome_text)
        logger.info(f"✅ Отправлен ответ пользователю {user_id}")

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /balance"""
        user = update.message.from_user
        user_id = user.id

        balance = self.sheets.get_user_balance(user_id)

        if balance is None:
            await update.message.reply_text("❌ Ты не зарегистрирован! Напиши /start")
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

        await update.message.reply_text(message)

    async def id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать пользователю его ID"""
        user = update.message.from_user
        user_id = user.id

        await update.message.reply_text(f"📋 Твой ID: `{user_id}`", parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📖 Справка по системе жизней

💫 Что такое жизни?
- 3 жизни в начале месяца
- Просрочка ДЗ = -1 жизнь
- 3 просрочки = созвон

🎯 Как заработать жизни?
- Досрочная сдача = +1 жизнь

📊 Команды:
/start - Регистрация
/balance - Баланс
/id - Мой ID
/help - Справка
        """
        await update.message.reply_text(help_text)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка обычных сообщений"""
        await update.message.reply_text("🤖 Используй команды: /start, /balance, /help")


# === АДМИН-КОМАНДЫ ===
class AdminTools:
    def __init__(self, bot):
        self.bot = bot

    async def update_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для изменения баланса"""
        if update.message.from_user.username != ADMIN_USERNAME:
            await update.message.reply_text("❌ Нет доступа")
            return

        if len(context.args) < 3:
            await update.message.reply_text("Использование: /update user_id ±число 'причина'")
            return

        try:
            user_id = int(context.args[0])
            change = int(context.args[1])
            reason = ' '.join(context.args[2:])

            current_balance = self.bot.sheets.get_user_balance(user_id)
            if current_balance is None:
                await update.message.reply_text("❌ Ученик не найден")
                return

            new_balance = current_balance + change
            success, message = self.bot.sheets.update_balance(user_id, new_balance, reason)

            if success:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"💫 Баланс изменен: {new_balance}\nПричина: {reason}"
                    )
                except:
                    pass

                await update.message.reply_text(f"✅ Баланс обновлен: {new_balance}")
            else:
                await update.message.reply_text(f"❌ {message}")

        except ValueError:
            await update.message.reply_text("❌ Неверный формат")


# === ЗАПУСК СИСТЕМЫ УВЕДОМЛЕНИЙ ===
def run_notifier(bot):
    """Запуск системы уведомлений в отдельном потоке"""
    def check_changes():
        while True:
            try:
                import asyncio
                # Создаем новый event loop для асинхронного вызова
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(bot.notifier.check_balance_changes())
                loop.close()
            except Exception as e:
                logger.error(f"❌ Ошибка в системе уведомлений: {e}")
            time.sleep(60)  # Проверяем каждую минуту

    thread = Thread(target=check_changes, daemon=True)
    thread.start()


# === ЗАПУСК ПРИЛОЖЕНИЯ ===
def main():
    logger.info("🚀 Запуск Math Life Bot...")
    
    # Проверяем наличие переменных окружения
    if os.environ.get('GOOGLE_CREDENTIALS'):
        logger.info("✅ GOOGLE_CREDENTIALS найдена в переменных окружения")
    else:
        logger.info("ℹ️ GOOGLE_CREDENTIALS не найдена, будет использоваться credentials.json")

    try:
        bot = MathLifeBot()
        admin_tools = AdminTools(bot)
        bot.application.add_handler(CommandHandler("update", admin_tools.update_balance))

        # Инициализируем систему уведомлений
        bot.notifier.initialize_balances()

        # Запускаем систему уведомлений в отдельном потоке
        run_notifier(bot)

        logger.info("✅ Бот успешно запущен и готов к работе!")
        logger.info("✅ Система уведомлений запущена")
        print("\n" + "="*50)
        print("🤖 MATH LIFE BOT ЗАПУЩЕН!")
        print("🔔 Система уведомлений активна")
        print("⏹️  Нажмите Ctrl+C для остановки")
        print("="*50 + "\n")

        # Используем правильный метод для новой версии python-telegram-bot
        bot.application.run_polling()

    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}")
        print(f"❌ Ошибка: {e}")


if __name__ == '__main__':
    main()
