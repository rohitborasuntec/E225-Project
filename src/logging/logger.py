# logger.py
import logging
import csv
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import sys

# Global logger instance
_logger = None


class CsvLogHandler(logging.Handler):
    """Write the same complete application log to a readable CSV file."""

    def __init__(self, path):
        super().__init__()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as file:
                csv.writer(file).writerow(
                    ["Timestamp", "Level", "Logger", "Message"]
                )

    def emit(self, record):
        try:
            with self.path.open("a", newline="", encoding="utf-8") as file:
                csv.writer(file).writerow([
                    self.format(record).split(" | ", 1)[0],
                    record.levelname,
                    record.name,
                    record.getMessage(),
                ])
        except Exception:
            self.handleError(record)

def get_logger(
    name="E225Project",
    log_dir="Logs",
    csv_log_dir="CSV Logs",
    log_level=logging.INFO,
):
    """
    Get or create a logger instance
    
    Args:
        name (str): Logger name
        log_dir (str): Directory to store log files
        log_level (int): Logging level
    
    Returns:
        logging.Logger: Configured logger instance
    """
    global _logger
    
    if _logger is not None:
        return _logger
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_path = Path(log_dir) / date_str
    log_path.mkdir(parents=True, exist_ok=True)
    csv_log_path = Path(csv_log_dir) / date_str
    csv_log_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"{name}_{timestamp}.log"
    csv_file = csv_log_path / f"{name}_{timestamp}.csv"
    
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.propagate = False
    
    if logger.handlers:
        logger.handlers.clear()
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding="utf-8"
    )
    
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    csv_handler = CsvLogHandler(csv_file)
    csv_handler.setLevel(logging.DEBUG)
    csv_handler.setFormatter(formatter)
    logger.addHandler(csv_handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    _logger = logger
    
    logger.info("=" * 70)
    logger.info(f"Logger initialized: {log_file}")
    logger.info("=" * 70)
    
    return logger

# Convenience functions
def debug(message):
    get_logger().debug(message)

def info(message):
    message = f"{'-'*10} {message} {'-'*10}" 
    get_logger().info(message)

def warning(message):
    get_logger().warning(message)

def error(message):
    get_logger().error(message)

def critical(message):
    get_logger().critical(message)

def exception(message):
    get_logger().exception(message)

# Example usage
if __name__ == "__main__":
    logger = get_logger()
    logger.info("Test log message")
    logger.debug("Debug message")
    logger.warning("Warning message")
