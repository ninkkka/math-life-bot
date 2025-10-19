import gspread
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import json
import os
import asyncio
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
            
            # Указываем правильные scopes для Google Sheets API
            SCOPES = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
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
    def __init__(self, application, sheets_manager):
        self.application = application
        self.sheets = sheets_manager
        self.last_balances = {}
        self.initialize_balances()

    def initialize_balances(self):
        """Инициализируем начальные балансы при запуске"""
        try:
            all_records = self.sheets.sheet.get_all_records()
            for record in all_records:
                user_id = record.get('Telegram ID')
                balance = record.get('Баланс', 0)
                if user_id:
                    self.last_balances[str(user_id)] = balance
            logger.info(f"✅ Инициализированы балансы для {len(self.last_balances)} пользователей")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации балансов: {e}")

    async def check_balance_changes(self, context: ContextTypes.DEFAULT_TYPE = None):
        """Проверяем изменения балансов и отправляем уведомления"""
        try:
            all_records = self.sheets.sheet.get_all_records()
            changes_found = False

            for record in all_records:
                user_id = str(record.get('Telegram ID', ''))
                current_balance = record.get('Баланс', 0)

                if user_id and user_id != 'None':
                    last_balance = self.last_balances.get(user_id)
                    
                    # Если баланс изменился
                    if last_balance is not None and current_balance != last_balance:
                        changes_found = True
                        reason = "📈 Баланс увеличен" if current_balance > last_balance else "📉 Баланс уменьшен"
                        
                        try:
                            await self.application.bot.send_message(
                                chat_id=int(user_id),
                                text=f"💫 Изменение баланса!\n\n"
                                     f"🔄 {reason}\n"
                                     f"💫 Новый баланс: {current_balance} жизней\n\n"
                                     f"💡 Проверь детали: /balance"
                            )
                            logger.info(f"✅ Уведомление отправлено пользователю {user_id}")
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось отправить уведомление {user_id}: {e}")

                        # Обновляем последнее известное значение
                        self.last_balances[user_id] = current_balance

            if changes_found:
                logger.info("✅ Проверка изменений завершена, уведомления отправлены")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке изменений баланса: {e}")

# === АДМИН-КОМАНДЫ ===
class AdminTools:
    def __init__(self, sheets_manager):
        self.sheets = sheets_manager

    async def update_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для изменения баланса /update user_id ±число причина"""
        # Проверяем админские права
        if update.message.from_user.username != ADMIN_USERNAME:
            await update.message.reply_text("❌ Нет доступа")
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "❌ Неправильный формат команды!\n\n"
                "📝 **Правильное использование:**\n"
                "`/update USER_ID ИЗМЕНЕНИЕ ПРИЧИНА`\n\n"
                "🔢 **Примеры:**\n"
                "`/update 361845909 +1 Досрочная_сдача_ДЗ`\n"
                "`/update 361845909 -1 Просрочка_задания`\n\n"
                "💡 **Используйте подчеркивания _ вместо пробелов**"
            )
            return

        try:
            user_id = int(context.args[0])
            change = int(context.args[1])
            reason = ' '.join(context.args[2:]).replace('_', ' ')  # Заменяем _ на пробелы

            # Получаем текущий баланс
            current_balance = self.sheets.get_user_balance(user_id)
            if current_balance is None:
                await update.message.reply_text("❌ Ученик не найден")
                return

            # Вычисляем новый баланс
            new_balance = current_balance + change
            
            # Проверяем, чтобы баланс не ушел в минус
            if new_balance < 0:
                new_balance = 0

            # Обновляем в таблице
            success, message = self.sheets.update_balance(user_id, new_balance, reason)

            if success:
                # Пытаемся отправить уведомление ученику
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"💫 Изменение баланса!\n\n"
                             f"🔄 Причина: {reason}\n"
                             f"💫 Новый баланс: {new_balance} жизней\n\n"
                             f"💡 Подробнее: /balance"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отправить уведомление ученику {user_id}: {e}")

                await update.message.reply_text(
                    f"✅ Баланс обновлен!\n"
                    f"👤 Ученик: {user_id}\n"
                    f"💫 Было: {current_balance} → Стало: {new_balance}\n"
                    f"📝 Причина: {reason}"
                )
            else:
                await update.message.reply_text(f"❌ Ошибка: {message}")

        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат!\n\n"
                "📝 **Правильное использование:**\n"
                "`/update USER_ID ИЗМЕНЕНИЕ ПРИЧИНА`\n\n"
                "🔢 **Пример:**\n"
                "`/update 361845909 +1 Ты_молодец`"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка в update_balance: {e}")
            await update.message.reply_text("❌ Произошла ошибка")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    
    try:
        sheets = GoogleSheetsManager()
        balance = sheets.get_user_balance(user_id)

        if balance is None:
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            success, message = sheets.register_user(user_id, user.username, full_name)
            if success:
                await update.message.reply_text(
                    f"🎉 Добро пожаловать, {user.first_name}!\n\n"
                    f"✅ Ты успешно зарегистрирован в системе!\n"
                    f"💫 Начальный баланс: 3 жизни\n\n"
                    f"📊 Команды:\n"
                    f"/balance - Узнать баланс\n"
                    f"/help - Помощь"
                )
            else:
                await update.message.reply_text(f"❌ Ошибка регистрации: {message}")
        else:
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"💫 Твой текущий баланс: {balance} жизней"
            )
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /start: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    
    try:
        sheets = GoogleSheetsManager()
        balance = sheets.get_user_balance(user_id)

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
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /balance: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Используй команды: /start, /balance, /help")

def main():
    logger.info("🚀 Запуск Math Life Bot...")
    
    try:
        # Создаем менеджер таблиц
        sheets_manager = GoogleSheetsManager()
        
        # Создаем Application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Создаем систему уведомлений
        notifier = BalanceNotifier(application, sheets_manager)
        
        # Создаем админ-инструменты
        admin_tools = AdminTools(sheets_manager)
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("balance", balance_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("update", admin_tools.update_balance))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Запускаем фоновую задачу для проверки изменений
        application.job_queue.run_repeating(
            lambda context: asyncio.create_task(notifier.check_balance_changes(context)),
            interval=30,  # Проверяем каждые 30 секунд
            first=10      # Первая проверка через 10 секунд после запуска
        )
        
        logger.info("✅ Бот успешно запущен и готов к работе!")
        logger.info("✅ Система уведомлений активирована")
        print("🤖 MATH LIFE BOT ЗАПУЩЕН!")
        print("🔔 Система уведомлений активна")
        
        # Запускаем бота
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()
