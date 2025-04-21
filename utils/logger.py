# utils/logger.py
# Используем loguru, который уже настроен в config/settings.py
from loguru import logger

# Экспортируем настроенный логгер для использования в других модулях
log = logger

# Пример использования:
# from utils.logger import log
# log.info("Это информационное сообщение")
# log.error("Это сообщение об ошибке")