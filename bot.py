import asyncio
import logging
import random
from datetime import datetime

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============ НАСТРОЙКИ ============
BOT_TOKEN = "9239343763:AAH_YcLaPqIl4NZhp6bOJ9FfGK0UlTlgRjk"
ADMIN_IDS = [6956175793, 1479120225]
SELLER_USERNAME = "manager_darexvod17"
PAYMENT_INFO = "2202 2000 0000 0000"
START_IMAGE_URL = "https://images.unsplash.com/photo-1614680376593-902f74cf0d41?w=600"

STAR_PRICE_RUB = 1.61
MIN_STARS = 50
DB_PATH = "shop.db"
BOT_USERNAME = "DAREXVOD17_robot_bot"
# ===================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

last_bot_message = {}


# ============ Инициализация БД ============
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                stars_amount INTEGER,
                recipient TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER,
                title TEXT,
                description TEXT,
                prize TEXT,
                winners_count INTEGER DEFAULT 1,
                end_time TIMESTAMP,
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

        for ddl in [
            "ALTER TABLE orders ADD COLUMN recipient TEXT",
            "ALTER TABLE giveaways ADD COLUMN description TEXT",
            "ALTER TABLE giveaways ADD COLUMN winners_count INTEGER DEFAULT 1",
            "ALTER TABLE giveaways ADD COLUMN prize TEXT",
        ]:
            try:
                await db.execute(ddl)
                await db.commit()
            except Exception:
                pass


# ============ Вспомогательные функции ============
async def send_and_delete(chat_id: int, text: str = None, reply_markup=None, parse_mode="HTML", photo=None):
    if chat_id in last_bot_message:
        try:
            await bot.delete_message(chat_id, last_bot_message[chat_id])
        except Exception:
            pass

    if photo:
        try:
            msg = await bot.send_photo(
                chat_id=chat_id, photo=photo, caption=text,
                reply_markup=reply_markup, parse_mode=parse_mode
            )
        except Exception:
            msg = await bot.send_message(
                chat_id=chat_id, text=text,
                reply_markup=reply_markup, parse_mode=parse_mode
            )
    else:
        msg = await bot.send_message(
            chat_id=chat_id, text=text,
            reply_markup=reply_markup, parse_mode=parse_mode
        )

    last_bot_message[chat_id] = msg.message_id
    return msg


def progress_bar(count: int, target: int = 50) -> str:
    filled = min(int(count / target * 10), 10)
    return "█" * filled + "░" * (10 - filled)


def make_separator() -> str:
    return "━━━━━━━━━━━━━━━━━━━━"


# ============ Клавиатуры ============
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎲 Создать конкурс", callback_data="create_giveaway", style="primary")
    kb.button(text="💼 Мои конкурсы", callback_data="my_giveaways", style="primary")
    kb.button(text="⭐ Купить звёзды", callback_data="buy", style="success")
    kb.button(text="💬 Поддержка", callback_data="support", style="primary")
    kb.adjust(2, 2)
    return kb.as_markup()


