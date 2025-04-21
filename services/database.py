import aiosqlite
from loguru import logger
from config import settings
from typing import List, Tuple, Optional, Dict

DATABASE = settings.DATABASE_FILE

async def init_db():
    """Initializes the database and creates tables if they don't exist."""
    async with aiosqlite.connect(DATABASE) as db:
        # Table for user settings
        # Встраиваем значение DEFAULT напрямую, т.к. плейсхолдеры здесь не работают
        # Экранируем одинарные кавычки на всякий случай (хотя для 'friendly' и т.д. не нужно)
        default_mood_sql = settings.DEFAULT_MOOD.replace("'", "''")
        await db.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                mood TEXT DEFAULT '{default_mood_sql}',
                speak_enabled INTEGER DEFAULT 0
            )
        ''')
        # Параметры больше не нужны для этого запроса

        # Table for message history (context)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT, -- 'user' or 'model'
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_timestamp ON messages (user_id, timestamp);
        ''')
        await db.commit()
    logger.info(f"Database initialized successfully at {DATABASE}")

async def add_message(user_id: int, role: str, content: str):
    """Adds a message to the history and prunes old messages."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        # Prune messages, keeping only the last N
        await db.execute('''
            DELETE FROM messages
            WHERE id NOT IN (
                SELECT id FROM messages
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ) AND user_id = ?
        ''', (user_id, settings.MAX_CONTEXT_MESSAGES * 2, user_id)) # *2 to roughly keep pairs
        await db.commit()

async def get_message_history(user_id: int) -> List[Dict[str, str]]:
    """Retrieves the last N messages for a user."""
    history = []
    async with aiosqlite.connect(DATABASE) as db:
        # Убедимся, что MAX_CONTEXT_MESSAGES > 0
        limit = max(1, settings.MAX_CONTEXT_MESSAGES) # Запрашиваем хотя бы 1 сообщение
        async with db.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit) # Используем DESC для получения последних, затем развернем
        ) as cursor:
            rows = await cursor.fetchall()
            # Разворачиваем результат, чтобы порядок был от старых к новым
            for row in reversed(rows):
                history.append({"role": row[0], "content": row[1]})
    return history

async def get_user_settings(user_id: int) -> Dict[str, any]:
    """Gets user settings, creating default entry if user doesn't exist."""
    async with aiosqlite.connect(DATABASE) as db:
        async with db.execute(
            "SELECT mood, speak_enabled FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"mood": row[0], "speak_enabled": bool(row[1])}
            else:
                # Create default entry for new user
                try:
                    await db.execute(
                        "INSERT INTO users (user_id, mood, speak_enabled) VALUES (?, ?, ?)",
                        (user_id, settings.DEFAULT_MOOD, 0)
                    )
                    await db.commit()
                    logger.info(f"Created default settings for new user {user_id}")
                    return {"mood": settings.DEFAULT_MOOD, "speak_enabled": False}
                except aiosqlite.IntegrityError:
                    # На случай гонки потоков, если другой процесс успел вставить пользователя
                    logger.warning(f"User {user_id} likely already exists (IntegrityError on insert). Fetching again.")
                    # Повторно пытаемся получить настройки
                    async with db.execute("SELECT mood, speak_enabled FROM users WHERE user_id = ?", (user_id,)) as retry_cursor:
                        row = await retry_cursor.fetchone()
                        if row:
                            return {"mood": row[0], "speak_enabled": bool(row[1])}
                        else:
                            # Этого не должно произойти, но на всякий случай
                            logger.error(f"Failed to create or find settings for user {user_id} after IntegrityError.")
                            return {"mood": settings.DEFAULT_MOOD, "speak_enabled": False}


async def update_user_mood(user_id: int, mood: str):
    """Updates the user's mood preference."""
    async with aiosqlite.connect(DATABASE) as db:
        # Сначала убедимся, что пользователь существует (или создаем его)
        await get_user_settings(user_id)
        # Затем обновляем
        await db.execute(
            "UPDATE users SET mood = ? WHERE user_id = ?",
            (mood, user_id)
        )
        await db.commit()
    logger.info(f"Updated mood for user {user_id} to {mood}")

async def toggle_speak_mode(user_id: int) -> bool:
    """Toggles the speak mode for the user and returns the new state."""
    async with aiosqlite.connect(DATABASE) as db:
        # Ensure user exists first
        settings_data = await get_user_settings(user_id) # This creates the user if they don't exist

        # Get current state and toggle it
        current_state = settings_data.get("speak_enabled", False)
        new_state = not current_state

        # Update the state
        await db.execute(
            "UPDATE users SET speak_enabled = ? WHERE user_id = ?",
            (int(new_state), user_id)
        )
        await db.commit()
    logger.info(f"Toggled speak mode for user {user_id} to {new_state}")
    return new_state

async def get_speak_enabled(user_id: int) -> bool:
    """Checks if speak mode is enabled for the user."""
    settings_data = await get_user_settings(user_id)
    return settings_data.get("speak_enabled", False)