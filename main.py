from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold
import asyncio
from config_reader import config
import logging

logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.token.get_secret_value())

dp = Dispatcher()

class Form(StatesGroup):
    start_choice = State()
    get_count = State()
    get_names = State()
    confirm_names = State()
    handle_order = State()
    edit_menu = State()
    add_member = State()
    remove_member = State()
    reorder_members = State()

user_data = {}

async def send_weekly_reminder(chat_id: int, members: dict, current_index: int):
    names = list(members.keys())
    current_name = names[current_index % len(names)]
    
    await bot.send_message(
        chat_id=chat_id,
        text=f"🧹 {hbold('Это снова Фея Уборки с напоминанием :)')}\n\n"
             f"На этой неделе порядок наводит {hbold(current_name)}\n"
             "Не забудь отметиться в моём следующем напоминании."
    )

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    user_data[message.chat.id] = {
        'chat_id': message.chat.id,
        'members': {},
        'buffer_msg': None
    }
    
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="Погнали!", callback_data="start_now"),
        types.InlineKeyboardButton(text="Настрою тебя позже", callback_data="start_later")
    )
    
    await message.answer(
        f"✨ {hbold('Привет, это Фея Уборки!')} ✨\n\n"
        "Я помогу организовать график уборки в вашем блоке.\n\n"
        "Готовы начать настройку прямо сейчас?",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(Form.start_choice)

@dp.callback_query(Form.start_choice, F.data == "start_now")
async def handle_start_now(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for i in range(1, 7):
        builder.add(types.InlineKeyboardButton(text=str(i), callback_data=str(i)))
    builder.adjust(3)
    
    await callback.message.edit_text(
        "Отлично! Давайте начнем.\n\n"
        "Сколько человек будет участвовать в уборке?",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(Form.get_count)

@dp.callback_query(Form.start_choice, F.data == "start_later")
async def handle_start_later(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Хорошо! Когда будете готовы настроить график уборки, "
        "вызовите команду /hello снова.\n\n"
        "До новых чистых встреч! ✨"
    )
    await state.clear()

@dp.callback_query(Form.get_count)
async def get_member_count(callback: types.CallbackQuery, state: FSMContext):
    member_cnt = int(callback.data)
    user_data[callback.message.chat.id]['member_count'] = member_cnt
    user_data[callback.message.chat.id]['current_position'] = 1
    
    msg = await callback.message.edit_text(
        f"📝 {hbold('Введите имена участников по одному:')}\n\n"
        "Список пока пуст...\n\n"
        f"Осталось ввести: {member_cnt}"
    )
    
    user_data[callback.message.chat.id]['msg_buffer'] = msg
    await state.set_state(Form.get_names)

@dp.message(Form.get_names)
async def get_member_names(message: types.Message, state: FSMContext):
    name = message.text.strip()
    chat_id = message.chat.id
    user_data[chat_id]['members'][name] = 0
    
    names_list = "\n".join(f"▪ {name}" for name in user_data[chat_id]['members'])
    rest_cnt = user_data[chat_id]['member_count'] - len(user_data[chat_id]['members'])
    
    try:
        await user_data[chat_id]['msg_buffer'].edit_text(
            f"📝 {hbold('Введите имена участников по одному:')}\n\n"
            f"{names_list}\n\n"
            f"Осталось ввести: {rest_cnt}"
        )
        await message.delete()
    except:
        pass

    if len(user_data[chat_id]['members']) >= user_data[chat_id]['member_count']:
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(text="✅ Да, все верно", callback_data="yes"),
            types.InlineKeyboardButton(text="❌ Нет, ввести заново", callback_data="no")
        )
        
        names_text = "\n".join(f"▪ {n}" for n in user_data[chat_id]['members'])
        await message.answer(
            f"📋 {hbold('Подтвердите список участников:')}\n\n{names_text}",
            reply_markup=builder.as_markup()
        )
        await state.set_state(Form.confirm_names)

@dp.callback_query(Form.confirm_names, F.data == "yes")
async def confirm_names_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await setup_order(callback.message.chat.id, state)

@dp.callback_query(Form.confirm_names, F.data == "no")
async def confirm_names_no(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    user_data[chat_id]['members'] = {}
    user_data[chat_id]['current_position'] = 1
    
    try:
        await user_data[chat_id]['msg_buffer'].delete()
    except:
        pass
    
    msg = await callback.message.answer(
        f"{hbold('Список сброшен.')}\n\n📝 Введите имена участников по одному:"
    )
    user_data[chat_id]['msg_buffer'] = msg
    await state.set_state(Form.get_names)

async def setup_order(chat_id: int, state: FSMContext):
    try:
        await user_data[chat_id]['buffer_msg'].delete()
    except:
        pass
    
    builder = InlineKeyboardBuilder()
    for name in user_data[chat_id]['members']:
        if user_data[chat_id]['members'][name] == 0:
            builder.add(types.InlineKeyboardButton(text=name, callback_data=name))
    
    builder.adjust(2)
    builder.row(
        types.InlineKeyboardButton(text="✅ Завершить ввод", callback_data="done"),
        types.InlineKeyboardButton(text="🔄 Сбросить порядок", callback_data="reset")
    )
    
    current_order = []
    for name, pos in sorted(
        user_data[chat_id]['members'].items(), 
        key=lambda x: x[1] if x[1] > 0 else float('inf')
    ):
        if pos > 0:
            current_order.append(f"{pos}. {name}")
        else:
            current_order.append(f"➖ {name}")
    ordered_list = "\n".join(current_order)
    
    msg = await bot.send_message(
        chat_id=chat_id,
        text=f"🔢 {hbold('Установите порядок уборки:')}\n\n"
             f"Текущее распределение:\n{ordered_list}\n\n"
             f"Выберите, кто будет убираться следующим:",
        reply_markup=builder.as_markup()
    )
    
    user_data[chat_id]['buffer_msg'] = msg
    await state.set_state(Form.handle_order)

@dp.callback_query(Form.handle_order, F.data == "done")
async def handle_order_done(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    
    if any(pos == 0 for pos in user_data[chat_id]['members'].values()):
        await callback.answer("Не все участники распределены!", show_alert=True)
        return
    
    sorted_names = sorted(user_data[chat_id]['members'].items(), key=lambda x: x[1])
    ordered_list = "\n".join(f"{pos}. {name}" for name, pos in sorted_names)
    
    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer(
        f"✨ {hbold('График уборки установлен!')} ✨\n\n"
        f"Очередность:\n{ordered_list}\n\n"
        "Теперь я буду напоминать каждую неделю, чья очередь наводить порядок в блоке :)\n\n"
        "Используйте команды:\n"
        "/edit - изменить список\n"
        "/schedule - посмотреть график\n"
        "/help - справка по командам"
    )
    
    now = datetime.now(pytz.utc)
    next_monday = now + timedelta(days=(7 - now.weekday()) % 7)
    next_monday = next_monday.replace(hour=9, minute=0, second=0, microsecond=0)
    
    delay = (next_monday - now).total_seconds()
    
    asyncio.create_task(schedule_weekly_reminder(
        chat_id, 
        user_data[chat_id]['members'], 
        delay
    ))
    
    await state.clear()

async def schedule_weekly_reminder(chat_id: int, members: dict, delay: float):
    await asyncio.sleep(delay)
    current_index = 0
    
    while True:
        await send_weekly_reminder(chat_id, members, current_index)
        current_index += 1
        await asyncio.sleep(7 * 24 * 60 * 60)  # Sleep for 1 week

@dp.callback_query(Form.handle_order, F.data == "reset")
async def handle_order_reset(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    for name in user_data[chat_id]['members']:
        user_data[chat_id]['members'][name] = 0
    user_data[chat_id]['current_position'] = 1
    
    await callback.answer("Порядок сброшен!")
    await setup_order(chat_id, state)

@dp.callback_query(Form.handle_order)
async def handle_order_select(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    name = callback.data
    user_data[chat_id]['members'][name] = user_data[chat_id]['current_position']
    user_data[chat_id]['current_position'] += 1
    
    await setup_order(chat_id, state)

@dp.message(Command("schedule"))
async def show_schedule(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in user_data or not user_data[chat_id].get('members'):
        await message.answer("❌ График ещё не настроен.")
        return
    
    members = user_data[chat_id]['members']
    ordered = sorted(members.items(), key=lambda x: x[1])
    
    start_date = user_data[chat_id].get('schedule_start_date')
    if not start_date:
        start_date = datetime.now(pytz.utc).date()
        user_data[chat_id]['schedule_start_date'] = start_date
    
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
    
    await message.answer(f"📅 {hbold('График уборки с датами:')}\n\n{schedule_text}")

@dp.message(Command("edit"))
async def edit_menu(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    if chat_id not in user_data or not user_data[chat_id].get('members'):
        await message.answer("Графика уборки нет, для начала настройте его, используя команду /hello")
        return
    
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="➕ Добавить участника", callback_data="add"),
        types.InlineKeyboardButton(text="➖ Удалить участника", callback_data="remove"),
        types.InlineKeyboardButton(text="🔄 Изменить очерёдность", callback_data="reorder"),
        types.InlineKeyboardButton(text="↩️ Назад", callback_data="back")
    )
    builder.adjust(1)
    
    await message.answer(
        f"🛠️ {hbold('Режим редактирования графика')}",
        reply_markup=builder.as_markup()
    )
    await state.set_state(Form.edit_menu)

@dp.callback_query(Form.edit_menu, F.data == "add")
async def edit_menu_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите имя нового участника:")
    await state.set_state(Form.add_member)

@dp.callback_query(Form.edit_menu, F.data == "remove")
async def edit_menu_remove(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    builder = InlineKeyboardBuilder()
    for name in user_data[chat_id]['members']:
        builder.add(types.InlineKeyboardButton(text=f"🗑️ {name}", callback_data=f"remove_{name}"))
    builder.add(types.InlineKeyboardButton(text="↩️ Назад", callback_data="back"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        "Выберите участника для удаления:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(Form.remove_member)

@dp.callback_query(Form.edit_menu, F.data == "reorder")
async def edit_menu_reorder(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    names = list(user_data[chat_id]['members'].keys())
    builder = InlineKeyboardBuilder()
    for i, name in enumerate(names):
        pos = i + 1
        builder.add(types.InlineKeyboardButton(text=f"{pos}. {name}", callback_data=f"reorder_{i}"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        "Выберите порядковый номер для изменения:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(Form.reorder_members)

@dp.callback_query(Form.edit_menu, F.data == "back")
async def edit_menu_back(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Вы вышли из режима редактирования.")
    await state.clear()

@dp.message(Form.add_member)
async def add_member(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    name = message.text.strip()
    
    if name in user_data[chat_id]['members']:
        await message.answer("⚠️ Такой участник уже есть!")
        return
    
    user_data[chat_id]['members'][name] = 0
    user_data[chat_id]['member_count'] += 1
    user_data[chat_id]['current_position'] += 1
    
    await message.answer(f"✅ Участник {hbold(name)} успешно добавлен.")
    await setup_order(chat_id, state)

@dp.callback_query(Form.remove_member, F.data.startswith("remove_"))
async def remove_member(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    name_to_remove = callback.data.replace("remove_", "")
    
    del user_data[chat_id]['members'][name_to_remove]
    user_data[chat_id]['member_count'] -= 1
    user_data[chat_id]['current_position'] = 1
    
    await callback.message.edit_text(f"✅ Участник {hbold(name_to_remove)} удалён.")
    await setup_order(chat_id, state)

@dp.callback_query(Form.reorder_members, F.data.startswith("reorder_"))
async def reorder_members_select(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    index = int(callback.data.replace("reorder_", ""))
    names = list(user_data[chat_id]['members'].keys())
    name = names[index]
    
    user_data[chat_id]['reorder_index'] = index
    
    builder = InlineKeyboardBuilder()
    for i in range(1, len(names) + 1):
        builder.add(types.InlineKeyboardButton(text=str(i), callback_data=f"new_pos_{i}"))
    builder.adjust(3)
    
    await callback.message.edit_text(
        f"Выберите новую позицию для участника: {hbold(name)}",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(Form.reorder_members, F.data.startswith("new_pos_"))
async def reorder_members_set(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    new_pos = int(callback.data.replace("new_pos_", ""))
    names = list(user_data[chat_id]['members'].keys())
    old_index = user_data[chat_id].get('reorder_index', 0)
    name = names[old_index]
    
    # Удаляем старое имя
    del names[old_index]
    names.insert(new_pos - 1, name)
    
    # Обновляем словарь с позициями
    for i, n in enumerate(names):
        user_data[chat_id]['members'][n] = i + 1
    
    await callback.message.edit_text(
        f"✅ Порядок изменён!\nТеперь {hbold(name)} на {new_pos}-м месте."
    )
    await setup_order(chat_id, state)

@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = (
        f"📚 {hbold('Доступные команды:')}\n\n"
        "/edit — Редактировать список участников или изменить очередь\n"
        "/schedule — Посмотреть текущий график уборки с датами\n"
        "/help — Показать это сообщение\n"
        "/cancel — Прервать текущую операцию"
    )
    await message.answer(help_text)

@dp.message(Command("cancel"))
async def cancel_command(message: types.Message, state: FSMContext):
    await message.answer("Диалог отменён.")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
