import asyncio
import logging
import random
from datetime import datetime, timedelta
from html import escape

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "9239343763:AAEdUUahoxRPNkuEVoz3NP_GwOa_s1GjeKg"

ADMIN_IDS = [6956175793, 1479120225]

SELLER_USERNAME = "manager_darexvod17"
PAYMENT_INFO = "Перевод на карту: 2202 2000 0000 0000"

START_IMAGE_URL = "https://example.com/start.jpg"

DB_PATH = "/app/data/shop.db"

MIN_STARS = 50
MAX_STARS = 10000
PARSE = "HTML"
# ===================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============ Безопасное редактирование ============
async def safe_edit(message: types.Message, text: str, reply_markup=None):
    try:
        if message.photo or message.video or message.document or message.animation:
            await message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=PARSE
            )
        else:
            await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=PARSE
            )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise


# ============ База данных ============
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                recipient TEXT,
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
                winner_id INTEGER,
                creator_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS participants (
                giveaway_id INTEGER,
                user_id INTEGER,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (giveaway_id, user_id)
            );
        """)
        cursor = await db.execute("PRAGMA table_info(orders)")
        cols = [r[1] for r in await cursor.fetchall()]
        if "recipient" not in cols:
            await db.execute("ALTER TABLE orders ADD COLUMN recipient TEXT")

        cursor = await db.execute("PRAGMA table_info(giveaways)")
        cols = [r[1] for r in await cursor.fetchall()]
        if "creator_id" not in cols:
            await db.execute("ALTER TABLE giveaways ADD COLUMN creator_id INTEGER")

        await db.commit()


# ============ Клавиатуры ============
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⭐ Купить звёзды", callback_data="buy"))
    kb.row(InlineKeyboardButton(text="🎁 Розыгрыши", callback_data="giveaway_list"))
    kb.row(InlineKeyboardButton(text="➕ Создать розыгрыш", callback_data="create_giveaway"))
    return kb.as_markup()


def stars_menu():
    kb = InlineKeyboardBuilder()
    for amount in [50, 100, 250, 500, 1000]:
        kb.button(text=f"{amount} ⭐", callback_data=f"order_{amount}")
    kb.row(InlineKeyboardButton(text="✏️ Выбрать своё количество", callback_data="custom_amount"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    kb.adjust(2)
    return kb.as_markup()


def back_kb(callback_data="back_main"):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data))
    return kb.as_markup()


def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📋 Заказы", callback_data="admin_orders"))
    kb.row(InlineKeyboardButton(text="🎲 Выбрать победителя", callback_data="admin_draw"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    return kb.as_markup()


# ============ FSM ============
class GiveawayForm(StatesGroup):
    title = State()
    stars = State()
    duration = State()
    max_participants = State()


class BuyForm(StatesGroup):
    recipient = State()
    amount = State()


# ============ Старт ============
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    caption = (
        f"👋 Добро пожаловать, <b>{escape(message.from_user.first_name or 'друг')}</b>!\n\n"
        "🌟 Здесь вы можете:\n"
        "• купить звёзды\n"
        "• участвовать в розыгрышах\n"
        "• создать свой розыгрыш\n\n"
        "Выберите действие ниже 👇"
    )
    try:
        await message.answer_photo(
            photo=START_IMAGE_URL,
            caption=caption,
            reply_markup=main_menu(),
            parse_mode=PARSE
        )
    except TelegramBadRequest:
        await message.answer(caption, reply_markup=main_menu(), parse_mode=PARSE)


@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(
        callback.message,
        "🏠 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=main_menu()
    )
    await callback.answer()


# ============ Покупка звёзд ============
@dp.callback_query(F.data == "buy")
async def buy_stars(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "⭐️ <b>Покупка звёзд</b>\n\n"
        "👤 Получатель: <i>не указан</i>\n\n"
        f"— Минимум: <b>{MIN_STARS}</b> звёзд\n"
        f"— Максимум (за один заказ): <b>{MAX_STARS:,}</b> звёзд\n\n"
        "🔎 Выберите количество звёзд для покупки:"
    )
    await safe_edit(callback.message, text, reply_markup=stars_menu())
    await callback.answer()


@dp.callback_query(F.data == "custom_amount")
async def custom_amount_start(callback: types.CallbackQuery, state: FSMContext):
    await safe_edit(
        callback.message,
        "✏️ <b>Своё количество</b>\n\n"
        "Введите <b>@username</b> получателя звёзд\n"
        "Например: <code>@durov</code>",
        reply_markup=back_kb("buy")
    )
    await state.set_state(BuyForm.recipient)
    await callback.answer()


@dp.message(BuyForm.recipient)
async def buy_recipient(message: types.Message, state: FSMContext):
    recipient = (message.text or "").strip()
    if not recipient:
        await message.answer("⚠️ Введите username получателя.", reply_markup=back_kb("buy"), parse_mode=PARSE)
        return
    await state.update_data(recipient=recipient)
    await message.answer(
        f"👤 Получатель: <b>{escape(recipient)}</b>\n\n"
        f"Теперь введите количество звёзд (от <b>{MIN_STARS}</b> до <b>{MAX_STARS}</b>):",
        reply_markup=back_kb("buy"),
        parse_mode=PARSE
    )
    await state.set_state(BuyForm.amount)


@dp.message(BuyForm.amount)
async def buy_amount(message: types.Message, state: FSMContext):
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        await message.answer("⚠️ Введите число.", reply_markup=back_kb("buy"), parse_mode=PARSE)
        return

    if amount < MIN_STARS or amount > MAX_STARS:
        await message.answer(
            f"⚠️ Количество должно быть от {MIN_STARS} до {MAX_STARS}.",
            reply_markup=back_kb("buy"),
            parse_mode=PARSE
        )
        return

    data = await state.get_data()
    recipient = data.get("recipient", "не указан")
    user = message.from_user

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, recipient, stars_amount) VALUES (?, ?, ?, ?)",
            (user.id, user.username or user.first_name or "user", recipient, amount)
        )
        order_id = cursor.lastrowid
        await db.commit()

    await message.answer(
        f"✅ <b>Заказ #{order_id} создан</b>\n\n"
        f"⭐ Количество: <b>{amount}</b> звёзд\n"
        f"👤 Получатель: <b>{escape(recipient)}</b>\n"
        f"💰 К оплате: <b>{escape(PAYMENT_INFO)}</b>\n\n"
        f"📩 После перевода напишите продавцу: @{SELLER_USERNAME}\n"
        f"Укажите номер заказа: <code>#{order_id}</code>\n\n"
        f"После подтверждения оплаты продавец отправит звёзды получателю.",
        reply_markup=back_kb("back_main"),
        parse_mode=PARSE
    )
    await state.clear()


@dp.callback_query(F.data.startswith("order_"))
async def create_order(callback: types.CallbackQuery, state: FSMContext):
    amount = int(callback.data.split("_")[1])
    await state.update_data(amount=amount)
    await safe_edit(
        callback.message,
        f"⭐ Количество: <b>{amount}</b> звёзд\n\n"
        "✏️ Введите <b>@username</b> получателя звёзд\n"
        "Например: <code>@durov</code>",
        reply_markup=back_kb("buy")
    )
    await state.set_state(BuyForm.recipient)
    await callback.answer()


# ============ Розыгрыши (пользователи) ============
@dp.callback_query(F.data == "giveaway_list")
async def list_giveaways(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, title, stars_prize, end_time, max_participants "
            "FROM giveaways WHERE status='active'"
        )
        rows = await cursor.fetchall()

    if not rows:
        await safe_edit(
            callback.message,
            "🎁 <b>Активные розыгрыши</b>\n\n"
            "Пока нет активных розыгрышей.\n"
            "Вы можете создать свой — кнопка «➕ Создать розыгрыш» в меню.",
            reply_markup=back_kb("back_main")
        )
        await callback.answer()
        return

    kb = InlineKeyboardBuilder()
    for gid, title, stars, end_time, max_p in rows:
        kb.button(text=f"{escape(title)} ({stars}⭐)", callback_data=f"join_{gid}")
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    kb.adjust(1)

    await safe_edit(
        callback.message,
        "🎁 <b>Активные розыгрыши</b>\n\nВыберите розыгрыш, чтобы участвовать:",
        reply_markup=kb.as_markup()
    )
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
            (gid, user.id, user.username or user.first_name or "user")
        )
        await db.commit()

    await callback.answer("✅ Вы участвуете! Удачи!", show_alert=True)


# ============ Создание розыгрыша (любой пользователь) ============
@dp.callback_query(F.data == "create_giveaway")
async def create_giveaway_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(
        callback.message,
        "➕ <b>Создание розыгрыша</b>\n\n"
        "Шаг 1/4. Введите <b>название</b> розыгрыша:",
        reply_markup=back_kb("back_main")
    )
    await state.set_state(GiveawayForm.title)
    await callback.answer()


@dp.message(GiveawayForm.title)
async def gw_title(message: types.Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("⚠️ Введите название.", reply_markup=back_kb("back_main"), parse_mode=PARSE)
        return
    await state.update_data(title=title)
    await message.answer(
        "Шаг 2/4. Введите <b>количество звёзд</b> в призе (число):",
        reply_markup=back_kb("back_main"),
        parse_mode=PARSE
    )
    await state.set_state(GiveawayForm.stars)


@dp.message(GiveawayForm.stars)
async def gw_stars(message: types.Message, state: FSMContext):
    try:
        stars = int((message.text or "").strip())
    except ValueError:
        await message.answer("⚠️ Введите число.", reply_markup=back_kb("back_main"), parse_mode=PARSE)
        return
    if stars <= 0:
        await message.answer("⚠️ Число должно быть больше 0.", reply_markup=back_kb("back_main"), parse_mode=PARSE)
        return
    await state.update_data(stars=stars)
    await message.answer(
        "Шаг 3/4. Введите <b>длительность</b> в минутах (например, 60):",
        reply_markup=back_kb("back_main"),
        parse_mode=PARSE
    )
    await state.set_state(GiveawayForm.duration)


@dp.message(GiveawayForm.duration)
async def gw_duration(message: types.Message, state: FSMContext):
    try:
        minutes = int((message.text or "").strip())
    except ValueError:
        await message.answer("⚠️ Введите число.", reply_markup=back_kb("back_main"), parse_mode=PARSE)
        return
    if minutes <= 0:
        await message.answer("⚠️ Число должно быть больше 0.", reply_markup=back_kb("back_main"), parse_mode=PARSE)
        return
    await state.update_data(duration=minutes)
    await message.answer(
        "Шаг 4/4. Введите <b>максимальное количество участников</b>:",
        reply_markup=back_kb("back_main"),
        parse_mode=PARSE
    )
    await state.set_state(GiveawayForm.max_participants)


@dp.message(GiveawayForm.max_participants)
async def gw_max(message: types.Message, state: FSMContext):
    try:
        max_p = int((message.text or "").strip())
    except ValueError:
        await message.answer("⚠️ Введите число.", reply_markup=back_kb("back_main"), parse_mode=PARSE)
        return
    if max_p <= 0:
        await message.answer("⚠️ Число должно быть больше 0.", reply_markup=back_kb("back_main"), parse_mode=PARSE)
        return

    data = await state.get_data()
    end_time = datetime.now() + timedelta(minutes=data["duration"])
    creator_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO giveaways (title, stars_prize, end_time, max_participants, creator_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (data["title"], data["stars"], end_time.isoformat(), max_p, creator_id)
        )
        await db.commit()

    await message.answer(
        f"✅ <b>Розыгрыш создан!</b>\n\n"
        f"📌 Название: <b>{escape(data['title'])}</b>\n"
        f"⭐ Приз: <b>{data['stars']}</b> звёзд\n"
        f"⏰ Окончание: <b>{end_time.strftime('%Y-%m-%d %H:%M')}</b>\n"
        f"👥 Лимит участников: <b>{max_p}</b>\n\n"
        f"Он появился в разделе «🎁 Розыгрыши».",
        reply_markup=back_kb("back_main"),
        parse_mode=PARSE
    )
    await state.clear()


# ============ Админ-панель ============
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🛠 <b>Панель администратора</b>", reply_markup=admin_menu(), parse_mode=PARSE)


@dp.callback_query(F.data == "admin_orders")
async def admin_orders(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, username, recipient, stars_amount, status "
            "FROM orders ORDER BY id DESC LIMIT 20"
        )
        rows = await cursor.fetchall()

    if not rows:
        await safe_edit(callback.message, "📋 Заказов пока нет.", reply_markup=admin_menu())
        await callback.answer()
        return

    lines = ["📋 <b>Последние заказы</b>\n"]
    for oid, uname, recipient, stars, status in rows:
        lines.append(
            f"#{oid} | @{escape(uname or 'user')} → {escape(recipient or '—')} | {stars}⭐ | {status}"
        )

    await safe_edit(callback.message, "\n".join(lines), reply_markup=admin_menu())
    await callback.answer()


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
        await safe_edit(callback.message, "Нет активных розыгрышей.", reply_markup=admin_menu())
        await callback.answer()
        return

    kb = InlineKeyboardBuilder()
    for gid, title, stars in rows:
        kb.button(text=f"{escape(title)} ({stars}⭐)", callback_data=f"draw_{gid}")
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    kb.adjust(1)

    await safe_edit(
        callback.message,
        "🎲 Выберите розыгрыш для определения победителя:",
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

    await safe_edit(
        callback.message,
        f"🎉 <b>Розыгрыш «{escape(title)}» завершён!</b>\n\n"
        f"🏆 Победитель: @{escape(winner_name or 'user')} (ID: <code>{winner_id}</code>)\n"
        f"⭐ Приз: <b>{stars}</b> звёзд\n\n"
        f"Свяжитесь с победителем для вручения приза.",
        reply_markup=admin_menu()
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    await safe_edit(callback.message, "🛠 <b>Панель администратора</b>", reply_markup=admin_menu())
    await callback.answer()


# ============ Запуск ============
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
