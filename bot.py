import asyncio
import logging
import random
from datetime import datetime, timedelta

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============ НАСТРОЙКИ ============
BOT_TOKEN = "9239343763:AAEdUUahoxRPNkuEVoz3NP_GwOa_s1GjeKg"
ADMIN_IDS = [6956175793, 1479120225]
SELLER_USERNAME = "manager_darexvod17"
PAYMENT_INFO = "Перевод на карту: 2202 2000 0000 0000"
START_IMAGE_URL = "https://example.com/start.jpg"  # если пусто/битая — отправится текст
DB_PATH = "shop.db"
# ===================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============ Инициализация БД ============
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
                creator_id INTEGER,
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
    kb.button(text="🎁 Мои розыгрыши", callback_data="my_giveaways")
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
    kb.adjust(1)
    return kb.as_markup()


# ============ Состояния FSM ============
class GiveawayForm(StatesGroup):
    title = State()
    stars = State()
    duration = State()
    max_participants = State()


# ============ Главное меню ============
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        f"Привет, {message.from_user.first_name}!\n\n"
        "Здесь можно:\n"
        "⭐ Купить звёзды Telegram\n"
        "🎁 Создать и смотреть свои розыгрыши\n\n"
        "Выберите действие ниже:"
    )

    # Пытаемся отправить с картинкой, если URL задан
    if START_IMAGE_URL:
        try:
            await message.answer_photo(
                photo=START_IMAGE_URL,
                caption=text,
                reply_markup=main_menu()
            )
            return
        except Exception as e:
            logging.warning(f"Не удалось отправить стартовую картинку: {e}")

    await message.answer(text, reply_markup=main_menu())


@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()


# ============ Покупка звёзд ============
@dp.callback_query(F.data == "buy")
async def buy_stars(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите количество звёзд:", reply_markup=stars_menu())
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
        f"Укажите номер заказа: #{order_id}"
    )
    await callback.message.edit_text(text)
    await callback.answer()


# ============ Мои розыгрыши (только свои) ============
@dp.callback_query(F.data == "my_giveaways")
async def my_giveaways(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, title, stars_prize, end_time, max_participants, status, winner_id "
            "FROM giveaways WHERE creator_id=? ORDER BY id DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        kb = InlineKeyboardBuilder()
        kb.button(text="🎁 Создать розыгрыш", callback_data="create_giveaway")
        kb.button(text="◀️ Назад", callback_data="back_main")
        kb.adjust(1)
        await callback.message.edit_text(
            "У вас ещё нет розыгрышей. Создайте первый!",
            reply_markup=kb.as_markup()
        )
        await callback.answer()
        return

    lines = ["🎁 Ваши розыгрыши:\n"]
    for gid, title, stars, end_time, max_p, status, winner_id in rows:
        end_dt = datetime.fromisoformat(end_time)
        status_text = "✅ завершён" if status == "ended" else "🟢 активен"
        line = (
            f"#{gid} «{title}»\n"
            f"  Приз: {stars}⭐ | Лимит: {max_p}\n"
            f"  До: {end_dt.strftime('%Y-%m-%d %H:%M')} | {status_text}"
        )
        if winner_id:
            line += f"\n  🏆 Победитель ID: {winner_id}"
        lines.append(line)

    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Создать розыгрыш", callback_data="create_giveaway")
    kb.button(text="◀️ Назад", callback_data="back_main")
    kb.adjust(1)

    await callback.message.edit_text("\n\n".join(lines), reply_markup=kb.as_markup())
    await callback.answer()


# ============ Создание розыгрыша ============
@dp.callback_query(F.data == "create_giveaway")
async def create_giveaway_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите название розыгрыша:\n\n"
        "(или отправьте /cancel для отмены)"
    )
    await state.set_state(GiveawayForm.title)
    await callback.answer()


@dp.message(Command("cancel"))
async def cancel_form(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание розыгрыша отменено.", reply_markup=main_menu())


@dp.message(GiveawayForm.title)
async def gw_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Сколько звёзд в призе? (число)")
    await state.set_state(GiveawayForm.stars)


@dp.message(GiveawayForm.stars)
async def gw_stars(message: types.Message, state: FSMContext):
    try:
        stars = int(message.text)
        if stars <= 0:
            raise ValueError
        await state.update_data(stars=stars)
        await message.answer("Длительность в минутах (например, 60):")
        await state.set_state(GiveawayForm.duration)
    except ValueError:
        await message.answer("Введите положительное число.")


@dp.message(GiveawayForm.duration)
async def gw_duration(message: types.Message, state: FSMContext):
    try:
        minutes = int(message.text)
        if minutes <= 0:
            raise ValueError
        await state.update_data(duration=minutes)
        await message.answer("Максимальное количество участников:")
        await state.set_state(GiveawayForm.max_participants)
    except ValueError:
        await message.answer("Введите положительное число.")


@dp.message(GiveawayForm.max_participants)
async def gw_max(message: types.Message, state: FSMContext):
    try:
        max_p = int(message.text)
        if max_p <= 0:
            raise ValueError
        data = await state.get_data()
        end_time = datetime.now() + timedelta(minutes=data['duration'])
        creator_id = message.from_user.id

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO giveaways (creator_id, title, stars_prize, end_time, max_participants) "
                "VALUES (?, ?, ?, ?, ?)",
                (creator_id, data['title'], data['stars'], end_time.isoformat(), max_p)
            )
            gid = cursor.lastrowid
            await db.commit()

        await message.answer(
            f"✅ Розыгрыш #{gid} создан!\n\n"
            f"📌 Название: {data['title']}\n"
            f"⭐ Приз: {data['stars']} звёзд\n"
            f"⏰ Окончание: {end_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"👥 Лимит участников: {max_p}\n\n"
            f"Чтобы пригласить участников — отправьте им команду:\n"
            f"<code>/join {gid}</code>\n\n"
            f"Когда время истечёт или наберётся {max_p} участников — "
            f"я сам выберу победителя и пришлю вам сообщение.",
            parse_mode="HTML"
        )
        await state.clear()
    except ValueError:
        await message.answer("Введите положительное число.")


