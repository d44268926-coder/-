import asyncio
import logging
import random
from datetime import datetime

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============ НАСТРОЙКИ ============
BOT_TOKEN = "9239343763:AAH_YcLaPqIl4NZhp6bOJ9FfGK0UlTlgRjk"
ADMIN_IDS = [6956175793, 1479120225]
SELLER_USERNAME = "manager_darexvod17"
PAYMENT_INFO = "Перевод на карту: 2202 2000 0000 0000"
START_IMAGE_URL = "https://images.unsplash.com/photo-1614680376593-902f74cf0d41?w=600"
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
                description TEXT,
                prize TEXT,                -- теперь строковый выигрыш
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

        # Миграция старых БД: добавляем колонку prize, если её нет
        try:
            await db.execute("ALTER TABLE giveaways ADD COLUMN prize TEXT")
            await db.commit()
        except Exception:
            pass
        # Старая колонка stars_prize больше не используется, но не мешает
        try:
            await db.execute("ALTER TABLE giveaways ADD COLUMN description TEXT")
            await db.commit()
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE giveaways ADD COLUMN winners_count INTEGER DEFAULT 1")
            await db.commit()
        except Exception:
            pass


# ============ Клавиатуры ============
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="Создать конкурс 🎲", callback_data="create_giveaway", style="primary")
    kb.button(text="Мои конкурсы 💼", callback_data="my_giveaways", style="primary")
    kb.button(text="Купить звезды ⭐", callback_data="buy", style="primary")
    kb.button(text="Служба поддержки 💬", callback_data="support", style="primary")
    kb.adjust(2)
    return kb.as_markup()


def stars_menu():
    kb = InlineKeyboardBuilder()
    for amount in [50, 100, 250, 500, 1000]:
        kb.button(text=f"💫 {amount} ⭐", callback_data=f"order_{amount}", style="primary")
    kb.button(text="🔙 Назад", callback_data="back_main", style="danger")
    kb.adjust(2)
    return kb.as_markup()


def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Заказы", callback_data="admin_orders", style="primary")
    kb.adjust(1)
    return kb.as_markup()


def my_giveaways_menu(has_rows: bool):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать конкурс", callback_data="create_giveaway", style="primary")
    if has_rows:
        kb.button(text="🔄 Обновить", callback_data="my_giveaways", style="primary")
    kb.button(text="🔙 Назад", callback_data="back_main", style="danger")
    kb.adjust(1)
    return kb.as_markup()


def giveaway_actions_menu(gid: int, is_active: bool):
    kb = InlineKeyboardBuilder()
    if is_active:
        kb.button(text="🔗 Получить ссылку для участников", callback_data=f"share_{gid}", style="primary")
    kb.button(text="🔙 К списку", callback_data="my_giveaways", style="danger")
    kb.adjust(1)
    return kb.as_markup()


# ============ Состояния FSM ============
class GiveawayForm(StatesGroup):
    title = State()
    description = State()
    prize = State()
    winners = State()
    end_datetime = State()


# ============ Главное меню ============
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        f"Привет, {message.from_user.first_name}!\n\n"
        "Здесь можно:\n"
        "⭐ Купить звёзды Telegram\n"
        "🎲 Создать и смотреть свои конкурсы\n\n"
        "Выберите действие ниже:"
    )
    if START_IMAGE_URL:
        try:
            await message.answer_photo(
                photo=START_IMAGE_URL,
                caption=text,
                reply_markup=main_menu()
            )
            return
        except Exception as e:
            logging.warning(f"Не удалось отправить картинку: {e}")
    await message.answer(text, reply_markup=main_menu())


@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()


@dp.callback_query(F.data == "support")
async def support_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"По всем вопросам пишите: @{SELLER_USERNAME}",
        reply_markup=main_menu()
    )
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