def stars_menu():
    kb = InlineKeyboardBuilder()
    for amount in [50, 100, 250, 500, 1000]:
        price = amount * STAR_PRICE_RUB
        kb.button(
            text=f"💫 {amount} ⭐ — {price:.0f} ₽",
            callback_data=f"order_{amount}",
            style="success"
        )
    kb.button(text="✍️ Своё количество", callback_data="custom_amount", style="primary")
    kb.button(text="🔙 Назад", callback_data="back_main", style="danger")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def recipient_menu(amount: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Себе", callback_data=f"rec_self_{amount}", style="success")
    kb.button(text="👥 Другому", callback_data=f"rec_other_{amount}", style="primary")
    kb.button(text="🔙 Назад", callback_data="buy", style="danger")
    kb.adjust(2, 1)
    return kb.as_markup()


def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Заказы", callback_data="admin_orders", style="primary")
    kb.adjust(1)
    return kb.as_markup()


def my_giveaways_menu(has_rows: bool):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать конкурс", callback_data="create_giveaway", style="success")
    if has_rows:
        kb.button(text="🔄 Обновить", callback_data="my_giveaways", style="primary")
    kb.button(text="🔙 Назад", callback_data="back_main", style="danger")
    kb.adjust(1)
    return kb.as_markup()


def giveaway_actions_menu(gid: int, is_active: bool):
    kb = InlineKeyboardBuilder()
    if is_active:
        kb.button(text="🔗 Ссылка для участников", callback_data=f"share_{gid}", style="primary")
        kb.button(
            text="📤 Поделиться",
            url=f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start=join_{gid}"
                f"&text=🎲 Участвуй в конкурсе!"
        )
    kb.button(text="🔙 К списку", callback_data="my_giveaways", style="danger")
    kb.adjust(2, 1) if is_active else kb.adjust(1)
    return kb.as_markup()


# ============ Состояния FSM ============
class OrderForm(StatesGroup):
    custom_amount = State()
    recipient_username = State()


class GiveawayForm(StatesGroup):
    title = State()
    description = State()
    prize = State()
    winners = State()
    end_datetime = State()


# ============ Главное меню ============
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    text = (
        f"<b>👋 Привет, {message.from_user.first_name}!</b>\n\n"
        f"<blockquote>Здесь ты можешь:\n"
        f"⭐ Купить звёзды Telegram\n"
        f"🎲 Создать свой конкурс\n"
        f"💼 Управлять своими конкурсами</blockquote>\n\n"
        f"<b>Выбери действие ниже:</b>"
    )
    await send_and_delete(
        chat_id=message.chat.id,
        text=text,
        reply_markup=main_menu(),
        photo=START_IMAGE_URL
    )


@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.TYPING)
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text="<b>🏠 Главное меню</b>\n\nВыбери действие:",
        reply_markup=main_menu()
    )
    await callback.answer()


@dp.callback_query(F.data == "support")
async def support_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        f"<b>💬 Служба поддержки</b>\n\n"
        f"По всем вопросам пиши: @{SELLER_USERNAME}\n\n"
        f"<i>Отвечаем в течение 30 минут в рабочее время.</i>"
    )
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=text,
        reply_markup=main_menu()
    )
    await callback.answer()


# ============ Покупка звёзд ============
@dp.callback_query(F.data == "buy")
async def buy_stars(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.TYPING)
    text = (
        f"<b>⭐ Покупка звёзд</b>\n\n"
        f"<blockquote>Цена: <b>1 звезда = {STAR_PRICE_RUB} ₽</b>\n"
        f"Минимум: <b>{MIN_STARS} звёзд</b></blockquote>\n\n"
        f"Выбери количество:"
    )
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=text,
        reply_markup=stars_menu()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("order_"))
async def choose_recipient(callback: types.CallbackQuery):
    amount = int(callback.data.split("_")[1])
    price = amount * STAR_PRICE_RUB
    text = (
        f"<b>⭐ Ты выбрал {amount} звёзд</b>\n\n"
        f"<blockquote>💵 Сумма к оплате: <b>{price:.2f} ₽</b></blockquote>\n\n"
        f"<b>Кому отправить подарок?</b>"
    )
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=text,
        reply_markup=recipient_menu(amount)
    )
    await callback.answer()


@dp.callback_query(F.data == "custom_amount")
async def custom_amount_start(callback: types.CallbackQuery, state: FSMContext):
    text = (
        f"<b>✍️ Своё количество</b>\n\n"
        f"<blockquote>Введи количество звёзд (целое число):\n"
        f"Минимум: <b>{MIN_STARS}</b> ⭐</blockquote>"
    )
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=text,
    )
    await state.set_state(OrderForm.custom_amount)
    await callback.answer()


