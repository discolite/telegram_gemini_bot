from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_mood_keyboard() -> InlineKeyboardMarkup:
    """Creates an inline keyboard for selecting the communication mood."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="😊 Дружелюбный", callback_data="set_mood:friendly"),
        InlineKeyboardButton(text="🧐 Профессиональный", callback_data="set_mood:professional")
    )
    builder.row(
        InlineKeyboardButton(text="😏 Саркастичный", callback_data="set_mood:sarcastic")
    )
    return builder.as_markup()

# Можно добавить другие клавиатуры по необходимости