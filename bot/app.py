from datetime import datetime, time, timedelta
import pytz
import os

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler, 
    JobQueue
)
from telegram.error import BadRequest
import nest_asyncio
nest_asyncio.apply()

TOKEN = "7163266270:AAHiO2VqNdY7KPdn7MA_YIKKAt4KkQ-mfdQ"

START_CHOICE, GET_COUNT, GET_NAMES, CONFIRM_NAMES, HANDLE_ORDER, EDIT_MENU, ADD_MEMBER, REMOVE_MEMBER, REORDER_MEMBERS = range(9)

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['CHAT_ID'] = update.effective_chat.id
    
    hello_keyboard = [
        [InlineKeyboardButton("Погнали!", callback_data="start_now"), 
        InlineKeyboardButton("Настрою тебя позже", callback_data="start_later")]
    ]

    await update.message.reply_text(
        "✨ *Привет, это Фея Уборки!* ✨\n\n"
        "Я помогу организовать график уборки в вашем блоке.\n\n"
        "Готовы начать настройку прямо сейчас?",
        reply_markup=InlineKeyboardMarkup(hello_keyboard),
        parse_mode="Markdown"
    )

    return START_CHOICE

async def handle_start_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "start_now":
        count_keyboard = [[
            InlineKeyboardButton("1", callback_data="1"),
            InlineKeyboardButton("2", callback_data="2"),
            InlineKeyboardButton("3", callback_data="3"),
            InlineKeyboardButton("4", callback_data="4"),
            InlineKeyboardButton("5", callback_data="5"),
            InlineKeyboardButton("6", callback_data="6")
        ]]

        await query.edit_message_text(
            "Отлично! Давайте начнем.\n\n"
            "Сколько человек будет участвовать в уборке?",
            reply_markup=InlineKeyboardMarkup(count_keyboard),
            parse_mode="Markdown"
        )
        return GET_COUNT
    else:
        await query.edit_message_text(
            "Хорошо! Когда будете готовы настроить график уборки, "
            "вызовите команду /hello снова.\n\n"
            "До новых чистых встреч! ✨",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
async def get_member_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    member_cnt = int(query.data)

    context.user_data["MEMBER_COUNT"] = member_cnt 
    context.user_data['MEMBERS'] = {}
    context.user_data['BUFFER_MSG'] = None

    msg = await query.edit_message_text(
        "📝 *Введите имена участников по одному:*\n\n"
        "Список пока пуст...\n\n"
        f"Осталось ввести: {member_cnt}",
        parse_mode="Markdown"
    )

    context.user_data['MSG_BUFFER'] = msg

    return GET_NAMES

async def get_member_names(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    context.user_data['MEMBERS'][name] = 0
    
    names_list = "\n".join(f"▪ {name}" for name in context.user_data['MEMBERS'])

    rest_cnt = context.user_data['MEMBER_COUNT'] - len(context.user_data['MEMBERS'])

    await context.user_data['MSG_BUFFER'].edit_text(
        f"📝 *Введите имена участников по одному:*\n\n"
        f"{names_list}\n\n"
        f"Осталось ввести: {rest_cnt}",
        parse_mode="Markdown"
    )

    try:
        await update.message.delete()
    except:
        pass

    if len(context.user_data['MEMBERS']) >= context.user_data['MEMBER_COUNT']:
        context.user_data['CURRENT_POSITION'] = 1
        try:
            await update.message.delete()
        except:
            pass

        confirm_keyboard = [
            [InlineKeyboardButton("✅ Да, все верно", callback_data="yes")],
            [InlineKeyboardButton("❌ Нет, ввести заново", callback_data="no")]
        ]
        names_text = "\n".join(f"▪ {n}" for n in context.user_data['MEMBERS'])
        await context.bot.send_message(
            chat_id=context.user_data['CHAT_ID'],
            text=f"📋 *Подтвердите список участников:*\n\n{names_text}",
            reply_markup=InlineKeyboardMarkup(confirm_keyboard),
            parse_mode="Markdown"
        )
        return CONFIRM_NAMES
    return GET_NAMES

async def confirm_names(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "yes":
        try:
            await query.message.delete()
        except:
            pass

        return await setup_order(update, context)

    else:
        try:
            await query.message.delete()
        except:
            pass

        context.user_data['MEMBERS'] = {}
        context.user_data['CURRENT_POSITION'] = 1

        if 'MSG_BUFFER' in context.user_data:
            try:
                await context.user_data['MSG_BUFFER'].delete()
                del context.user_data['MSG_BUFFER']
            except:
                pass

        msg = await context.bot.send_message(
            chat_id=context.user_data['CHAT_ID'],
            text="*Список сброшен.*\n\n📝 Введите имена участников по одному:",
            parse_mode="Markdown"
        )
        context.user_data['MSG_BUFFER'] = msg

        return GET_NAMES

async def setup_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'BUFFER_MSG' in context.user_data:
        try:
            await context.user_data['BUFFER_MSG'].delete()
        except:
            pass
    member_keyboard = []
    for name in context.user_data['MEMBERS']:
        if context.user_data['MEMBERS'][name] == 0:
            member_keyboard.append([InlineKeyboardButton(
                f"{name}", 
                callback_data=f"{name}"
            )])

    member_keyboard.append([InlineKeyboardButton("✅ Завершить ввод", callback_data="done"), InlineKeyboardButton("🔄 Сбросить порядок", callback_data="reset")])
    
    current_order = []
    for name, pos in sorted(
        context.user_data['MEMBERS'].items(), 
        key=lambda x: x[1] if x[1] > 0 else float('inf')
    ):
        if pos > 0:
            current_order.append(f"{pos}. {name}")
        else:
            current_order.append(f"➖ {name}")
    ordered_list = "\n".join(current_order)
    
    msg = await context.bot.send_message(
        chat_id=context.user_data['CHAT_ID'],
        text=f"🔢 *Установите порядок уборки:*\n\n"
             f"Текущее распределение:\n{ordered_list}\n\n"
             f"Выберите, кто будет убираться следующим:",
        reply_markup=InlineKeyboardMarkup(member_keyboard),
        parse_mode="Markdown"
    )

    context.user_data['BUFFER_MSG'] = msg
    return HANDLE_ORDER

async def handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "done":
        if any(pos == 0 for pos in context.user_data['MEMBERS'].values()):
            await query.answer("Не все участники распределены!", show_alert=True)
            return HANDLE_ORDER
            
        sorted_names = sorted(context.user_data['MEMBERS'].items(), key=lambda x: x[1])
        ordered_list = "\n".join(f"{pos}. {name}" for name, pos in sorted_names)
        
        try:
            await query.message.delete()
        except:
            pass

        await context.bot.send_message(
            chat_id=context.user_data['CHAT_ID'],
            text=f"✨ *График уборки установлен!* ✨\n\n"
                 f"Очередность:\n{ordered_list}\n\n"
                 "Теперь я буду напоминать каждую неделю, чья очередь наводить порядок в блоке :)\n\n"
                 "Используйте команды:\n"
                 "/edit - изменить список\n"
                 "/schedule - посмотреть график\n"
                 "/help - справка по командам",
            parse_mode="Markdown"
        )
        
        now = datetime.now()
        context.user_data['NEXT_MONDAY'] = now + timedelta(days=(7 - now.weekday()) % 7)
        context.user_data['NEXT_MONDAY'] = context.user_data['NEXT_MONDAY'].replace(hour=9, minute=0, second=0, microsecond=0)

        delay = (context.user_data['NEXT_MONDAY'] - now).total_seconds()

        members = context.user_data['MEMBERS']
        job_data = {
            'chat_id': context.user_data['CHAT_ID'],
            'members': members,
            'current_index': 0
        }

        context.job_queue.run_repeating(
            send_weekly_reminder,
            interval=7 * 24 * 60 * 60,  # раз в неделю
            first=delay,
            data=job_data,
            name="weekly_cleaning_reminder"
        )

        return ConversationHandler.END
    
    elif query.data == "reset":
        for name in context.user_data['MEMBERS']:
            context.user_data['MEMBERS'][name] = 0
        context.user_data['CURRENT_POSITION'] = 1
        
        await query.answer("Порядок сброшен!")
        return await setup_order(update, context)
    
    else:
        context.user_data['MEMBERS'][query.data] = context.user_data['CURRENT_POSITION']
        context.user_data['CURRENT_POSITION'] += 1
        return await setup_order(update, context)

async def send_weekly_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data['chat_id']
    members = job.data['members']
    curr_week_num = job.data['curr_week_num']

    names = list(members.keys())
    current_name = names[curr_week_num % len(names)]

    await context.bot.send_message(
        chat_id=chat_id,
        # TODO: добавить никнеймы в тг
        text=f"🧹 *Это снова Фея Уборки с напоминанием :)* \n\n"
             f"На этой неделе порядок наводит **{current_name}**\n"
             "Не забудь отметиться в моём следующем напоминании.",
        parse_mode="Markdown"
    )

    job.data['curr_week_num'] += 1

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'MEMBERS' not in context.user_data or not context.user_data['MEMBERS']:
        await update.message.reply_text("❌ График ещё не настроен.")
        return

    members = context.user_data['MEMBERS']
    ordered = sorted(members.items(), key=lambda x: x[1])

    start_date = context.user_data.get('SCHEDULE_START_DATE')
    if not start_date:
        start_date = datetime.now(pytz.utc).date()
        context.user_data['SCHEDULE_START_DATE'] = start_date

    today = datetime.now(pytz.utc).date()
    delta_days = (today - start_date).days
    week_number = delta_days // 7
    current_index = (week_number) % len(members)

    schedule_lines = []
    for i, (name, _) in enumerate(ordered):
        week_offset = i - current_index
        date = today + timedelta(days=-(delta_days % 7)) + timedelta(weeks=week_offset)
        status = "👉" if i == current_index else ""
        schedule_lines.append(f"{status} {i+1}. {name} — {date.strftime('%d.%m.%Y')}")

    schedule_text = "\n".join(schedule_lines)

    await update.message.reply_text(
        "📅 *График уборки с датами:*\n\n" + schedule_text,
        parse_mode="Markdown"
    )

async def edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'MEMBERS' not in context.user_data or not context.user_data['MEMBERS']:
        await update.message.reply_text("Графика уборки нет, для начала настройте его, используя команду /hello")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("➕ Добавить участника", callback_data="add")],
        [InlineKeyboardButton("➖ Удалить участника", callback_data="remove")],
        [InlineKeyboardButton("🔄 Изменить очерёдность", callback_data="reorder")],
        [InlineKeyboardButton("↩️ Назад", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("🛠️ *Режим редактирования графика*", reply_markup=reply_markup, parse_mode="Markdown")
    return EDIT_MENU

async def edit_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "add":
        msg = await query.edit_message_text("Введите имя нового участника:")
        context.user_data["EDIT_MODE"] = "ADD"
        return ADD_MEMBER

    elif query.data == "remove":
        keyboard = []
        for name in context.user_data['MEMBERS']:
            keyboard.append([InlineKeyboardButton(f"🗑️ {name}", callback_data=f"remove_{name}")])
        keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data="back")])

        await query.edit_message_text("Выберите участника для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
        return REMOVE_MEMBER

    elif query.data == "reorder":
        names = list(context.user_data['MEMBERS'].keys())
        keyboard = []
        for i, name in enumerate(names):
            pos = i + 1
            keyboard.append([InlineKeyboardButton(f"{pos}. {name}", callback_data=f"reorder_{i}")])

        await query.edit_message_text("Выберите порядковый номер для изменения:", reply_markup=InlineKeyboardMarkup(keyboard))
        return REORDER_MEMBERS

    elif query.data == "back":
        await query.edit_message_text("Вы вышли из режима редактирования.")
        return ConversationHandler.END

async def add_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if name in context.user_data['MEMBERS']:
        await update.message.reply_text("⚠️ Такой участник уже есть!")
        return ADD_MEMBER

    context.user_data['MEMBERS'][name] = 0
    context.user_data['MEMBER_COUNT'] += 1

    await update.message.reply_text(f"✅ Участник *{name}* успешно добавлен.", parse_mode="Markdown")

    context.user_data['CURRENT_POSITION'] += 1
    return await setup_order(update, context)

async def remove_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    name_to_remove = query.data.replace("remove_", "")
    del context.user_data['MEMBERS'][name_to_remove]
    context.user_data['MEMBER_COUNT'] -= 1

    await query.edit_message_text(f"✅ Участник *{name_to_remove}* удалён.")

    context.user_data['CURRENT_POSITION'] = 1
    return await setup_order(update, context)

async def reorder_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    index = int(query.data.replace("reorder_", ""))
    names = list(context.user_data['MEMBERS'].keys())
    name = names[index]

    context.user_data['REORDER_INDEX'] = index

    keyboard = []
    for i in range(1, len(names) + 1):
        keyboard.append([InlineKeyboardButton(str(i), callback_data=f"new_pos_{i}")])

    await query.edit_message_text(f"Выберите новую позицию для участника: **{name}**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return REORDER_MEMBERS

async def reorder_members_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    new_pos = int(query.data.replace("new_pos_", ""))
    names = list(context.user_data['MEMBERS'].keys())
    old_index = context.user_data.get('REORDER_INDEX', 0)
    name = names[old_index]

    # Удаляем старое имя
    del names[old_index]
    names.insert(new_pos - 1, name)

    # Обновляем словарь с позициями
    for i, n in enumerate(names):
        context.user_data['MEMBERS'][n] = i + 1

    await query.edit_message_text(f"✅ Порядок изменён!\nТеперь *{name}* на {new_pos}-м месте.", parse_mode="Markdown")
    return await setup_order(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог отменён.")
    return ConversationHandler.END

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 *Доступные команды:*\n\n"
        "/edit — Редактировать список участников или изменить очередь\n"
        "/schedule — Посмотреть текущий график уборки с датами\n"
        "/help — Показать это сообщение\n"
        "/cancel — Прервать текущую операцию\n"
    )

    await update.effective_message.reply_text(help_text, parse_mode="Markdown")

    
def main() -> None:
    job_queue = JobQueue()

    application = Application.builder().token(TOKEN).job_queue(job_queue).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("hello", hello),
            CommandHandler("edit", edit_menu),
            CommandHandler("schedule", show_schedule)
        ],
        states={
            START_CHOICE: [CallbackQueryHandler(handle_start_choice)],
            GET_COUNT: [CallbackQueryHandler(get_member_count)],
            GET_NAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_member_names)],
            CONFIRM_NAMES: [CallbackQueryHandler(confirm_names)],
            HANDLE_ORDER: [CallbackQueryHandler(handle_order)],

            EDIT_MENU: [CallbackQueryHandler(edit_menu_handler)],
            ADD_MEMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_member)],
            REMOVE_MEMBER: [CallbackQueryHandler(remove_member)],
            REORDER_MEMBERS: [
                CallbackQueryHandler(reorder_members, pattern=r"^reorder_\d+$"),
                CallbackQueryHandler(reorder_members_set, pattern=r"^new_pos_\d+$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ]
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help))

    job_queue.start()
    application.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 5000)),
    webhook_url="https://your-app-name.scalingo.io/" + TOKEN
)

if __name__ == "__main__":
    main()  
