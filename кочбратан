import asyncio
import logging
import os
import random
from datetime import datetime, timedelta

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "9239343763:AAEdUUahoxRPNkuEVoz3NP_GwOa_s1GjeKg"  # токен от @BotFather
ADMIN_IDS = [6956175793]                                        # ваши Telegram ID
SELLER_USERNAME = "stylepyt"                            # username продавца без @
PAYMENT_INFO = "Перевод на карту: 2202 2000 0000 0000"         # реквизиты для оплаты
DB_PATH = "shop.db"
# ===================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============ База данных ============
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                stars_amount INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                stars_prize INTEGER,
                end_time TIMESTAMP,
                max_participants INTEGER,
                status TEXT DEFAULT 'active',
                winner_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS participants (
                giveaway_id INTEGER,
                user_id INTEGER,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (giveaway_id, user_id)
            );
        """)
        await db.commit()


# ============ Клавиатуры ============
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ Купить звёзды", callback_data="buy")
    kb.button(text="🎁 Розыгрыши", callback_data="giveaway_list")
    kb.adjust(1)
    return kb.as_markup()


def stars_menu():
    kb = InlineKeyboardBuilder()
    for amount in [50, 100, 250, 500, 1000]:
        kb.button(text=f"{amount} ⭐", callback_data=f"order_{amount}")
    kb.button(text="◀️ Назад", callback_data="back_main")
    kb.adjust(2)
    return kb.as_markup()


def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Заказы", callback_data="admin_orders")
    kb.button(text="🎁 Создать розыгрыш", callback_data="admin_create_giveaway")
    kb.button(text="🎲 Выбрать победителя", callback_data="admin_draw")
    kb.adjust(1)
    return kb.as_markup()


# ============ FSM ============
class GiveawayForm(StatesGroup):
    title = State()
    stars = State()
    duration = State()
    max_participants = State()


# ============ Старт ============
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"Добро пожаловать, {message.from_user.first_name}!\n"
        "Здесь можно купить звёзды или участвовать в розыгрышах.",
        reply_markup=main_menu()
    )


@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()


# ============ Покупка звёзд ============
@dp.callback_query(F.data == "buy")
async def buy_stars(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Выберите количество звёзд:",
        reply_markup=stars_menu()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("order_"))
async def create_order(callback: types.CallbackQuery):
    amount = int(callback.data.split("_")[1])
    user = callback.from_user

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, stars_amount) VALUES (?, ?, ?)",
            (user.id, user.username or user.first_name, amount)
        )
        order_id = cursor.lastrowid
        await db.commit()

    text = (
        f"✅ Заказ #{order_id} создан\n\n"
        f"⭐ Количество: {amount} звёзд\n"
        f"💰 К оплате: {PAYMENT_INFO}\n\n"
        f"После перевода напишите продавцу: @{SELLER_USERNAME}\n"
        f"Укажите номер заказа: #{order_id}\n\n"
        f"После подтверждения оплаты продавец отправит вам звёзды."
    )
    await callback.message.edit_text(text)
    await callback.answer()


# ============ Розыгрыши (пользователи) ============
@dp.callback_query(F.data == "giveaway_list")
async def list_giveaways(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, title, stars_prize, end_time, max_participants "
            "FROM giveaways WHERE status='active'"
        )
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.edit_text(
            "Сейчас нет активных розыгрышей.",
            reply_markup=main_menu()
        )
        await callback.answer()
        return

    kb = InlineKeyboardBuilder()
    for gid, title, stars, end_time, max_p in rows:
        kb.button(text=f"{title} ({stars}⭐)", callback_data=f"join_{gid}")
    kb.button(text="◀️ Назад", callback_data="back_main")
    kb.adjust(1)

    await callback.message.edit_text("Активные розыгрыши:", reply_markup=kb.as_markup())
    await callback.answer()


@dp.callback_query(F.data.startswith("join_"))
async def join_giveaway(callback: types.CallbackQuery):
    gid = int(callback.data.split("_")[1])
    user = callback.from_user

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT title, stars_prize, end_time, max_participants "
            "FROM giveaways WHERE id=? AND status='active'",
            (gid,)
        )
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Розыгрыш уже завершён.", show_alert=True)
            return

        title, stars, end_time, max_p = row

        if datetime.now() > datetime.fromisoformat(end_time):
            await callback.answer("Время розыгрыша истекло.", show_alert=True)
            return

        cursor = await db.execute(
            "SELECT COUNT(*) FROM participants WHERE giveaway_id=?", (gid,)
        )
        count = (await cursor.fetchone())[0]
        if count >= max_p:
            await callback.answer("Лимит участников достигнут.", show_alert=True)
            return

        cursor = await db.execute(
            "SELECT 1 FROM participants WHERE giveaway_id=? AND user_id=?",
            (gid, user.id)
        )
        if await cursor.fetchone():
            await callback.answer("Вы уже участвуете.", show_alert=True)
            return

        await db.execute(
            "INSERT INTO participants (giveaway_id, user_id, username) VALUES (?, ?, ?)",
            (gid, user.id, user.username or user.first_name)
        )
        await db.commit()

    await callback.answer("Вы участвуете! Удачи!", show_alert=True)


# ============ Админ-панель ============
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Панель администратора:", reply_markup=admin_menu())


@dp.callback_query(F.data == "admin_orders")
async def admin_orders(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, username, stars_amount, status "
            "FROM orders ORDER BY id DESC LIMIT 20"
        )
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.edit_text("Нет заказов.", reply_markup=admin_menu())
        await callback.answer()
        return

    lines = ["📋 Последние заказы:\n"]
    for oid, uname, stars, status in rows:
        lines.append(f"#{oid} | @{uname} | {stars}⭐ | {status}")

    await callback.message.edit_text("\n".join(lines), reply_markup=admin_menu())
    await callback.answer()


@dp.callback_query(F.data == "admin_create_giveaway")
async def admin_create_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.edit_text("Введите название розыгрыша:")
    await state.set_state(GiveawayForm.title)
    await callback.answer()


@dp.message(GiveawayForm.title)
async def gw_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите количество звёзд в призе (число):")
    await state.set_state(GiveawayForm.stars)


@dp.message(GiveawayForm.stars)
async def gw_stars(message: types.Message, state: FSMContext):
    try:
        stars = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(stars=stars)
    await message.answer("Длительность в минутах (например, 60):")
    await state.set_state(GiveawayForm.duration)


@dp.message(GiveawayForm.duration)
async def gw_duration(message: types.Message, state: FSMContext):
    try:
        minutes = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(duration=minutes)
    await message.answer("Максимальное количество участников:")
    await state.set_state(GiveawayForm.max_participants)


@dp.message(GiveawayForm.max_participants)
async def gw_max(message: types.Message, state: FSMContext):
    try:
        max_p = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return

    data = await state.get_data()
    end_time = datetime.now() + timedelta(minutes=data["duration"])

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO giveaways (title, stars_prize, end_time, max_participants) "
            "VALUES (?, ?, ?, ?)",
            (data["title"], data["stars"], end_time.isoformat(), max_p)
        )
        await db.commit()

    await message.answer(
        f"✅ Розыгрыш создан!\n"
        f"Название: {data['title']}\n"
        f"Приз: {data['stars']}⭐\n"
        f"Окончание: {end_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"Лимит участников: {max_p}"
    )
    await state.clear()


@dp.callback_query(F.data == "admin_draw")
async def admin_draw(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, title, stars_prize FROM giveaways WHERE status='active'"
        )
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.edit_text("Нет активных розыгрышей.", reply_markup=admin_menu())
        await callback.answer()
        return

    kb = InlineKeyboardBuilder()
    for gid, title, stars in rows:
        kb.button(text=f"{title} ({stars}⭐)", callback_data=f"draw_{gid}")
    kb.button(text="◀️ Назад", callback_data="admin_back")
    kb.adjust(1)

    await callback.message.edit_text(
        "Выберите розыгрыш для определения победителя:",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("draw_"))
async def do_draw(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    gid = int(callback.data.split("_")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, username FROM participants WHERE giveaway_id=?", (gid,)
        )
        participants = await cursor.fetchall()

        if not participants:
            await callback.answer("Нет участников.", show_alert=True)
            return

        winner_id, winner_name = random.choice(participants)

        await db.execute(
            "UPDATE giveaways SET status='ended', winner_id=? WHERE id=?",
            (winner_id, gid)
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT title, stars_prize FROM giveaways WHERE id=?", (gid,)
        )
        title, stars = await cursor.fetchone()

    await callback.message.edit_text(
        f"🎉 Розыгрыш «{title}» завершён!\n"
        f"Победитель: @{winner_name} (ID: {winner_id})\n"
        f"Приз: {stars}⭐\n\n"
        f"Свяжитесь с победителем для вручения приза."
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    await callback.message.edit_text("Панель администратора:", reply_markup=admin_menu())
    await callback.answer()


# ============ Запуск ============
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
