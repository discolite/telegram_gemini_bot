from typing import Callable, Dict, Any, Awaitable, Optional # <--- ИЗМЕНЕНИЕ: Добавлены импорты
from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery, User
from loguru import logger

from config import settings # Импортируем напрямую для доступа к AUTHORIZED_USERS

class AuthMiddleware(BaseMiddleware):
    """
    Middleware to check if the user is authorized based on user ID.
    """
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]], # Используются Callable, Dict, Any, Awaitable
        event: Update,
        data: Dict[str, Any] # Используется Dict, Any
    ) -> Any:

        # Проверяем только для событий, у которых есть пользователь (Сообщения, Колбэки)
        user: Optional[User] = data.get('event_from_user') # Получаем пользователя из data (стандарт aiogram 3)
        chat: Optional[Any] = data.get('event_chat') # Получаем чат из data
        chat_id: Optional[int] = chat.id if chat else None

        # Если пользователя нет в данных (некоторые типы обновлений), пропускаем
        if not user:
             # logger.debug(f"AuthMiddleware: No user found in event data ({type(event)}), skipping auth check.")
             return await handler(event, data)

        user_id = user.id

        # Если список AUTHORIZED_USERS пуст в .env, разрешаем всем (но выводим предупреждение при старте)
        if not settings.AUTHORIZED_USERS:
             # logger.debug(f"AuthMiddleware: AUTHORIZED_USERS is empty, allowing user {user_id}")
             # Добавляем user_id в data для хэндлеров, даже если авторизация отключена
             data['user_id'] = user_id
             return await handler(event, data)

        # Проверяем авторизацию
        if user_id not in settings.AUTHORIZED_USERS:
            logger.warning(f"Unauthorized access attempt by user {user_id} ({user.full_name or user.username}) in chat {chat_id}")
            if chat_id:
                # Пытаемся отправить сообщение, если это возможно
                try:
                    # Используем data['bot'], который должен быть доступен в middleware
                    bot = data.get('bot')
                    if bot:
                        await bot.send_message(chat_id, "⛔ Доступ запрещён.")
                    else:
                        logger.error("Bot instance not found in middleware data to send 'Access Denied' message.")
                except Exception as e:
                     logger.error(f"Failed to send 'Access Denied' message to {chat_id}: {e}")
            return # Прерываем обработку события
        else:
            # logger.debug(f"AuthMiddleware: User {user_id} is authorized.")
            # Передаем user_id в data для удобства в хэндлерах
            data['user_id'] = user_id
            return await handler(event, data)