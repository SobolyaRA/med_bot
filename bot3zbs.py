import logging
import random
import sqlite3
import os  # Добавлено для порта webhook
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, \
    ConversationHandler

# ---------- ЛОГИРОВАНИЕ ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- КОНСТАНТЫ СОСТОЯНИЙ ----------
START, CASE_ACTIVE = range(2)

# ---------- СЕКРЕТЫ И ПУТИ ----------
# Токен берем только из переменной окружения BOT_TOKEN.
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не установлена")

# Путь к базе:
# - по умолчанию рядом с файлом (локальный запуск/Heroku эфемерен),
# - если задан DB_DIR (например, /data на Render/Fly), база ляжет туда.
BASE_DIR = os.getenv("DB_DIR") or os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cases.db")

# Состояния
START, CASE_ACTIVE = range(2)

# Разделы
SECTIONS = {
    "Сердечно-сосудистая система": "cardio",
    "Пищеварительная система": "digestive",
    "Мочевыделительная система": "urinary",
    "Кровь": "blood",
    "Дыхательная система": "respiratory",
    "Общий": "general"
}


# Инициализация базы данных SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    tables = ['cardio_cases', 'digestive_cases', 'urinary_cases', 'blood_cases', 'respiratory_cases', 'general_cases']

    for table in tables:
        c.execute(f'''
            CREATE TABLE IF NOT EXISTS {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base TEXT NOT NULL,
                lab TEXT,
                instrumental TEXT,
                correct_diagnosis TEXT NOT NULL,
                options TEXT NOT NULL,
                explanation TEXT NOT NULL
            )
        ''')

    # Добавим тестовые случаи, если базы пусты
    # Для cardio_cases
    c.execute('SELECT COUNT(*) FROM cardio_cases')
    if c.fetchone()[0] == 0:
        c.execute(f'''
            INSERT INTO cardio_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 55 лет, мужчина. Жалобы: боль в груди, иррадиирующая в левую руку, одышка. Анамнез: гипертония, курение.",
            "Тропонин I повышен, креатинкиназа-MB повышен.",
            "ЭКГ: подъём сегмента ST в отведениях V2-V4.",
            "Острый инфаркт миокарда",
            "Острый инфаркт миокарда,Стенокардия,Перикардит",
            "Подъём ST и повышение тропонина указывают на инфаркт."
        ))
        c.execute(f'''
            INSERT INTO general_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 55 лет, мужчина. Жалобы: боль в груди, иррадиирующая в левую руку, одышка. Анамнез: гипертония, курение.",
            "Тропонин I повышен, креатинкиназа-MB повышен.",
            "ЭКГ: подъём сегмента ST в отведениях V2-V4.",
            "Острый инфаркт миокарда",
            "Острый инфаркт миокарда,Стенокардия,Перикардит",
            "Подъём ST и повышение тропонина указывают на инфаркт."
        ))

    # Для digestive_cases
    c.execute('SELECT COUNT(*) FROM digestive_cases')
    if c.fetchone()[0] == 0:
        c.execute(f'''
            INSERT INTO digestive_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 30 лет, женщина. Жалобы: боль в эпигастрии, тошнота, рвота. Анамнез: нерегулярное питание, стресс.",
            "Амилаза повышена, лейкоциты в норме.",
            "УЗИ: отёк поджелудочной железы.",
            "Острый панкреатит",
            "Острый панкреатит,Гастрит,Язва желудка",
            "Повышенная амилаза и УЗИ подтверждают панкреатит."
        ))
        c.execute(f'''
            INSERT INTO general_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 30 лет, женщина. Жалобы: боль в эпигастрии, тошнота, рвота. Анамнез: нерегулярное питание, стресс.",
            "Амилаза повышена, лейкоциты в норме.",
            "УЗИ: отёк поджелудочной железы.",
            "Острый панкреатит",
            "Острый панкреатит,Гастрит,Язва желудка",
            "Повышенная амилаза и УЗИ подтверждают панкреатит."
        ))

    # Для urinary_cases
    c.execute('SELECT COUNT(*) FROM urinary_cases')
    if c.fetchone()[0] == 0:
        c.execute(f'''
            INSERT INTO urinary_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 40 лет, женщина. Жалобы: боль в пояснице, дизурия, температура 38°C. Анамнез: переохлаждение.",
            "Лейкоциты в моче повышенные, нитриты положительные.",
            "УЗИ: расширение чашечно-лоханочной системы.",
            "Острый пиелонефрит",
            "Острый пиелонефрит,Цистит,Мочекаменная болезнь",
            "Лейкоцитурия и УЗИ подтверждают пиелонефрит."
        ))
        c.execute(f'''
            INSERT INTO general_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 40 лет, женщина. Жалобы: боль в пояснице, дизурия, температура 38°C. Анамнез: переохлаждение.",
            "Лейкоциты в моче повышенные, нитриты положительные.",
            "УЗИ: расширение чашечно-лоханочной системы.",
            "Острый пиелонефрит",
            "Острый пиелонефрит,Цистит,Мочекаменная болезнь",
            "Лейкоцитурия и УЗИ подтверждают пиелонефрит."
        ))

    # Для blood_cases
    c.execute('SELECT COUNT(*) FROM blood_cases')
    if c.fetchone()[0] == 0:
        c.execute(f'''
            INSERT INTO blood_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 25 лет, женщина. Жалобы: слабость, бледность, усталость. Анамнез: обильные менструации.",
            "Гемоглобин 80 г/л, MCV снижен, ферритин низкий.",
            "Биопсия костного мозга: нормальная.",
            "Железодефицитная анемия",
            "Железодефицитная анемия,В12-дефицитная анемия,Гемолитическая анемия",
            "Низкий гемоглобин и ферритин указывают на железодефицит."
        ))
        c.execute(f'''
            INSERT INTO general_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 25 лет, женщина. Жалобы: слабость, бледность, усталость. Анамнез: обильные менструации.",
            "Гемоглобин 80 г/л, MCV снижен, ферритин низкий.",
            "Биопсия костного мозга: нормальная.",
            "Железодефицитная анемия",
            "Железодефицитная анемия,В12-дефицитная анемия,Гемолитическая анемия",
            "Низкий гемоглобин и ферритин указывают на железодефицит."
        ))

    # Для respiratory_cases
    c.execute('SELECT COUNT(*) FROM respiratory_cases')
    if c.fetchone()[0] == 0:
        c.execute(f'''
            INSERT INTO respiratory_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 45 лет, мужчина. Жалобы: кашель с мокротой, одышка, температура 38.5°C. Анамнез: курит 20 лет. Объективно: перкуторный звук укорочен слева, хрипы.",
            "Лейкоциты 12x10^9/л, СОЭ 40 мм/ч.",
            "Рентген: инфильтрат в левом лёгком.",
            "Острая пневмония",
            "Острая пневмония,Хронический бронхит,Рак лёгкого",
            "Инфильтрат и лейкоцитоз указывают на пневмонию."
        ))
        c.execute(f'''
            INSERT INTO general_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 45 лет, мужчина. Жалобы: кашель с мокротой, одышка, температура 38.5°C. Анамнез: курит 20 лет. Объективно: перкуторный звук укорочен слева, хрипы.",
            "Лейкоциты 12x10^9/л, СОЭ 40 мм/ч.",
            "Рентген: инфильтрат в левом лёгком.",
            "Острая пневмония",
            "Острая пневмония,Хронический бронхит,Рак лёгкого",
            "Инфильтрат и лейкоцитоз указывают на пневмонию."
        ))

    # Для general_cases (дополнительный уникальный случай)
    c.execute('SELECT COUNT(*) FROM general_cases')
    if c.fetchone()[0] < 6:  # Чтобы не дублировать, если уже добавлены
        c.execute(f'''
            INSERT INTO general_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Пациент 50 лет, мужчина. Жалобы: усталость, потеря веса, лихорадка. Анамнез: контакт с инфекцией.",
            "СОЭ повышен, анемия.",
            "КТ: множественные инфильтраты.",
            "Туберкулёз",
            "Туберкулёз,Саркоидоз,Лимфома",
            "Клиническая картина и КТ указывают на туберкулёз."
        ))

    conn.commit()
    conn.close()


# Функция для получения всех случаев из указанной таблицы
def get_cases(table_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f'SELECT * FROM {table_name}')
    rows = c.fetchall()
    conn.close()
    return [{'id': row[0], 'base': row[1], 'lab': row[2], 'instrumental': row[3],
             'correct_diagnosis': row[4], 'options': row[5].split(','), 'explanation': row[6]} for row in rows]


# Хранение состояний и статистики
user_states = {}
user_stats = {}  # {user_id: {'correct': 0, 'total': 0}}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_states[user_id] = {'state': START}
    if user_id not in user_stats:
        user_stats[user_id] = {'correct': 0, 'total': 0}

    keyboard = [[key] for key in SECTIONS.keys()] + [["Помощь", "Статистика"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.effective_message.reply_text("Привет! Я бот для практики диагностики. Выберите раздел:",
                                              reply_markup=reply_markup)
    return START


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Инструкция: Выберите раздел, затем решайте случаи. Задавайте вопросы и ставьте диагноз.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    stats = user_stats.get(user_id, {'correct': 0, 'total': 0})
    await update.effective_message.reply_text(f"Статистика: Правильных: {stats['correct']}/{stats['total']}")


async def new_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    table_name = user_states[user_id].get('section_table')
    if not table_name:
        return await start(update, context)  # Если нет раздела, назад в меню

    cases = get_cases(table_name)
    if not cases:
        await update.effective_message.reply_text("В этом разделе пока нет случаев.")
        return await start(update, context)

    case = random.choice(cases)
    user_states[user_id] = {'state': CASE_ACTIVE, 'current_case': case, 'revealed': set(), 'section_table': table_name}

    inline_keyboard = [
        [InlineKeyboardButton("Задать вопросы", callback_data='questions')],
        [InlineKeyboardButton("Поставить диагноз", callback_data='diagnose')],
        [InlineKeyboardButton("Завершить", callback_data='end')]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard)
    await update.effective_message.reply_text(case['base'], reply_markup=reply_markup)
    return CASE_ACTIVE


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    state = user_states.get(user_id, {})
    if not state:
        return await start(update, context)

    case = state.get('current_case')

    try:
        if query.data == 'questions':
            inline_keyboard = [
                [InlineKeyboardButton("Лабораторные данные", callback_data='lab')],
                [InlineKeyboardButton("Инструментальные", callback_data='instrumental')],
                [InlineKeyboardButton("Назад", callback_data='back')]
            ]
            await query.edit_message_reply_markup(InlineKeyboardMarkup(inline_keyboard))

        elif query.data in ['lab', 'instrumental']:
            if query.data not in state['revealed']:
                state['revealed'].add(query.data)
                data = case.get(query.data, "Данные недоступны.")
                await query.message.reply_text(data)
            # Замена рекурсии: возвращаем к меню вопросов
            inline_keyboard = [
                [InlineKeyboardButton("Лабораторные данные", callback_data='lab')],
                [InlineKeyboardButton("Инструментальные", callback_data='instrumental')],
                [InlineKeyboardButton("Назад", callback_data='back')]
            ]
            await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard))

        elif query.data == 'diagnose':
            inline_keyboard = [[InlineKeyboardButton(opt, callback_data=f'diag_{i}')] for i, opt in
                               enumerate(case['options'])]
            inline_keyboard.append([InlineKeyboardButton("Назад", callback_data='back')])
            await query.edit_message_text(text=query.message.text + "\n\nВыберите диагноз:",
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard))

        elif query.data.startswith('diag_'):
            selected = case['options'][int(query.data.split('_')[1])]
            stats = user_stats[user_id]
            stats['total'] += 1
            if selected == case['correct_diagnosis']:
                stats['correct'] += 1
                msg = f"Верно! {case['explanation']}"
            else:
                msg = f"Неправильно. Подсказка: {case['explanation'][:50]}... Попробуйте снова."
            await query.message.reply_text(msg)

            inline_keyboard = [
                [InlineKeyboardButton("Новый случай в этом разделе", callback_data='new_same')],
                [InlineKeyboardButton("Выбрать другой раздел", callback_data='menu')]
            ]
            await query.edit_message_reply_markup(InlineKeyboardMarkup(inline_keyboard))

        elif query.data == 'back':
            inline_keyboard = [
                [InlineKeyboardButton("Задать вопросы", callback_data='questions')],
                [InlineKeyboardButton("Поставить диагноз", callback_data='diagnose')],
                [InlineKeyboardButton("Завершить", callback_data='end')]
            ]
            await query.edit_message_reply_markup(InlineKeyboardMarkup(inline_keyboard))

        elif query.data == 'end':
            if user_id in user_states:
                del user_states[user_id]
            await query.message.reply_text("Сеанс завершён.")
            return await start(update, context)

        elif query.data == 'new_same':
            table_name = state['section_table']
            cases = get_cases(table_name)
            case = random.choice(cases)
            user_states[user_id]['current_case'] = case
            user_states[user_id]['revealed'] = set()

            inline_keyboard = [
                [InlineKeyboardButton("Задать вопросы", callback_data='questions')],
                [InlineKeyboardButton("Поставить диагноз", callback_data='diagnose')],
                [InlineKeyboardButton("Завершить", callback_data='end')]
            ]
            await query.edit_message_text(text=case['base'], reply_markup=InlineKeyboardMarkup(inline_keyboard))
            return CASE_ACTIVE

        elif query.data == 'menu':
            if user_id in user_states:
                del user_states[user_id]
            return await start(update, context)

    except Exception as e:
        logger.error(f"Error in button_handler: {e}")
        await query.message.reply_text("Произошла ошибка. Попробуйте снова.")

    return state.get('state', START)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    user_id = update.effective_user.id

    if text in SECTIONS:
        section_code = SECTIONS[text]
        table_name = f"{section_code}_cases"
        user_states[user_id]['section_table'] = table_name
        return await new_case(update, context)
    elif text == "Помощь":
        await help_command(update, context)
    elif text == "Статистика":
        await stats_command(update, context)
    return START


async def add_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id != 542889252:  # Замените на ваш Telegram ID
        await update.effective_message.reply_text("Доступ запрещён.")
        return

    args = context.args
    if len(args) != 7:
        await update.effective_message.reply_text(
            "Формат: /addcase section base lab instrumental correct_diagnosis options explanation\nГде section: cardio, digestive, urinary, blood, respiratory")
        return

    section = args[0].lower()
    if section not in ['cardio', 'digestive', 'urinary', 'blood', 'respiratory']:
        await update.effective_message.reply_text(
            "Неверный раздел. Доступные: cardio, digestive, urinary, blood, respiratory")
        return

    data = args[1:]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    table = f"{section}_cases"
    c.execute(f'''
        INSERT INTO {table} (base, lab, instrumental, correct_diagnosis, options, explanation)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', data)

    c.execute(f'''
        INSERT INTO general_cases (base, lab, instrumental, correct_diagnosis, options, explanation)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', data)

    conn.commit()
    conn.close()
    await update.effective_message.reply_text("Случай добавлен в раздел и в общий!")


def main() -> None:
    # Инициализируем базу данных
    init_db()

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            START: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            CASE_ACTIVE: [CallbackQueryHandler(button_handler)],
        },
        fallbacks=[CommandHandler('start', start)],
        per_chat=True,
        per_user=True
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('stats', stats_command))
    application.add_handler(CommandHandler('addcase', add_case))
    # Глобальный хендлер для текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Запуск с webhook (замена polling)
    port = int(os.environ.get('PORT', 8443))  # Для Heroku или другого хостинга
    webhook_url = f"https://your-app-name.herokuapp.com/{TOKEN}"  # Замените на ваш реальный URL!
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=webhook_url
    )


if __name__ == '__main__':
    main()