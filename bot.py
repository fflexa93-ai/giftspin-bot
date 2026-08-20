"""
GiftSpin Bot — бот с заданиями и кейсами.
Валюта: Бонусы.
Пользователь выполняет задания (подписка на канал), получает бонусы,
крутит кейс за бонусы и может выиграть приз.
Призы выдаются администратором вручную (бот только записывает выигрыши).

АДМИН-КОМАНДЫ (доступны только тебе, ADMIN_ID):
  /admin                          — показать список всех команд
  /give <user_id> <сумма>         — выдать бонусы пользователю
  /take <user_id> <сумма>         — забрать бонусы у пользователя
  /userinfo <user_id>             — посмотреть баланс и выигрыши пользователя
  /addtask <канал> <награда> <текст>  — добавить задание (подписка на канал)
  /deltask <номер>                — удалить задание по номеру (см. /listtasks)
  /listtasks                      — показать все задания
  /addprize <название> <шанс> [бонусы]  — добавить приз в кейс
                                        (если указать [бонусы] — приз будет начислять бонусы,
                                         если нет — это будет предмет/NFT, который ты выдашь вручную)
  /delprize <номер>               — удалить приз по номеру (см. /listprizes)
  /listprizes                     — показать все призы
  /setspincost <сумма>            — изменить стоимость одного прокрута
  /stats                          — общая статистика бота
"""

import json
import logging
import random
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ==================== НАСТРОЙКИ (меняй под себя) ====================

BOT_TOKEN = "8695779141:AAHWJY8ecgVsUXSqZ-EaDdHjnbCbjs9013Y"

# ID администратора — ТОЛЬКО этот человек сможет пользоваться админ-командами.
# Узнать свой ID можно у бота @userinfobot (напиши ему /start)
ADMIN_ID = 8377955327  # твой Telegram ID — админ-команды доступны только тебе

CURRENCY = "Бонусы"  # название валюты, используется в текстах

USERS_FILE = "users.json"
CONFIG_FILE = "config.json"

# Значения по умолчанию, если config.json ещё не создан.
# После первого запуска всё хранится в config.json и меняется командами админа.
DEFAULT_CONFIG = {
    "spin_cost": 100,
    "tasks": [
        {"channel": "your_channel_username", "reward": 50, "title": "Подпишись на наш канал"},
    ],
    "prizes": [
        {"name": "Пусто (не повезло)", "weight": 50},
        {"name": "10 Бонусов", "weight": 25, "coins": 10},
        {"name": "NFT подарок: Мишка", "weight": 10},
        {"name": "NFT подарок: Роза", "weight": 8},
        {"name": "NFT подарок: Торт", "weight": 5},
        {"name": "Редкий NFT подарок", "weight": 2},
    ],
}

# ======================================================================

logging.basicConfig(level=logging.INFO)


# -------------------- Хранилище данных --------------------

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_users():
    return load_json(USERS_FILE, {})


def save_users(data):
    save_json(USERS_FILE, data)


def load_config():
    return load_json(CONFIG_FILE, DEFAULT_CONFIG)


def save_config(cfg):
    save_json(CONFIG_FILE, cfg)


def get_user(users, user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"balance": 0, "completed_tasks": [], "wins": []}
    return users[uid]


def is_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID


