from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
import logging
from datetime import datetime
from calendar import monthrange
import os
from dotenv import load_dotenv

load_dotenv()

# --- Настройка ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("8309361791:AAFkMAUHPljHFbVxToFSdJeq4i3YA2OgikY")
ADMIN_CHAT_ID = os.getenv("1436846209")

# Состояния диалога
(
    START, NAME, SURNAME_OR_NICKNAME, 
    MESSAGE, SOURCE, APPROVAL,
    SCHEDULE_DATE, CONFIRM_DATE
) = range(8)

# --- Генерация календаря ---
def generate_calendar(year: int = None, month: int = None) -> InlineKeyboardMarkup:
    now = datetime.now()
    if not year or not month:
        year, month = now.year, now.month
    
    keyboard = []
    
    # Заголовок (месяц + навигация)
    month_name = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", 
                 "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"][month-1]
    header = [
        InlineKeyboardButton("◀", callback_data=f"prev_{year}_{month}"),
        InlineKeyboardButton(f"{month_name} {year}", callback_data="ignore"),
        InlineKeyboardButton("▶", callback_data=f"next_{year}_{month}")
    ]
    keyboard.append(header)
    
    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in week_days])
    
    # Дни месяца
    _, days_in_month = monthrange(year, month)
    first_weekday = datetime(year, month, 1).weekday()
    
    days = []
    # Пустые клетки для первого ряда
    days.extend([InlineKeyboardButton(" ", callback_data="ignore")] * first_weekday)
    
    for day in range(1, days_in_month + 1):
        date = datetime(year, month, day)
        if date.date() < now.date():
            days.append(InlineKeyboardButton(" ", callback_data="ignore"))
        else:
            days.append(InlineKeyboardButton(str(day), callback_data=f"day_{year}_{month}_{day}"))
    
    # Разбиваем на ряды по 7 дней
    for i in range(0, len(days), 7):
        keyboard.append(days[i:i+7])
    
    # Кнопка подтверждения
    keyboard.append([InlineKeyboardButton("✅ Подтвердить дату", callback_data="confirm_date")])
    
    return InlineKeyboardMarkup(keyboard)

# --- Основные обработчики ---
async def start(update: Update, context: CallbackContext) -> int:
    welcome_text = (
        "👋 Привет! Я секретарь *YAG_ARTEM*.\n\n"
        "📝 Перед перепиской с ним нужно заполнить анкету.\n"
        "🔎 Если ты пройдёшь модерацию, тебе назначат время переписки.\n\n"
        "*Введи своё имя:*"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")
    return NAME

async def get_name(update: Update, context: CallbackContext) -> int:
    context.user_data["name"] = update.message.text
    await update.message.reply_text("🔹 Теперь введи фамилию или ник:")
    return SURNAME_OR_NICKNAME

async def get_surname_or_nickname(update: Update, context: CallbackContext) -> int:
    context.user_data["surname_or_nickname"] = update.message.text
    await update.message.reply_text("✉️ Напиши своё сообщение для YAG_ARTEM:")
    return MESSAGE

async def get_message(update: Update, context: CallbackContext) -> int:
    context.user_data["message"] = update.message.text
    await update.message.reply_text("🔍 Откуда ты узнал(а) об этом боте/YAG_ARTEM?")
    return SOURCE

async def get_source(update: Update, context: CallbackContext) -> int:
    context.user_data["source"] = update.message.text
    user = update.message.from_user

    application_text = (
        "📄 *Новая анкета*\n\n"
        f"👤 Имя: {context.user_data['name']}\n"
        f"🔖 Фамилия/Ник: {context.user_data['surname_or_nickname']}\n"
        f"📩 Сообщение: {context.user_data['message']}\n"
        f"🌐 Источник: {context.user_data['source']}\n\n"
        f"🆔 ID: {user.id}\n"
        f"🔗 Профиль: @{user.username if user.username else 'нет'}"
    )

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=application_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user.id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user.id}")
            ]
        ])
    )

    await update.message.reply_text(
        "✅ Анкета отправлена на модерацию!\n"
        "Я сообщу тебе, когда её проверят."
    )
    return ConversationHandler.END

async def admin_decision(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    action, applicant_id = query.data.split("_")
    applicant_id = int(applicant_id)

    if action == "approve":
        context.user_data["applicant_id"] = applicant_id
        await query.edit_message_text(
            "✅ Анкета одобрена! Выберите дату:",
            reply_markup=generate_calendar()
        )
    elif action == "reject":
        await context.bot.send_message(
            chat_id=applicant_id,
            text="❌ К сожалению, твоя анкета отклонена."
        )
        await query.edit_message_text("❌ Анкета отклонена.")

async def handle_calendar_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    now = datetime.now()
    
    if data.startswith("prev_") or data.startswith("next_"):
        # Навигация между месяцами
        _, year, month = data.split("_")
        year, month = int(year), int(month)
        
        if data.startswith("prev_"):
            if month == 1:
                month = 12
                year -= 1
            else:
                month -= 1
        else:
            if month == 12:
                month = 1
                year += 1
            else:
                month += 1
                
        await query.edit_message_reply_markup(
            reply_markup=generate_calendar(year, month)
        )
    
    elif data.startswith("day_"):
        # Выбор дня
        _, year, month, day = data.split("_")
        context.user_data["selected_date"] = f"{day}.{month}.{year}"
        await query.answer(f"Выбрана дата: {day}.{month}.{year}")
    
    elif data == "confirm_date":
        # Подтверждение даты
        if "selected_date" not in context.user_data:
            await query.answer("Сначала выберите дату!")
            return
            
        selected_date = context.user_data["selected_date"]
        applicant_id = context.user_data["applicant_id"]
        
        await context.bot.send_message(
            chat_id=applicant_id,
            text=f"📅 Вам назначена переписка на *{selected_date}*\n\nЖдём вас!",
            parse_mode="Markdown"
        )
        
        await query.edit_message_text(
            f"✅ Дата {selected_date} назначена пользователю",
            reply_markup=None
        )

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("❌ Диалог прерван. Напиши /start, чтобы начать заново.")
    return ConversationHandler.END

# --- Запуск бота ---
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            SURNAME_OR_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_surname_or_nickname)],
            MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_message)],
            SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_source)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(admin_decision, pattern=r"^(approve|reject)_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_calendar_selection))
    
    application.run_polling()

if __name__ == "__main__":
    main()