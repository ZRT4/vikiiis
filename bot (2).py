import os
import json
import random
import logging
import threading
from datetime import time as dtime
from zoneinfo import ZoneInfo
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = "8634178334:AAGdIGqXstckYNAQHFQ_y0wFCjhr-37NIIs"
OWNER_ID = 5952825437  # ВАШ TELEGRAM ID СЮДА

USERS_FILE = "users.json"
DEFAULT_TIME = "09:00"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# =========================
# PING-СЕРВЕР (для fps.ms)
# =========================

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # Отключаем лишние логи от сервера

def run_ping_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    server.serve_forever()

# =========================
# IN-MEMORY CACHE
# =========================

_users_cache: dict = {}

def load_users() -> dict:
    global _users_cache
    if _users_cache:
        return _users_cache
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                _users_cache = json.load(f)
        except Exception as e:
            logger.warning(f"Не удалось загрузить users.json: {e}")
            _users_cache = {}
    return _users_cache

def save_users(data: dict):
    global _users_cache
    _users_cache = data
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Не удалось сохранить users.json: {e}")

def _default_user() -> dict:
    return {"time": DEFAULT_TIME, "waiting_media": False}

def add_user(uid: int):
    users = load_users()
    if str(uid) not in users:
        users[str(uid)] = _default_user()
        save_users(users)

def update_user(uid: int, **kwargs):
    users = load_users()
    user = users.get(str(uid), _default_user())
    user.update(kwargs)
    users[str(uid)] = user
    save_users(users)

def get_user(uid: int) -> dict:
    users = load_users()
    return users.get(str(uid), _default_user())

# =========================
# UI
# =========================

def user_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🌅 Предсказание дня"],
            ["💌 Подарок"],
            ["🎭 Поднять настроение Яну"]
        ],
        resize_keyboard=True
    )

def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ Установить время", callback_data="set_time")],
        [InlineKeyboardButton("💭 Кто-то думает (всем)", callback_data="think_all")]
    ])

# =========================
# ПРЕДСКАЗАНИЯ — 60 фраз
# =========================

IDEAS = [
    "🌙 Сегодня кто-то неожиданно вспомнит о тебе",
    "💫 Вечером тебя ждёт приятный момент",
    "🌸 День будет спокойнее, чем кажется утром",
    "✨ Кто-то хочет написать тебе первым",
    "💌 Сегодня стоит довериться интуиции",
    "🌿 У тебя получится отпустить лишние мысли",
    "🌙 Один разговор изменит настроение к лучшему",
    "💭 Кто-то скучает по тебе сильнее, чем показывает",
    "✨ Тебя ждёт маленький сюрприз",
    "🌸 Сегодня особенно важно слушать себя",
    "💫 Твоё настроение может заразить других теплом",
    "🌙 Этот день запомнится одной тихой мелочью",
    "💌 Очень скоро ты услышишь нужные слова",
    "✨ Кто-то наблюдает за тобой с симпатией",
    "🌿 Сегодня удачный день для новых мыслей",
    "🌸 Утро только кажется обычным — оно особенное",
    "💫 Твой день начнётся медленно, но закончится хорошо",
    "🌙 Сегодня что-то произойдёт точно в нужный момент",
    "💌 Кто-то сегодня скажет тебе именно то, что нужно",
    "✨ День принесёт неожиданную радость",
    "🌿 Твоя интуиция сегодня особенно точна",
    "🌸 Сегодня хороший день, чтобы позволить себе отдохнуть",
    "💫 Кто-то вспомнит о тебе с улыбкой",
    "🌙 Маленькое везение ждёт тебя там, где не ожидаешь",
    "💌 Твой день будет согрет чьей-то заботой",
    "✨ Сегодня можно немного больше доверять миру",
    "🌿 Что-то, что беспокоило, само собой разрешится",
    "🌸 Один момент сегодня захочется запомнить навсегда",
    "💫 К тебе придёт нужная мысль в самый подходящий момент",
    "🌙 Сегодня кто-то будет рад тебя видеть",
    "💌 Ты узнаешь кое-что приятное о себе",
    "✨ Сегодня особенно хорошо работает притяжение хорошего",
    "🌿 День подарит тебе минуту настоящей тишины",
    "🌸 Кто-то думает о тебе прямо сейчас",
    "💫 Сегодня твоя улыбка будет иметь значение",
    "🌙 Ты окажешься в нужном месте в нужное время",
    "💌 Что-то хорошее уже движется к тебе",
    "✨ Сегодня легче будет сказать то, что давно хотелось",
    "🌿 Твои слова сегодня попадут точно в цель",
    "🌸 Один взгляд или жест сделает день теплее",
    "💫 Сегодня мир будет немного на твоей стороне",
    "🌙 Что-то незаметное сегодня изменится к лучшему",
    "💌 Хорошие новости приходят неожиданно — сегодня их день",
    "✨ Ты справишься с тем, что казалось трудным",
    "🌿 Сегодня стоит обратить внимание на мелочи",
    "🌸 Кто-то видит в тебе больше, чем ты сама",
    "💫 Сегодня ты почувствуешь лёгкость там, где её не ждала",
    "🌙 Твоё присутствие сегодня кому-то очень нужно",
    "💌 День сложится лучше, чем планировалось",
    "✨ Сегодня можно позволить себе быть счастливой просто так",
    "🌿 Что-то хорошее начинается сегодня — ты пока не знаешь об этом",
    "🌸 Сегодня у тебя получится то, что не давалось раньше",
    "💫 Тебя ждёт момент, который захочется сохранить в памяти",
    "🌙 Кто-то очень хочет тебя порадовать",
    "💌 Сегодня ты будешь особенно притягательна",
    "✨ Твой день начнётся с одного правильного ощущения",
    "🌿 Сегодня всё встанет на свои места",
    "🌸 Один человек сегодня будет думать только о тебе",
    "💫 Ты сделаешь чей-то день лучше, сама того не заметив",
    "🌙 Сегодня Вселенная действует в твою пользу"
]