# -------------------- Пользовательские команды --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user = get_user(users, update.effective_user.id)
    save_users(users)

    keyboard = [
        [InlineKeyboardButton("📋 Задания", callback_data="tasks")],
        [InlineKeyboardButton("🎰 Крутить кейс", callback_data="spin")],
        [InlineKeyboardButton(f"💰 Баланс", callback_data="balance")],
    ]
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 🎁\n\n"
        f"Добро пожаловать в GiftSpin!\n"
        f"Выполняй задания, получай {CURRENCY} и крути кейс с призами.\n\n"
        f"Твой баланс: {user['balance']} {CURRENCY}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    users = load_users()
    cfg = load_config()
    user = get_user(users, query.from_user.id)

    text = "📋 Доступные задания:\n\n"
    keyboard = []
    if not cfg["tasks"]:
        text += "Пока заданий нет, загляни позже!"
    for i, task in enumerate(cfg["tasks"]):
        done = task["channel"] in user["completed_tasks"]
        status = "✅" if done else f"+{task['reward']} {CURRENCY}"
        text += f"{'✅' if done else '⬜'} {task['title']} — {status}\n"
        if not done:
            keyboard.append(
                [InlineKeyboardButton(f"Проверить: {task['title']}", callback_data=f"check_{i}")]
            )
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def check_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    task_index = int(query.data.split("_")[1])
    cfg = load_config()

    if task_index >= len(cfg["tasks"]):
        await query.answer("Это задание больше не существует.", show_alert=True)
        return

    task = cfg["tasks"][task_index]
    user_id = query.from_user.id

    try:
        member = await context.bot.get_chat_member(f"@{task['channel']}", user_id)
        is_subscribed = member.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        await query.answer("Не могу проверить подписку. Убедись, что бот — админ канала.", show_alert=True)
        return

    users = load_users()
    user = get_user(users, user_id)

    if not is_subscribed:
        await query.answer("Ты ещё не подписан(а) на канал!", show_alert=True)
        return

    if task["channel"] in user["completed_tasks"]:
        await query.answer("Задание уже засчитано ✅", show_alert=True)
        return

    user["completed_tasks"].append(task["channel"])
    user["balance"] += task["reward"]
    save_users(users)

    await query.answer(f"✅ Задание выполнено! +{task['reward']} {CURRENCY}", show_alert=True)
    await show_tasks(update, context)


