import logging
import os
import re
from html import escape
from typing import Optional

from dotenv import load_dotenv
from telegram import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

ASK_NAME, ASK_CONTACT, ASK_DAY, ASK_TIME = range(4)

PHONE_ICON = "\U0001F4DE"
PIN_ICON = "\U0001F4CC"
CALENDAR_ICON = "\U0001F4C5"
CLOCK_ICON = "\U000023F0"
USER_ICON = "\U0001F464"
LINK_ICON = "\U0001F517"
def build_contact_keyboard() -> ReplyKeyboardMarkup:
    button = KeyboardButton(f"{PHONE_ICON} Kontaktni yuborish", request_contact=True,style="danger")
    return ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)


def build_day_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text="Bugun", style="danger")], [KeyboardButton(text="Ertaga", style="primary")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _safe_name(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "Mijoz"
    return user.full_name or user.first_name or "Mijoz"


def _format_manager_text(
    name: str,
    phone: str,
    day: str,
    time_text: str,
    user_link: str,
    username: Optional[str],
) -> str:
    username_line = (
        f"{LINK_ICON} Username: @{username}" if username else f"{LINK_ICON} Username: yo'q"
    )
    return (
        f"{PIN_ICON} Yangi buyurtma qabul qilindi\n"
        f"{USER_ICON} Ism: {name}\n"
        f"{PHONE_ICON} Telefon: {phone}\n"
        f"{CALENDAR_ICON} Kun: {day}\n"
        f"{CLOCK_ICON} Vaqt: {time_text}\n"
        f"{USER_ICON} Foydalanuvchi: {user_link}\n"
        f"{username_line}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Salom! Ismingizni kiriting, iltimos.", reply_markup=ReplyKeyboardRemove()
    )
    return ASK_NAME


async def ask_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not text:
        text = _safe_name(update)
    context.user_data["name"] = text
    await update.message.reply_text(
        "Kontakt raqamingizni yuboring.", reply_markup=build_contact_keyboard()
    )
    return ASK_CONTACT


async def ask_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact = ""
    if update.message.contact:
        contact = update.message.contact.phone_number or ""
        if update.message.contact.first_name:
            context.user_data.setdefault("name", update.message.contact.first_name)
    else:
        contact = (update.message.text or "").strip()
    context.user_data["phone"] = contact or "Kontakt yo'q"
    await update.message.reply_text(
        "Qaysi kun uchun buyurtma kerak?",
        reply_markup=build_day_keyboard(),
    )
    return ASK_DAY


async def ask_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    day_choice = (update.message.text or "").strip().capitalize()
    if day_choice not in {"Bugun", "Ertaga"}:
        await update.message.reply_text(
            "Faqat 'Bugun' yoki 'Ertaga' tugmalaridan birini bosing."
        )
        return ASK_DAY
    context.user_data["day"] = day_choice
    await update.message.reply_text(
        "Qaysi vaqtga buyurtma beriladi? Masalan: 17:00",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_TIME


async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_text = (update.message.text or "").strip()
    context.user_data["time"] = time_text or "Vaqt ko'rsatilmagan"

    user = update.effective_user
    name = context.user_data.get("name") or _safe_name(update)
    phone = context.user_data.get("phone") or "Kontakt yo'q"
    day = context.user_data.get("day") or "Kun ko'rsatilmagan"
    user_link = (
        f"<a href=\"tg://user?id={user.id}\">{escape(name)}</a>"
        if user
        else name
    )
    username = user.username if user else None
    barber_address = os.environ.get(
        "BARBER_ADDRESS", "Barber salon manzili hozirda mavjud emas."
    )

    await update.message.reply_text(
        "✅ Zakazingiz qabul qilindi, sizga aloqaga chiqamiz.",
        parse_mode=ParseMode.HTML,
    )

    manager_chat_id = os.environ.get("MANAGER_CHAT_ID")
    if manager_chat_id:
        try:
            await context.bot.send_message(
                chat_id=int(manager_chat_id),
                text=_format_manager_text(
                    name=name,
                    phone=phone,
                    day=day,
                    time_text=context.user_data["time"],
                    user_link=user_link,
                    username=username,
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:  # pragma: no cover
            logging.exception("Manager guruhiga xabar yuborishda xatolik: %s", exc)
    else:
        logging.warning("MANAGER_CHAT_ID muhit o'zgaruvchisi o'rnatilmagan.")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Buyurtma bekor qilindi.", reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END


async def send_heartbeat(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = os.environ.get("MANAGER_CHAT_ID")
    if not chat_id:
        logging.debug("Heartbeat ignored because MANAGER_CHAT_ID is not set.")
        return
    message = os.environ.get("HEARTBEAT_MESSAGE", "Bot faoliyatda, signal yuborildi.")
    try:
        await context.bot.send_message(chat_id=int(chat_id), text=message)
        logging.info("Heartbeat yuborildi.")
    except Exception as exc:  # pragma: no cover
        logging.warning("Heartbeat yuborishda xatolik: %s", exc)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN muhit o'zgaruvchisi o'rnatilishi kerak.")

    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(8)
        .build()
    )

    heartbeat_interval = int(os.environ.get("HEARTBEAT_INTERVAL", "300"))
    if application.job_queue is None:
        logging.warning(
            "JobQueue not available; heartbeat scheduling skipped. "
            "Install python-telegram-bot[job-queue] if you need it."
        )
    else:
        application.job_queue.run_repeating(
            send_heartbeat,
            interval=heartbeat_interval,
            first=heartbeat_interval,
        )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_contact)],
            ASK_CONTACT: [
                MessageHandler(
                    filters.CONTACT | (filters.TEXT & ~filters.COMMAND), ask_day
                )
            ],
            ASK_DAY: [
            MessageHandler(
                filters.Regex("^(Bugun|Ertaga)$", flags=re.IGNORECASE), ask_time
            )
            ],
            ASK_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, finalize)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == "__main__":
    main()