@dp.message(OrderForm.custom_amount)
async def custom_amount_process(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
    except ValueError:
        await send_and_delete(
            chat_id=message.chat.id,
            text="<b>❌ Ошибка</b>\n\nПожалуйста, введи <b>целое число</b>."
        )
        return

    if amount < MIN_STARS:
        await send_and_delete(
            chat_id=message.chat.id,
            text=f"<b>❌ Ошибка</b>\n\nМинимальное количество звёзд — <b>{MIN_STARS}</b>. Введи снова:"
        )
        return

    await state.clear()
    price = amount * STAR_PRICE_RUB
    text = (
        f"<b>⭐ Ты выбрал {amount} звёзд</b>\n\n"
        f"<blockquote>💵 Сумма к оплате: <b>{price:.2f} ₽</b></blockquote>\n\n"
        f"<b>Кому отправить подарок?</b>"
    )
    await send_and_delete(
        chat_id=message.chat.id,
        text=text,
        reply_markup=recipient_menu(amount)
    )


@dp.callback_query(F.data.startswith("rec_self_"))
async def rec_self(callback: types.CallbackQuery):
    amount = int(callback.data.split("_")[2])
    user = callback.from_user
    price = amount * STAR_PRICE_RUB

    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.TYPING)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, stars_amount, recipient) VALUES (?, ?, ?, ?)",
            (user.id, user.username or user.first_name, amount, "Себе")
        )
        order_id = cursor.lastrowid
        await db.commit()

    text = (
        f"<b>✅ Заказ #{order_id} создан</b>\n\n"
        f"<blockquote>"
        f"⭐ Количество: <b>{amount} звёзд</b>\n"
        f"💵 Сумма: <b>{price:.2f} ₽</b>\n"
        f"🎁 Получатель: <b>Себе (@{user.username or user.first_name})</b>"
        f"</blockquote>\n\n"
        f"<b>💳 Реквизиты для оплаты:</b>\n"
        f"<code>{PAYMENT_INFO}</code>\n\n"
        f"<b>📌 После оплаты:</b>\n"
        f"Напиши продавцу: @{SELLER_USERNAME}\n"
        f"Твой номер заказа: <code>#{order_id}</code>"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Написать продавцу", url=f"https://t.me/{SELLER_USERNAME}")
    kb.button(text="🏠 В главное меню", callback_data="back_main", style="danger")
    kb.adjust(1)
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=text,
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("rec_other_"))
async def rec_other(callback: types.CallbackQuery, state: FSMContext):
    amount = int(callback.data.split("_")[2])
    await state.update_data(order_amount=amount)
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=(
            f"<b>👥 Получатель подарка</b>\n\n"
            f"Введи <b>@username</b> или <b>ID</b> получателя:\n\n"
            f"<blockquote><i>Например: @durov или 123456789</i></blockquote>"
        )
    )
    await state.set_state(OrderForm.recipient_username)
    await callback.answer()