# ============ Мои конкурсы ============
@dp.callback_query(F.data == "my_giveaways")
async def my_giveaways(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, title, prize, end_time, status, winner_id "
            "FROM giveaways WHERE creator_id=? ORDER BY id DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.edit_text(
            "У вас ещё нет конкурсов. Создайте первый!",
            reply_markup=my_giveaways_menu(has_rows=False)
        )
        await callback.answer()
        return

    lines = ["💼 Ваши конкурсы:\n"]
    buttons = []
    for gid, title, prize, end_time, status, winner_id in rows:
        end_dt = datetime.fromisoformat(end_time)
        status_text = "✅ завершён" if status == "ended" else "🟢 активен"
        emoji = "🔴" if status == "ended" else "🟢"
        line = (
            f"{emoji} #{gid} «{title}»\n"
            f"  Выигрыш: {prize or '—'}\n"
            f"  До: {end_dt.strftime('%d.%m.%Y %H:%M')} | {status_text}"
        )
        if winner_id:
            line += f"\n  🏆 Победитель ID: {winner_id}"
        lines.append(line)
        buttons.append((gid, title))

    kb = InlineKeyboardBuilder()
    for gid, title in buttons:
        short = title if len(title) <= 20 else title[:20] + "…"
        kb.button(text=f"👁 #{gid} {short}", callback_data=f"view_{gid}", style="primary")
    kb.button(text="➕ Создать конкурс", callback_data="create_giveaway", style="primary")
    kb.button(text="🔙 Назад", callback_data="back_main", style="danger")
    kb.adjust(1)

    await callback.message.edit_text("\n\n".join(lines), reply_markup=kb.as_markup())
    await callback.answer()


@dp.callback_query(F.data.startswith("view_"))
async def view_giveaway(callback: types.CallbackQuery):
    gid = int(callback.data.split("_")[1])

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
            await callback.answer("Это не ваш конкурс.", show_alert=True)
            return

        cursor = await db.execute(
            "SELECT COUNT(*) FROM participants WHERE giveaway_id=?", (gid,)
        )
        count = (await cursor.fetchone())[0]

    end_dt = datetime.fromisoformat(end_time)
    status_text = "✅ завершён" if status == "ended" else "🟢 активен"

    text = f"🎲 Конкурс #{gid} — «{title}»\n\n"
    if description:
        text += f"{description}\n\n"

    text += (
        f"🎁 Выигрыш: {prize or '—'}\n"
        f"🏆 Победителей: {winners}\n"
        f"⏰ Окончание: {end_dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 Статус: {status_text}\n"
        f"👥 Участников: {count}"
    )
    if winner_id:
        text += f"\n🏆 Победитель ID: {winner_id}"
    if status == "active":
        text += f"\n\n🔗 Ссылка для участия: <code>/join {gid}</code>"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=giveaway_actions_menu(gid, is_active=(status == "active"))
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("share_"))
async def share_giveaway(callback: types.CallbackQuery):
    gid = int(callback.data.split("_")[1])
    await callback.message.edit_text(
        f"Отправьте участникам эту команду:\n\n"
        f"<code>/join {gid}</code>\n\n"
        f"Они напишут её боту и автоматически зарегистрируются.",
        parse_mode="HTML",
        reply_markup=giveaway_actions_menu(gid, is_active=True)
    )
    await callback.answer()


# ============ Создание конкурса ============
@dp.callback_query(F.data == "create_giveaway")
async def create_giveaway_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите название конкурса:\n\n"
        "(или отправьте /cancel для отмены)"
    )
    await state.set_state(GiveawayForm.title)
    await callback.answer()


