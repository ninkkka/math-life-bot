import gspread
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import json
import os
import asyncio
from google.oauth2.service_account import Credentials
from aiohttp import web
import threading

# === НАСТРОЙКИ ===
BOT_TOKEN = "8444538558:AAF3vHHUC4YZb6BZUfzGVETjVFTzXDSedis"
GOOGLE_SHEET_NAME = "Жизни учеников"
ADMIN_USERNAME = "niinaaaa"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_http_server():
    """Запускает простой HTTP сервер для проверки портов на Render.com"""
    async def handle(request):
        return web.Response(text="🤖 Math Life Bot is running!")
    
    app = web.Application()
    app.router.add_get('/', handle)
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Запуск HTTP сервера на порту {port}")
    web.run_app(app, host='0.0.0.0', port=port)

# Запускаем HTTP сервер в отдельном потоке
http_thread = threading.Thread(target=run_http_server, daemon=True)
http_thread.start()

def get_google_sheets_client():
    """Универсальная функция для получения клиента Google Sheets"""
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    
    if creds_json:
        try:
            logger.info("✅ Используем GOOGLE_CREDENTIALS из переменных окружения")
            creds_dict = json.loads(creds_json)
            
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
                3,
                3,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            self.sheet.append_row(new_row)
            logger.info(f"✅ Зарегистрирован новый пользователь: {full_name} (ID: {user_id})")
            return True, "Успешная регистрация"
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации: {e}")
            return False, f"Ошибка регистрации: {e}"

    def update_balance(self, user_id, new_balance, reason=""):
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