@dp.message(OrderForm.recipient_username)
async def process_recipient(message: types.Message, state: FSMContext):
    recipient = message.text.strip()
    data = await state.get_data()
    amount = data.get("order_amount")
    user = message.from_user
    price = amount * STAR_PRICE_RUB

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, stars_amount, recipient) VALUES (?, ?, ?, ?)",
            (user.id, user.username or user.first_name, amount, recipient)
        )
        order_id = cursor.lastrowid
        await db.commit()

    text = (
        f"<b>✅ Заказ #{order_id} создан</b>\n\n"
        f"<blockquote>"
        f"⭐ Количество: <b>{amount} звёзд</b>\n"
        f"💵 Сумма: <b>{price:.2f} ₽</b>\n"
        f"🎁 Получатель: <b>{recipient}</b>"
        f"</blockquote>\n\n"
        f"<b>💳 Реквизиты для оплаты:</b>\n"
        f"<code>{PAYMENT_INFO}</code>\n\n"
        f"<b>📌 После оплаты:</b>\n"
        f"Напиши продавцу: @{SELLER_USERNAME}\n"
        f"Твой номер заказа: <code>#{order_id}</code>"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Написать продавцу", url=f"https://t.me/{SELLER_USERNAME}")
    kb.button(text="🏠 В главное меню", callback_data="back_main", style="danger")
    kb.adjust(1)
    await send_and_delete(
        chat_id=message.chat.id,
        text=text,
        reply_markup=kb.as_markup()
    )
    await state.clear()


# ============ Мои конкурсы ============
@dp.callback_query(F.data == "my_giveaways")
async def my_giveaways(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.TYPING)
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, title, prize, end_time, status, winner_id "
            "FROM giveaways WHERE creator_id=? ORDER BY id DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await send_and_delete(
            chat_id=callback.message.chat.id,
            text="<b>💼 Мои конкурсы</b>\n\n<i>У тебя ещё нет конкурсов. Создай первый!</i>",
            reply_markup=my_giveaways_menu(has_rows=False)
        )
        await callback.answer()
        return

    lines = [f"<b>💼 Твои конкурсы:</b>\n"]
    buttons = []
    for gid, title, prize, end_time, status, winner_id in rows:
        end_dt = datetime.fromisoformat(end_time)
        status_text = "✅ завершён" if status == "ended" else "🟢 активен"
        emoji = "🔴" if status == "ended" else "🟢"
        line = (
            f"{emoji} <b>#{gid}</b> «{title}»\n"
            f"  🎁 {prize or '—'}\n"
            f"  ⏰ До: {end_dt.strftime('%d.%m.%Y %H:%M')} | {status_text}"
        )
        if winner_id:
            line += f"\n  🏆 Победитель ID: {winner_id}"
        lines.append(line)
        buttons.append((gid, title))

    kb = InlineKeyboardBuilder()
    for gid, title in buttons:
        short = title if len(title) <= 20 else title[:20] + "…"
        kb.button(text=f"👁 #{gid} {short}", callback_data=f"view_{gid}", style="primary")
    kb.button(text="➕ Создать конкурс", callback_data="create_giveaway", style="success")
    kb.button(text="🔙 Назад", callback_data="back_main", style="danger")
    kb.adjust(1)

    await send_and_delete(
        chat_id=callback.message.chat.id,
        text="\n\n".join(lines),
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("view_"))
async def view_giveaway(callback: types.CallbackQuery):
    gid = int(callback.data.split("_")[1])
    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.TYPING)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT creator_id, title, description, prize, winners_count, "
            "end_time, status, winner_id FROM giveaways WHERE id=?",
            (gid,)
        )
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Конкурс не найден.", show_alert=True)
            return
        (creator_id, title, description, prize, winners,
         end_time, status, winner_id) = row

        if creator_id != callback.from_user.id:
            await callback.answer("Это не твой конкурс.", show_alert=True)
            return

        cursor = await db.execute(
            "SELECT COUNT(*) FROM participants WHERE giveaway_id=?", (gid,)
        )
        count = (await cursor.fetchone())[0]

    end_dt = datetime.fromisoformat(end_time)
    status_text = "✅ завершён" if status == "ended" else "🟢 активен"

    text = f"<b>🎲 Конкурс #{gid}</b>\n\n"
    if description:
        text += f"<i>{description}</i>\n\n"

    text += (
        f"{make_separator()}\n"
        f"🎁 <b>Выигрыш:</b> {prize or '—'}\n"
        f"🏆 <b>Победителей:</b> {winners}\n"
        f"⏰ <b>Окончание:</b> {end_dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 <b>Статус:</b> {status_text}\n"
        f"👥 <b>Участников:</b> {count}  {progress_bar(count)}\n"
        f"{make_separator()}"
    )

    if winner_id:
        text += f"\n🏆 Победитель ID: {winner_id}"
    if status == "active":
        text += f"\n\n<b>🔗 Ссылка для участия:</b>\n<code>/join {gid}</code>"

    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=text,
        reply_markup=giveaway_actions_menu(gid, is_active=(status == "active"))
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("share_"))
async def share_giveaway(callback: types.CallbackQuery):
    gid = int(callback.data.split("_")[1])
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=(
            f"<b>🔗 Ссылка для участников</b>\n\n"
            f"Отправь участникам эту команду:\n"
            f"<code>/join {gid}</code>\n\n"
            f"<i>Они напишут её боту и автоматически зарегистрируются.</i>"
        ),
        reply_markup=giveaway_actions_menu(gid, is_active=True)
    )
    await callback.answer()


# ============ Создание конкурса ============
@dp.callback_query(F.data == "create_giveaway")
async def create_giveaway_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await send_and_delete(
        chat_id=callback.message.chat.id,
        text=(
            f"<b>🎲 Создание конкурса</b> (1/5)\n\n"
            f"Введи <b>название</b> конкурса:\n\n"
            f"<blockquote><i>Отправь /cancel для отмены</i></blockquote>"
        )
    )
    await state.set_state(GiveawayForm.title)
    await callback.answer()