# =========================
# ПОДАРКИ — 50 фраз
# =========================

GIFTS = [
    "💌 Ты умеешь делать мир спокойнее одним сообщением",
    "🌸 Ты красивее, чем думаешь о себе",
    "💖 Иногда достаточно просто твоего присутствия",
    "✨ Ты сегодня особенно нужна этому миру",
    "🌙 Кто-то сейчас улыбается, вспоминая тебя",
    "💫 Ты оставляешь после себя тёплые эмоции",
    "🌿 С тобой даже обычный день становится лучше",
    "💌 Ты очень уютный человек",
    "🌸 У тебя редкая энергетика",
    "✨ Ты заслуживаешь гораздо больше хорошего",
    "💖 Твоя забота — одна из самых ценных вещей в этом мире",
    "🌙 Ты умеешь слушать так, как мало кто умеет",
    "💫 Рядом с тобой люди чувствуют себя нужными",
    "🌿 Ты сильнее, чем кажешься себе в трудные моменты",
    "💌 Ты создаёшь тепло просто своим существованием",
    "🌸 В тебе есть что-то, что невозможно не заметить",
    "✨ Твоя улыбка — это отдельный подарок миру",
    "💖 Ты умеешь находить красоту там, где другие не видят",
    "🌙 Тебя любят больше, чем ты об этом знаешь",
    "💫 Ты меняешь настроение вокруг себя в лучшую сторону",
    "🌿 Твой голос успокаивает",
    "💌 Ты именно такая, какой нужно быть",
    "🌸 Люди чувствуют себя лучше после разговора с тобой",
    "✨ Ты заслуживаешь того хорошего, о чём боишься мечтать",
    "💖 Твоя нежность — это сила, а не слабость",
    "🌙 Ты притягиваешь хороших людей",
    "💫 Рядом с тобой легче дышится",
    "🌿 Ты умеешь превращать простые моменты в особенные",
    "💌 В тебе столько тепла, что хватит на всех",
    "🌸 Ты красива даже в моменты, когда сама себя не видишь",
    "✨ Твоя интуиция — один из твоих лучших талантов",
    "💖 Ты достаточно. Прямо сейчас — достаточно",
    "🌙 Кто-то благодарен тебе за то, о чём ты уже забыла",
    "💫 Ты умеешь любить по-настоящему — это редкость",
    "🌿 Твоё присутствие в чьей-то жизни — это подарок",
    "💌 Ты сегодня выглядишь особенно хорошо",
    "🌸 Твои руки создают уют везде, куда ты приходишь",
    "✨ Кто-то очень рад, что ты есть",
    "💖 Ты помогаешь людям чувствовать себя увиденными",
    "🌙 Твоя искренность — твоя суперсила",
    "💫 Ты не просто нравишься — тебя ценят",
    "🌿 Твоя доброта не остаётся незамеченной",
    "💌 Ты умеешь быть настоящей — это очень много",
    "🌸 Твоя энергия сегодня особенно притягательна",
    "✨ Ты делаешь мир немного добрее просто тем, что в нём есть",
    "💖 Тебя замечают даже тогда, когда ты думаешь, что нет",
    "🌙 Ты сильная — даже в моменты, когда это незаметно",
    "💫 Твоя любовь к жизни заряжает окружающих",
    "🌿 Ты именно та, кем нужно быть прямо сейчас",
    "💌 Кто-то мечтает о таком человеке, как ты"
]