# === ОСНОВНЫЕ КОМАНДЫ ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.message.from_user
    user_id = user.id
    logger.info(f"🔄 Получена команда /start от пользователя {user_id}")
    
    try:
        # Получаем sheets_manager из context
        sheets = context.bot_data['sheets_manager']
        balance = sheets.get_user_balance(user_id)

        if balance is None:
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            success, message = sheets.register_user(user_id, user.username, full_name)
            if success:
                response = f"🎉 Добро пожаловать, {user.first_name}!\n\n✅ Ты успешно зарегистрирован!\n💫 Начальный баланс: 3 жизни"
                await update.message.reply_text(response)
                logger.info(f"✅ Пользователь {user_id} зарегистрирован")
            else:
                await update.message.reply_text(f"❌ Ошибка регистрации: {message}")
                logger.error(f"❌ Ошибка регистрации пользователя {user_id}: {message}")
        else:
            response = f"👋 С возвращением, {user.first_name}!\n💫 Твой текущий баланс: {balance} жизней"
            await update.message.reply_text(response)
            logger.info(f"✅ Пользователь {user_id} получил баланс: {balance}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /start для пользователя {user_id}: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /balance"""
    user = update.message.from_user
    user_id = user.id
    logger.info(f"🔄 Получена команда /balance от пользователя {user_id}")
    
    try:
        sheets = context.bot_data['sheets_manager']
        balance = sheets.get_user_balance(user_id)

        if balance is None:
            await update.message.reply_text("❌ Ты не зарегистрирован! Напиши /start")
            logger.warning(f"⚠️ Пользователь {user_id} не зарегистрирован")
            return

        if balance >= 3:
            emoji, status = "🎉", "Отлично! Так держать!"
        elif balance == 2:
            emoji, status = "⚠️", "Хорошо, но будь внимателен!"
        elif balance == 1:
            emoji, status = "🔔", "Внимание! Осталась 1 жизнь!"
        else:
            emoji, status = "🚨", "Срочно нужно исправлять!"

        message = f"{emoji} Твой баланс жизней\n\n💫 Осталось жизней: {balance}\n📝 Статус: {status}"
        await update.message.reply_text(message)
        logger.info(f"✅ Пользователь {user_id} получил баланс: {balance}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /balance для пользователя {user_id}: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    logger.info(f"🔄 Получена команда /help от пользователя {update.message.from_user.id}")
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
    logger.info("✅ Отправлена справка")

# === АДМИН КОМАНДЫ ===
async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /update"""
    user = update.message.from_user
    user_id = user.id
    logger.info(f"🔄 Получена команда /update от пользователя {user_id}: {context.args}")
    
    # Проверяем админские права
    if user.username != ADMIN_USERNAME:
        await update.message.reply_text("❌ Нет доступа")
        logger.warning(f"⚠️ Попытка доступа к /update от не-админа: {user.username}")
        return

    if len(context.args) < 3:
        help_text = (
            "❌ Неправильный формат команды!\n\n"
            "📝 Правильное использование:\n"
            "`/update USER_ID ИЗМЕНЕНИЕ ПРИЧИНА`\n\n"
            "🔢 Примеры:\n"
            "`/update 361845909 +1 Ты_молодец`\n"
            "`/update 361845909 -1 Просрочка_ДЗ`\n\n"
            "💡 Используйте подчеркивания _ вместо пробелов"
        )
        await update.message.reply_text(help_text)
        return

    try:
        target_user_id = int(context.args[0])
        change = int(context.args[1])
        reason = ' '.join(context.args[2:]).replace('_', ' ')

        sheets = context.bot_data['sheets_manager']
        current_balance = sheets.get_user_balance(target_user_id)
        
        if current_balance is None:
            await update.message.reply_text("❌ Ученик не найден")
            logger.warning(f"⚠️ Ученик {target_user_id} не найден")
            return

        new_balance = current_balance + change
        if new_balance < 0:
            new_balance = 0

        success, message = sheets.update_balance(target_user_id, new_balance, reason)

        if success:
            # Пытаемся отправить уведомление ученику
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"💫 Изменение баланса!\n\n🔄 Причина: {reason}\n💫 Новый баланс: {new_balance} жизней\n\n💡 Подробнее: /balance"
                )
                logger.info(f"✅ Уведомление отправлено ученику {target_user_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить уведомление ученику {target_user_id}: {e}")

            response = f"✅ Баланс обновлен!\n👤 Ученик: {target_user_id}\n💫 Было: {current_balance} → Стало: {new_balance}\n📝 Причина: {reason}"
            await update.message.reply_text(response)
            logger.info(f"✅ Баланс ученика {target_user_id} изменен: {current_balance} -> {new_balance}")
        else:
            await update.message.reply_text(f"❌ Ошибка: {message}")
            logger.error(f"❌ Ошибка обновления баланса для {target_user_id}: {message}")

    except ValueError:
        error_text = (
            "❌ Неверный формат!\n\n"
            "📝 Правильное использование:\n"
            "`/update USER_ID ИЗМЕНЕНИЕ ПРИЧИНА`\n\n"
            "🔢 Пример:\n"
            "`/update 361845909 +1 Ты_молодец`"
        )
        await update.message.reply_text(error_text)
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /update: {e}")
        await update.message.reply_text("❌ Произошла ошибка")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычных сообщений"""
    user_id = update.message.from_user.id
    logger.info(f"🔄 Получено сообщение от пользователя {user_id}: {update.message.text}")
    await update.message.reply_text("🤖 Используй команды: /start, /balance, /help")

def main():
    logger.info("🚀 Запуск Math Life Bot...")
    
    try:
        # Создаем менеджер таблиц один раз
        sheets_manager = GoogleSheetsManager()
        
        # Создаем Application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Сохраняем sheets_manager в bot_data для общего доступа
        application.bot_data['sheets_manager'] = sheets_manager
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("balance", balance_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("update", update_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("✅ Бот успешно запущен и готов к работе!")
        logger.info("✅ Обработчики команд зарегистрированы")
        print("🤖 MATH LIFE BOT ЗАПУЩЕН!")
        print("📝 Доступные команды: /start, /balance, /help, /update")
        print("🌐 HTTP сервер запущен для проверки портов")
        
        # Запускаем бота
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()