@dp.message(Command("cancel"))
async def cancel_form(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание конкурса отменено.", reply_markup=main_menu())


@dp.message(GiveawayForm.title)
async def gw_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите описание конкурса (или отправьте /skip, чтобы пропустить):")
    await state.set_state(GiveawayForm.description)


@dp.message(GiveawayForm.description)
async def gw_description(message: types.Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(description="")
    else:
        await state.update_data(description=message.text)
    await message.answer("Введите выигрыш (что получит победитель):\n\nНапример: <code>100 звёзд</code>, <code>500 рублей</code>, <code>подписка на месяц</code>", parse_mode="HTML")
    await state.set_state(GiveawayForm.prize)


@dp.message(GiveawayForm.prize)
async def gw_prize(message: types.Message, state: FSMContext):
    prize = message.text.strip()
    if not prize:
        await message.answer("Выигрыш не может быть пустым. Введите снова:")
        return
    await state.update_data(prize=prize)
    await message.answer("Сколько победителей будет в конкурсе? (число)")
    await state.set_state(GiveawayForm.winners)


@dp.message(GiveawayForm.winners)
async def gw_winners(message: types.Message, state: FSMContext):
    try:
        winners = int(message.text)
        if winners <= 0:
            raise ValueError
        await state.update_data(winners=winners)
        await message.answer(
            "Введите дату и время окончания конкурса\n"
            "в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
            "Например: <code>15.11.2026 18:30</code>",
            parse_mode="HTML"
        )
        await state.set_state(GiveawayForm.end_datetime)
    except ValueError:
        await message.answer("Введите положительное число.")


@dp.message(GiveawayForm.end_datetime)
async def gw_end_datetime(message: types.Message, state: FSMContext):
    try:
        end_dt = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer(
            "Неверный формат. Введите дату и время так:\n"
            "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
            "Например: <code>15.11.2026 18:30</code>",
            parse_mode="HTML"
        )
        return

    if end_dt <= datetime.now():
        await message.answer(
            "Дата окончания должна быть в будущем. Введите снова:\n"
            "Например: <code>15.11.2026 18:30</code>",
            parse_mode="HTML"
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
    text = f"🎲 <b>{data['title']}</b>\n\n"
    if desc:
        text += f"{desc}\n\n"

    text += (
        f"🎁 Выигрыш: {data['prize']}\n"
        f"🏆 Победителей: {data['winners']}\n"
        f"⏰ Окончание: {end_dt.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Чтобы участвовать — отправьте:\n"
        f"<code>/join {gid}</code>"
    )

    await message.answer(text, parse_mode="HTML")
    await state.clear()


# ============ Участие в конкурсе ============
@dp.message(Command("join"))
async def join_cmd(message: types.Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /join <номер> (например /join 5)")
        return
    try:
        gid = int(args[1])
    except ValueError:
        await message.answer("Неверный номер конкурса.")
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
            await message.answer("Конкурс не найден.")
            return

        creator_id, title, end_time, status = row

        if status != "active":
            await message.answer("Конкурс уже завершён.")
            return

        if datetime.now() > datetime.fromisoformat(end_time):
            await message.answer("Время конкурса истекло.")
            return

        if user.id == creator_id:
            await message.answer("Вы создатель этого конкурса и не можете в нём участвовать.")
            return

        cursor = await db.execute(
            "SELECT 1 FROM participants WHERE giveaway_id=? AND user_id=?", (gid, user.id)
        )
        already = await cursor.fetchone()

    if already:
        await message.answer("Вы уже участвуете в этом конкурсе.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO participants (giveaway_id, user_id, username) VALUES (?, ?, ?)",
            (gid, user.id, user.username or user.first_name)
        )
        await db.commit()

    await message.answer(f"✅ Вы участвуете в конкурсе «{title}»! Удачи!")


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
            f"🏆 Конкурс «{title}» (#{gid}) завершён!\n"
            f"Причина: истекло время\n\n"
            f"🎉 Победители ({len(winners)}):\n"
            f"{winners_list}\n\n"
            f"🎁 Выигрыш: {prize}\n\n"
            f"Свяжитесь с победителями и вручите приз."
        )
    except Exception as e:
        logging.warning(f"Не удалось уведомить создателя {creator_id}: {e}")

    for w_id, w_name in winners:
        try:
            await bot.send_message(
                w_id,
                f"🎉 Поздравляем! Вы выиграли в конкурсе «{title}»!\n"
                f"🎁 Выигрыш: {prize}\n\n"
                f"С вами свяжется создатель конкурса."
            )
        except Exception:
            pass


# ============ Фоновая проверка истёкших конкурсов ============
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
                    await finish_giveaway(gid)
        except Exception as e:
            logging.error(f"Ошибка в watcher: {e}")

        await asyncio.sleep(30)


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


# ============ Fallback ============
@dp.message()
async def fallback_message(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current is not None:
        return
    await message.answer(
        "Я не понял это сообщение 🤔\n\n"
        "Используйте кнопки меню или команды:\n"
        "/start — главное меню\n"
        "/join <номер> — участвовать в конкурсе\n"
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