# =========================
# ГЕНЕРАТОРЫ БЕЗ ПОВТОРОВ
# =========================

def _make_generator(pool: list):
    deck: list = []
    def pick() -> str:
        nonlocal deck
        if not deck:
            deck = pool[:]
            random.shuffle(deck)
        return deck.pop()
    return pick

morning_text = _make_generator(IDEAS)
gift_text    = _make_generator(GIFTS)

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    add_user(uid)
    update_user(uid, waiting_media=False)
    await update.message.reply_text(
        "💖 Добро пожаловать",
        reply_markup=user_keyboard()
    )

# =========================
# ADMIN
# =========================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("⛔ нет доступа")
    await update.message.reply_text(
        "🔐 Админ панель",
        reply_markup=admin_panel()
    )

# =========================
# CALLBACKS
# =========================

async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if update.effective_user.id != OWNER_ID:
        return

    if q.data == "think_all":
        msgs = [
            "💭 кто-то сейчас думает о тебе…",
            "✨ ты сегодня в чьих-то мыслях",
            "💌 тебя сейчас вспоминают",
            "🌙 кто-то хочет тебе написать",
            "💫 о тебе сейчас говорят",
            "🌸 кому-то очень нравится твоя энергия",
            "💖 кто-то улыбнулся, вспомнив тебя",
            "🌿 ты занимаешь чьи-то мысли прямо сейчас"
        ]
        users = load_users()
        for uid in users:
            try:
                await context.bot.send_message(
                    int(uid),
                    random.choice(msgs),
                    reply_markup=user_keyboard()
                )
            except Exception as e:
                logger.warning(f"think_all → {uid}: {e}")
        await q.message.reply_text("✅ отправлено всем")

    elif q.data == "set_time":
        context.user_data["wait_time"] = True
        await q.message.reply_text("⏰ Отправь время в формате: 09:00")

# =========================
# TEXT HANDLER
# =========================

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    text = update.message.text

    add_user(uid)

    # --- Ввод времени от админа ---
    if uid == OWNER_ID and context.user_data.get("wait_time"):
        try:
            h, m = map(int, text.strip().split(":"))
            assert 0 <= h <= 23 and 0 <= m <= 59
            users = load_users()
            for user_id in users:
                users[user_id]["time"] = f"{h:02d}:{m:02d}"
            save_users(users)
            schedule(context.application)
            context.user_data["wait_time"] = False
            return await update.message.reply_text(f"⏰ Установлено: {h:02d}:{m:02d} МСК")
        except Exception:
            return await update.message.reply_text("❌ Неверный формат. Попробуй ещё раз: 09:00")

    # --- Кнопки ---
    if text == "🌅 Предсказание дня":
        return await update.message.reply_text(morning_text(), reply_markup=user_keyboard())

    elif text == "💌 Подарок":
        return await update.message.reply_text(gift_text(), reply_markup=user_keyboard())

    elif text == "🎭 Поднять настроение Яну":
        update_user(uid, waiting_media=True)
        return await update.message.reply_text(
            "💖 Отправь:\n\n• текст\n• фото\n• видео\n• кружок\n• голосовое\n• гиф\n• аудио\n• файл\n\nЯ всё передам Яну ✨",
            reply_markup=user_keyboard()
        )

    # --- Текст → Яну ---
    user = get_user(uid)
    if user.get("waiting_media"):
        username = update.effective_user.username
        sender = f"@{username}" if username else str(uid)
        try:
            await context.bot.send_message(
                OWNER_ID,
                f"💬 Сообщение от {sender}:\n\n{text}"
            )
            update_user(uid, waiting_media=False)
            await update.message.reply_text("💖 Отправлено Яну", reply_markup=user_keyboard())
        except Exception as e:
            logger.warning(f"Пересылка текста → {uid}: {e}")

