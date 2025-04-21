from typing import Callable, Dict, Any, Awaitable
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
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:

        # Проверяем только для событий, у которых есть пользователь (Сообщения, Колбэки)
        user: Optional[User] = None
        chat_id: Optional[int] = None

        if isinstance(event, Message):
            user = event.from_user
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            chat_id = event.message.chat.id if event.message else None
        # Можно добавить другие типы event по необходимости (InlineQuery, etc.)

        if user:
            user_id = user.id
            # Если список AUTHORIZED_USERS пуст, разрешаем всем (но выводим предупреждение при старте)
            if not settings.AUTHORIZED_USERS:
                 # logger.debug(f"AuthMiddleware: AUTHORIZED_USERS is empty, allowing user {user_id}")
                 return await handler(event, data)

            if user_id not in settings.AUTHORIZED_USERS:
                logger.warning(f"Unauthorized access attempt by user {user_id} ({user.full_name or user.username})")
                if chat_id:
                    # Пытаемся отправить сообщение, если это возможно
                    try:
                        # Используем data['bot'], который должен быть доступен в middleware
                        await data['bot'].send_message(chat_id, "⛔ Доступ запрещён.")
                    except Exception as e:
                         logger.error(f"Failed to send 'Access Denied' message to {chat_id}: {e}")
                return # Прерываем обработку события
            else:
                # logger.debug(f"AuthMiddleware: User {user_id} is authorized.")
                # Передаем user_id в data для удобства в хэндлерах
                data['user_id'] = user_id
                return await handler(event, data)
        else:
            # Если событие не содержит информации о пользователе, пропускаем проверку
            # logger.debug(f"AuthMiddleware: Event type {type(event)} does not have user info, skipping auth check.")
            return await handler(event, data)