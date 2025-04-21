import aiosqlite
from loguru import logger
from config import settings
from typing import List, Tuple, Optional, Dict

DATABASE = settings.DATABASE_FILE

async def init_db():
    """Initializes the database and creates tables if they don't exist."""
    async with aiosqlite.connect(DATABASE) as db:
        # Table for user settings
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                mood TEXT DEFAULT ?,
                speak_enabled INTEGER DEFAULT 0
            )
        ''', (settings.DEFAULT_MOOD,))

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
        async with db.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp ASC LIMIT ?",
            (user_id, settings.MAX_CONTEXT_MESSAGES)
        ) as cursor:
            async for row in cursor:
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
                await db.execute(
                    "INSERT OR IGNORE INTO users (user_id, mood, speak_enabled) VALUES (?, ?, ?)",
                    (user_id, settings.DEFAULT_MOOD, 0)
                )
                await db.commit()
                logger.info(f"Created default settings for new user {user_id}")
                return {"mood": settings.DEFAULT_MOOD, "speak_enabled": False}

async def update_user_mood(user_id: int, mood: str):
    """Updates the user's mood preference."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "INSERT INTO users (user_id, mood) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET mood = excluded.mood",
            (user_id, mood)
        )
        await db.commit()
    logger.info(f"Updated mood for user {user_id} to {mood}")

async def toggle_speak_mode(user_id: int) -> bool:
    """Toggles the speak mode for the user and returns the new state."""
    async with aiosqlite.connect(DATABASE) as db:
        # Ensure user exists first
        await get_user_settings(user_id) # This creates the user if they don't exist

        # Get current state and toggle it
        async with db.execute("SELECT speak_enabled FROM users WHERE user_id = ?", (user_id,)) as cursor:
            current_state = await cursor.fetchone()
            new_state = not bool(current_state[0])

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