@dp.message(Command("cancel"))
async def cancel_form(message: types.Message, state: FSMContext):
    await state.clear()
    await send_and_delete(
        chat_id=message.chat.id,
        text="<b>❌ Создание конкурса отменено</b>",
        reply_markup=main_menu()
    )


@dp.message(GiveawayForm.title)
async def gw_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await send_and_delete(
        chat_id=message.chat.id,
        text=(
            f"<b>🎲 Создание конкурса</b> (2/5)\n\n"
            f"Введи <b>описание</b> конкурса:\n\n"
            f"<blockquote><i>Или отправь /skip, чтобы пропустить</i></blockquote>"
        )
    )
    await state.set_state(GiveawayForm.description)


@dp.message(GiveawayForm.description)
async def gw_description(message: types.Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(description="")
    else:
        await state.update_data(description=message.text)
    await send_and_delete(
        chat_id=message.chat.id,
        text=(
            f"<b>🎲 Создание конкурса</b> (3/5)\n\n"
            f"Введи <b>выигрыш</b> (что получит победитель):\n\n"
            f"<blockquote><i>Например: <code>100 звёзд</code>, <code>500 рублей</code>, <code>подписка</code></i></blockquote>"
        )
    )
    await state.set_state(GiveawayForm.prize)


@dp.message(GiveawayForm.prize)
async def gw_prize(message: types.Message, state: FSMContext):
    prize = message.text.strip()
    if not prize:
        await send_and_delete(
            chat_id=message.chat.id,
            text="<b>❌ Ошибка</b>\n\nВыигрыш не может быть пустым. Введи снова:"
        )
        return
    await state.update_data(prize=prize)
    await send_and_delete(
        chat_id=message.chat.id,
        text=(
            f"<b>🎲 Создание конкурса</b> (4/5)\n\n"
            f"Введи <b>количество победителей</b> (целое число):"
        )
    )
    await state.set_state(GiveawayForm.winners)


@dp.message(GiveawayForm.winners)
async def gw_winners(message: types.Message, state: FSMContext):
    try:
        winners = int(message.text)
        if winners <= 0:
            raise ValueError
        await state.update_data(winners=winners)
        await send_and_delete(
            chat_id=message.chat.id,
            text=(
                f"<b>🎲 Создание конкурса</b> (5/5)\n\n"
                f"Введи <b>дату и время окончания</b>:\n\n"
                f"<blockquote>Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
                f"Например: <code>15.11.2026 18:30</code></blockquote>"
            )
        )
        await state.set_state(GiveawayForm.end_datetime)
    except ValueError:
        await send_and_delete(
            chat_id=message.chat.id,
            text="<b>❌ Ошибка</b>\n\nВведи <b>положительное число</b>."
        )


@dp.message(GiveawayForm.end_datetime)
async def gw_end_datetime(message: types.Message, state: FSMContext):
    try:
        end_dt = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        await send_and_delete(
            chat_id=message.chat.id,
            text=(
                f"<b>❌ Ошибка</b>\n\nНеверный формат. Введи так:\n"
                f"<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
                f"Например: <code>15.11.2026 18:30</code>"
            )
        )
        return

    if end_dt <= datetime.now():
        await send_and_delete(
            chat_id=message.chat.id,
            text=(
                f"<b>❌ Ошибка</b>\n\nДата окончания должна быть в будущем. Введи снова:\n"
                f"<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>"
            )
        )
        return

    data = await state.get_data()
    creator_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO giveaways (creator_id, title, description, prize, "
            "winners_count, end_time) VALUES (?, ?, ?, ?, ?, ?)",
            (creator_id, data['title'], data.get('description', ''),
             data['prize'], data['winners'], end_dt.isoformat())
        )
        gid = cursor.lastrowid
        await db.commit()

    desc = data.get('description', '')
    text = f"<b>🎲 КОНКУРС «{data['title']}»</b>\n\n"
    if desc:
        text += f"<i>{desc}</i>\n\n"

    text += (
        f"{make_separator()}\n"
        f"🎁 <b>Выигрыш:</b> {data['prize']}\n"
        f"🏆 <b>Победителей:</b> {data['winners']}\n"
        f"⏰ <b>Окончание:</b> {end_dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"{make_separator()}\n\n"
        f"<b>Как участвовать?</b>\n"
        f"Отправь боту команду <code>/join {gid}</code>"
    )

    await send_and_delete(
        chat_id=message.chat.id,
        text=text
    )
    await state.clear()


# ============ Участие в конкурсе ============
@dp.message(Command("join"))
async def join_cmd(message: types.Message):
    args = message.text.split()
    if len(args) != 2:
        await send_and_delete(
            chat_id=message.chat.id,
            text="<b>Использование:</b> <code>/join <номер></code>\n\nНапример: <code>/join 5</code>"
        )
        return
    try:
        gid = int(args[1])
    except ValueError:
        await send_and_delete(
            chat_id=message.chat.id,
            text="<b>❌ Неверный номер конкурса.</b>"
        )
        return
    await _try_join(message, gid)


async def _try_join(message: types.Message, gid: int):
    user = message.from_user

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT creator_id, title, end_time, status FROM giveaways WHERE id=?",
            (gid,)
        )
        row = await cursor.fetchone()
        if not row:
            await send_and_delete(
                chat_id=message.chat.id,
                text="<b>❌ Конкурс не найден.</b>"
            )
            return

        creator_id, title, end_time, status = row

        if status != "active":
            await send_and_delete(
                chat_id=message.chat.id,
                text="<b>❌ Конкурс уже завершён.</b>"
            )
            return

        if datetime.now() > datetime.fromisoformat(end_time):
            await send_and_delete(
                chat_id=message.chat.id,
                text="<b>❌ Время конкурса истекло.</b>"
            )
            return

        if user.id == creator_id:
            await send_and_delete(
                chat_id=message.chat.id,
                text="<b>❌ Ты создатель этого конкурса</b>\n\n<i>Ты не можешь в нём участвовать.</i>"
            )
            return

        cursor = await db.execute(
            "SELECT 1 FROM participants WHERE giveaway_id=? AND user_id=?", (gid, user.id)
        )
        already = await cursor.fetchone()

    if already:
        await send_and_delete(
            chat_id=message.chat.id,
            text="<b>❌ Ты уже участвуешь в этом конкурсе.</b>"
        )
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO participants (giveaway_id, user_id, username) VALUES (?, ?, ?)",
            (gid, user.id, user.username or user.first_name)
        )
        await db.commit()

    await send_and_delete(
        chat_id=message.chat.id,
        text=f"<b>✅ Ты участвуешь в конкурсе «{title}»!</b>\n\n<i>Удачи!</i>"
    )