# ============ Участие в розыгрыше ============
@dp.message(Command("join"))
async def join_cmd(message: types.Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /join <номер> (например /join 5)")
        return
    try:
        gid = int(args[1])
    except ValueError:
        await message.answer("Неверный номер розыгрыша.")
        return
    await _try_join(message, gid)


async def _try_join(message: types.Message, gid: int):
    user = message.from_user

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT creator_id, title, end_time, max_participants, status FROM giveaways WHERE id=?",
            (gid,)
        )
        row = await cursor.fetchone()
        if not row:
            await message.answer("Розыгрыш не найден.")
            return

        creator_id, title, end_time, max_p, status = row

        if status != "active":
            await message.answer("Розыгрыш уже завершён.")
            return

        if datetime.now() > datetime.fromisoformat(end_time):
            await message.answer("Время розыгрыша истекло.")
            return

        if user.id == creator_id:
            await message.answer("Вы создатель этого розыгрыша и не можете в нём участвовать.")
            return

        cursor = await db.execute(
            "SELECT COUNT(*) FROM participants WHERE giveaway_id=?", (gid,)
        )
        count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT 1 FROM participants WHERE giveaway_id=? AND user_id=?", (gid, user.id)
        )
        already = await cursor.fetchone()

    if already:
        await message.answer("Вы уже участвуете в этом розыгрыше.")
        return

    if count >= max_p:
        await message.answer("Лимит участников достигнут.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO participants (giveaway_id, user_id, username) VALUES (?, ?, ?)",
            (gid, user.id, user.username or user.first_name)
        )
        await db.commit()

    await message.answer(f"✅ Вы участвуете в розыгрыше «{title}»! Удачи!")

    if count + 1 >= max_p:
        await finish_giveaway(gid, reason="limit")


# ============ Завершение розыгрыша ============
async def finish_giveaway(gid: int, reason: str = "time"):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT creator_id, title, stars_prize, status FROM giveaways WHERE id=?",
            (gid,)
        )
        row = await cursor.fetchone()
        if not row:
            return
        creator_id, title, stars, status = row

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
                    f"⚠️ Розыгрыш «{title}» (#{gid}) завершён, "
                    f"но участников нет. Победитель не определён."
                )
            except Exception:
                pass
            return

        winner_id, winner_name = random.choice(participants)

        await db.execute(
            "UPDATE giveaways SET status='ended', winner_id=? WHERE id=?",
            (winner_id, gid)
        )
        await db.commit()

    reason_text = "набрался лимит участников" if reason == "limit" else "истекло время"

    try:
        await bot.send_message(
            creator_id,
            f"🏆 Розыгрыш «{title}» (#{gid}) завершён!\n"
            f"Причина: {reason_text}\n\n"
            f"🎉 Победитель: @{winner_name} (ID: {winner_id})\n"
            f"Приз: {stars}⭐\n\n"
            f"Свяжитесь с победителем и вручите приз."
        )
    except Exception as e:
        logging.warning(f"Не удалось уведомить создателя {creator_id}: {e}")

    try:
        await bot.send_message(
            winner_id,
            f"🎉 Поздравляем! Вы выиграли в розыгрыше «{title}»!\n"
            f"Приз: {stars}⭐\n\n"
            f"С вами свяжется создатель розыгрыша."
        )
    except Exception:
        pass


# ============ Фоновая проверка истёкших розыгрышей ============
async def giveaway_watcher():
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT id, end_time FROM giveaways WHERE status='active'"
                )
                rows = await cursor.fetchall()

            now = datetime.now()
            for gid, end_time in rows:
                if now >= datetime.fromisoformat(end_time):
                    await finish_giveaway(gid, reason="time")
        except Exception as e:
            logging.error(f"Ошибка в watcher: {e}")

        await asyncio.sleep(30)


# ============ Админ-панель (заказы) ============
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
            "SELECT id, username, stars_amount, status FROM orders ORDER BY id DESC LIMIT 20"
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

# ============ Fallback: ловит всё, что не поймали другие хэндлеры ============
@dp.message()
async def fallback_message(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current is not None:
        return  # пользователь в процессе создания розыгрыша — не мешаем
    await message.answer(
        "Я не понял это сообщение 🤔\n\n"
        "Используйте кнопки меню или команды:\n"
        "/start — главное меню\n"
        "/join <номер> — участвовать в розыгрыше\n"
        "/admin — панель администратора",
        reply_markup=main_menu()
    )


@dp.callback_query()
async def fallback_callback(callback: types.CallbackQuery):
    await callback.answer("Кнопка устарела. Откройте /start заново.", show_alert=True)

# ============ Запуск ============
async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    await init_db()
    asyncio.create_task(giveaway_watcher())
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
