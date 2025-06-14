from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup # Or ReplyKeyboardMarkup, depending on usage

MAX_MESSAGE_LENGTH = 4096

async def send_long_message(bot: Bot, chat_id: int, text: str, reply_markup=None, parse_mode: str = None):
    """
    Sends a long message, splitting it into parts if it exceeds Telegram's limit.
    """
    if len(text) <= MAX_MESSAGE_LENGTH:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        parts = []
        while len(text) > 0:
            if len(text) > MAX_MESSAGE_LENGTH:
                part = text[:MAX_MESSAGE_LENGTH]
                # Try to split at the last newline character to make messages prettier
                last_newline = part.rfind('\n')
                if last_newline != -1:
                    # Check if the newline is too far back (e.g., more than half the message length)
                    # to avoid creating very small initial parts if the last newline is very early.
                    # This threshold can be adjusted.
                    if last_newline > MAX_MESSAGE_LENGTH / 2:
                        part = text[:last_newline]
                        text = text[last_newline+1:]
                    else:
                        # If newline is too early, or for very long lines without newlines,
                        # just split at MAX_MESSAGE_LENGTH
                        part = text[:MAX_MESSAGE_LENGTH]
                        text = text[MAX_MESSAGE_LENGTH:]
                else:
                    # If no newline, split at MAX_MESSAGE_LENGTH
                    part = text[:MAX_MESSAGE_LENGTH]
                    text = text[MAX_MESSAGE_LENGTH:]
                parts.append(part)
            else:
                parts.append(text)
                break

        for i, part_text in enumerate(parts):
            if i == len(parts) - 1: # Send reply_markup only with the last part
                await bot.send_message(chat_id=chat_id, text=part_text, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                await bot.send_message(chat_id=chat_id, text=part_text, parse_mode=parse_mode)