# ============ Завершение конкурса ============
async def finish_giveaway(gid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT creator_id, title, prize, winners_count, status "
            "FROM giveaways WHERE id=?",
            (gid,)
        )
        row = await cursor.fetchone()
        if not row:
            return
        creator_id, title, prize, winners_count, status = row

        if status != "active":
            return

        cursor = await db.execute(
            "SELECT user_id, username FROM participants WHERE giveaway_id=?", (gid,)
        )
        participants = await cursor.fetchall()

        if not participants:
            await db.execute("UPDATE giveaways SET status='ended' WHERE id=?", (gid,))
            await db.commit()
            try:
                await bot.send_message(
                    creator_id,
                    f"⚠️ Конкурс «{title}» (#{gid}) завершён, "
                    f"но участников нет. Победитель не определён."
                )
            except Exception:
                pass
            return

        winners_count = min(winners_count, len(participants))
        winners = random.sample(participants, winners_count)

        first_winner_id = winners[0][0]
        await db.execute(
            "UPDATE giveaways SET status='ended', winner_id=? WHERE id=?",
            (first_winner_id, gid)
        )
        await db.commit()

    winners_list = "\n".join([f"• @{w[1]} (ID: {w[0]})" for w in winners])

    try:
        await bot.send_message(
            creator_id,
            f"<b>🏆 Конкурс
