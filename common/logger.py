import logging
from logging import handlers

def setup_logger(logger_name, log_file, level=logging.DEBUG, encoding='utf-8'):
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    file_handler = handlers.RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding=encoding)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