async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    users = load_users()
    user = get_user(users, query.from_user.id)

    text = f"💰 Твой баланс: {user['balance']} {CURRENCY}\n"
    if user["wins"]:
        text += "\n🏆 Твои выигрыши:\n" + "\n".join(f"— {w}" for w in user["wins"])

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def spin_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    users = load_users()
    cfg = load_config()
    user = get_user(users, query.from_user.id)
    spin_cost = cfg["spin_cost"]

    if not cfg["prizes"]:
        await query.answer("Призы ещё не настроены, загляни позже!", show_alert=True)
        return

    if user["balance"] < spin_cost:
        await query.answer(
            f"Недостаточно {CURRENCY}! Нужно {spin_cost}, у тебя {user['balance']}.", show_alert=True
        )
        return

    user["balance"] -= spin_cost

    prize = random.choices(cfg["prizes"], weights=[p["weight"] for p in cfg["prizes"]], k=1)[0]

    result_text = f"🎰 Ты крутишь кейс...\n\n🎁 Выпало: **{prize['name']}**"

    if "coins" in prize:
        user["balance"] += prize["coins"]
    elif prize["name"] != "Пусто (не повезло)":
        user["wins"].append(prize["name"])
        if ADMIN_ID:
            try:
                username = query.from_user.username or "нет юзернейма"
                await context.bot.send_message(
                    ADMIN_ID,
                    f"🏆 Новый выигрыш!\n"
                    f"Пользователь: {query.from_user.first_name} (@{username}, id={query.from_user.id})\n"
                    f"Приз: {prize['name']}\n"
                    f"Не забудь выдать вручную!",
                )
            except Exception as e:
                logging.error(f"Не смог уведомить админа: {e}")

    save_users(users)

    keyboard = [
        [InlineKeyboardButton("🎰 Крутить ещё", callback_data="spin")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu")],
    ]
    await query.edit_message_text(
        result_text + f"\n\nБаланс: {user['balance']} {CURRENCY}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    users = load_users()
    user = get_user(users, query.from_user.id)

    keyboard = [
        [InlineKeyboardButton("📋 Задания", callback_data="tasks")],
        [InlineKeyboardButton("🎰 Крутить кейс", callback_data="spin")],
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
    ]
    await query.edit_message_text(
        f"🎁 GiftSpin — главное меню\n\nТвой баланс: {user['balance']} {CURRENCY}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "tasks":
        await show_tasks(update, context)
    elif query.data == "balance":
        await show_balance(update, context)
    elif query.data == "spin":
        await spin_case(update, context)
    elif query.data == "menu":
        await back_to_menu(update, context)
    elif query.data.startswith("check_"):
        await check_task(update, context)


# -------------------- Админ-команды --------------------

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🛠 Админ-панель GiftSpin\n\n"
        "Управление балансом:\n"
        "/give <user_id> <сумма> — выдать бонусы\n"
        "/take <user_id> <сумма> — забрать бонусы\n"
        "/userinfo <user_id> — инфо о пользователе\n\n"
        "Задания:\n"
        "/addtask <канал> <награда> <текст> — добавить\n"
        "/deltask <номер> — удалить\n"
        "/listtasks — список заданий\n\n"
        "Призы:\n"
        "/addprize <название> <шанс> [бонусы] — добавить приз\n"
        "/delprize <номер> — удалить приз\n"
        "/listprizes — список призов\n"
        "/setspincost <сумма> — стоимость прокрута\n\n"
        "/stats — статистика бота"
    )


async def cmd_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        target_id, amount = context.args[0], int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /give <user_id> <сумма>")
        return

    users = load_users()
    user = get_user(users, target_id)
    user["balance"] += amount
    save_users(users)
    await update.message.reply_text(f"✅ Выдано {amount} {CURRENCY} пользователю {target_id}. Новый баланс: {user['balance']}")


async def cmd_take(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        target_id, amount = context.args[0], int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /take <user_id> <сумма>")
        return

    users = load_users()
    user = get_user(users, target_id)
    user["balance"] = max(0, user["balance"] - amount)
    save_users(users)
    await update.message.reply_text(f"✅ Списано {amount} {CURRENCY} у пользователя {target_id}. Новый баланс: {user['balance']}")


async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        target_id = context.args[0]
    except IndexError:
        await update.message.reply_text("Использование: /userinfo <user_id>")
        return

    users = load_users()
    if target_id not in users:
        await update.message.reply_text("Такого пользователя ещё нет в базе.")
        return
    user = users[target_id]
    wins = "\n".join(f"— {w}" for w in user["wins"]) or "нет"
    await update.message.reply_text(
        f"👤 Пользователь {target_id}\n"
        f"Баланс: {user['balance']} {CURRENCY}\n"
        f"Выполнено заданий: {len(user['completed_tasks'])}\n"
        f"Выигрыши:\n{wins}"
    )


async def cmd_addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        channel = context.args[0].lstrip("@")
        reward = int(context.args[1])
        title = " ".join(context.args[2:])
        if not title:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Использование: /addtask <канал_без_@> <награда> <текст задания>\n"
            "Пример: /addtask my_channel 50 Подпишись на наш канал"
        )
        return

    cfg = load_config()
    cfg["tasks"].append({"channel": channel, "reward": reward, "title": title})
    save_config(cfg)
    await update.message.reply_text(f"✅ Задание добавлено: {title} (+{reward} {CURRENCY})")


async def cmd_deltask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        index = int(context.args[0])
        cfg = load_config()
        removed = cfg["tasks"].pop(index)
        save_config(cfg)
        await update.message.reply_text(f"✅ Удалено задание: {removed['title']}")
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /deltask <номер> (см. /listtasks)")


async def cmd_listtasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cfg = load_config()
    if not cfg["tasks"]:
        await update.message.reply_text("Заданий пока нет.")
        return
    text = "📋 Задания:\n\n"
    for i, t in enumerate(cfg["tasks"]):
        text += f"{i}. {t['title']} — канал @{t['channel']}, +{t['reward']} {CURRENCY}\n"
    await update.message.reply_text(text)


async def cmd_addprize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        # Последние 1-2 аргумента — числа (шанс, и опционально бонусы), остальное — название
        args = context.args
        if len(args) < 2:
            raise ValueError
        # Пробуем понять, задан ли бонус (последний аргумент — число, предпоследний тоже число)
        coins = None
        if len(args) >= 3 and args[-1].isdigit() and args[-2].isdigit():
            coins = int(args[-1])
            weight = int(args[-2])
            name = " ".join(args[:-2])
        else:
            weight = int(args[-1])
            name = " ".join(args[:-1])
        if not name:
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Использование: /addprize <название> <шанс> [бонусы]\n"
            "Примеры:\n"
            "/addprize NFT Мишка 10  (предмет, выдаётся вручную)\n"
            "/addprize 20 Бонусов 15 20  (начисляет 20 бонусов автоматически)"
        )
        return

    cfg = load_config()
    prize = {"name": name, "weight": weight}
    if coins is not None:
        prize["coins"] = coins
    cfg["prizes"].append(prize)
    save_config(cfg)
    await update.message.reply_text(f"✅ Приз добавлен: {name} (шанс {weight})")


async def cmd_delprize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        index = int(context.args[0])
        cfg = load_config()
        removed = cfg["prizes"].pop(index)
        save_config(cfg)
        await update.message.reply_text(f"✅ Удалён приз: {removed['name']}")
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /delprize <номер> (см. /listprizes)")


async def cmd_listprizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cfg = load_config()
    if not cfg["prizes"]:
        await update.message.reply_text("Призов пока нет.")
        return
    text = "🎁 Призы в кейсе:\n\n"
    for i, p in enumerate(cfg["prizes"]):
        extra = f", начисляет {p['coins']} {CURRENCY}" if "coins" in p else " (выдаётся вручную)"
        text += f"{i}. {p['name']} — шанс {p['weight']}{extra}\n"
    text += f"\nСтоимость прокрута: {cfg['spin_cost']} {CURRENCY}"
    await update.message.reply_text(text)


async def cmd_setspincost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        amount = int(context.args[0])
        cfg = load_config()
        cfg["spin_cost"] = amount
        save_config(cfg)
        await update.message.reply_text(f"✅ Стоимость прокрута теперь {amount} {CURRENCY}")
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /setspincost <сумма>")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    users = load_users()
    total_users = len(users)
    total_balance = sum(u["balance"] for u in users.values())
    total_wins = sum(len(u["wins"]) for u in users.values())
    await update.message.reply_text(
        f"📊 Статистика GiftSpin\n\n"
        f"Пользователей: {total_users}\n"
        f"{CURRENCY} на балансах: {total_balance}\n"
        f"Всего выигрышей (предметов): {total_wins}"
    )


# -------------------- Запуск --------------------

def main():
    if ADMIN_ID == 0:
        print("⚠️  ВНИМАНИЕ: ты не задал ADMIN_ID в коде! Админ-команды не будут работать.")
        print("    Узнай свой ID у бота @userinfobot и впиши его в переменную ADMIN_ID.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Пользовательские команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Админ-команды
    app.add_handler(CommandHandler("admin", admin_help))
    app.add_handler(CommandHandler("give", cmd_give))
    app.add_handler(CommandHandler("take", cmd_take))
    app.add_handler(CommandHandler("userinfo", cmd_userinfo))
    app.add_handler(CommandHandler("addtask", cmd_addtask))
    app.add_handler(CommandHandler("deltask", cmd_deltask))
    app.add_handler(CommandHandler("listtasks", cmd_listtasks))
    app.add_handler(CommandHandler("addprize", cmd_addprize))
    app.add_handler(CommandHandler("delprize", cmd_delprize))
    app.add_handler(CommandHandler("listprizes", cmd_listprizes))
    app.add_handler(CommandHandler("setspincost", cmd_setspincost))
    app.add_handler(CommandHandler("stats", cmd_stats))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