# =========================
# MEDIA → ADMIN
# =========================

async def forward_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id

    if uid == OWNER_ID:
        return

    user = get_user(uid)
    if not user.get("waiting_media"):
        return

    try:
        msg = update.message
        username = update.effective_user.username
        sender = f"@{username}" if username else str(uid)
        caption = f"💖 от {sender}"

        sent = True
        user_caption = msg.caption
        if msg.photo:
            full_caption = caption + (f"\n\n{user_caption}" if user_caption else "")
            await context.bot.send_photo(OWNER_ID, msg.photo[-1].file_id, caption=full_caption)
        elif msg.video:
            full_caption = caption + (f"\n\n{user_caption}" if user_caption else "")
            await context.bot.send_video(OWNER_ID, msg.video.file_id, caption=full_caption)
        elif msg.voice:
            await context.bot.send_voice(OWNER_ID, msg.voice.file_id)
            await context.bot.send_message(OWNER_ID, caption)
        elif msg.video_note:
            await context.bot.send_video_note(OWNER_ID, msg.video_note.file_id)
            await context.bot.send_message(OWNER_ID, caption)
        elif msg.audio:
            await context.bot.send_audio(OWNER_ID, msg.audio.file_id, caption=caption)
        elif msg.document:
            await context.bot.send_document(OWNER_ID, msg.document.file_id, caption=caption)
        elif msg.sticker:
            await context.bot.send_sticker(OWNER_ID, msg.sticker.file_id)
            await context.bot.send_message(OWNER_ID, caption)
        elif msg.animation:
            full_caption = caption + (f"\n\n{user_caption}" if user_caption else "")
            await context.bot.send_animation(OWNER_ID, msg.animation.file_id, caption=full_caption)
        else:
            sent = False

        if sent:
            update_user(uid, waiting_media=False)
            await update.message.reply_text("💖 Отправлено Яну", reply_markup=user_keyboard())

    except Exception as e:
        logger.warning(f"forward_media → {uid}: {e}")

# =========================
# MORNING JOB
# =========================

async def morning_job(context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    for uid in users:
        try:
            await context.bot.send_message(
                int(uid),
                "🌅 " + morning_text(),
                reply_markup=user_keyboard()
            )
        except Exception as e:
            logger.warning(f"morning_job → {uid}: {e}")

# =========================
# SCHEDULE
# =========================

def schedule(app: Application):
    jq = app.job_queue
    for job in jq.jobs():
        if job.name == "morning":
            job.schedule_removal()

    users = load_users()
    time_str = DEFAULT_TIME
    if users:
        first_user = next(iter(users.values()))
        time_str = first_user.get("time", DEFAULT_TIME)

    try:
        h, m = map(int, time_str.split(":"))
    except ValueError:
        h, m = 9, 0

    jq.run_daily(
        morning_job,
        time=dtime(hour=h, minute=m, tzinfo=ZoneInfo("Europe/Moscow")),
        name="morning"
    )
    logger.info(f"Рассылка запланирована на {h:02d}:{m:02d} МСК")

# =========================
# MAIN
# =========================

def main():
    # Запускаем ping-сервер в фоновом потоке
    t = threading.Thread(target=run_ping_server, daemon=True)
    t.start()
    logger.info("Ping-сервер запущен на порту 8080")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.VOICE |
            filters.VIDEO_NOTE | filters.AUDIO | filters.Document.ALL |
            filters.Sticker.ALL | filters.ANIMATION,
            forward_media
        )
    )

    schedule(app)

    logger.info("BOT RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
