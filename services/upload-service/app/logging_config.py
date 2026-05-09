"""Logging configuration for security monitoring."""
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(service_name: str) -> None:
    """Configure logging with security-focused settings."""
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Formatters
    standard_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    security_formatter = logging.Formatter(
        '%(asctime)s - SECURITY - %(levelname)s - %(message)s - IP:%(client_ip)s - User:%(user)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(standard_formatter)
    logger.addHandler(console_handler)
    
    # File handler for security events
    log_dir = os.getenv("LOG_DIR", "/var/log/archianalyzer")
    os.makedirs(log_dir, exist_ok=True)
    
    security_handler = RotatingFileHandler(
        f"{log_dir}/{service_name}_security.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(security_formatter)
    logger.addHandler(security_handler)
    
    # File handler for all events
    all_handler = RotatingFileHandler(
        f"{log_dir}/{service_name}.log",
        maxBytes=50*1024*1024,  # 50MB
        backupCount=10
    )
    all_handler.setLevel(logging.INFO)
    all_handler.setFormatter(standard_formatter)
    logger.addHandler(all_handler)