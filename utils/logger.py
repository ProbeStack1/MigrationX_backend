"""Logging utilities for migration operations"""
import logging
from typing import List
from datetime import datetime, timezone


class MigrationLogger:
    """Custom logger for migration operations with in-memory storage"""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.logs: List[str] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
        # Set up standard logger
        self.logger = logging.getLogger(f"migration.{job_id}")
        self.logger.setLevel(logging.INFO)
        
        # Add handler if not already present
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _add_timestamp(self, message: str) -> str:
        """Add timestamp to log message"""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] {message}"
    
    def info(self, message: str):
        """Log info message"""
        log_msg = self._add_timestamp(f"INFO: {message}")
        self.logs.append(log_msg)
        self.logger.info(message)
    
    def error(self, message: str):
        """Log error message"""
        log_msg = self._add_timestamp(f"ERROR: {message}")
        self.errors.append(log_msg)
        self.logs.append(log_msg)
        self.logger.error(message)
    
    def warning(self, message: str):
        """Log warning message"""
        log_msg = self._add_timestamp(f"WARNING: {message}")
        self.warnings.append(log_msg)
        self.logs.append(log_msg)
        self.logger.warning(message)
    
    def success(self, message: str):
        """Log success message"""
        log_msg = self._add_timestamp(f"SUCCESS: {message}")
        self.logs.append(log_msg)
        self.logger.info(f"✓ {message}")
    
    def get_logs(self) -> List[str]:
        """Get all logs"""
        return self.logs
    
    def get_errors(self) -> List[str]:
        """Get all errors"""
        return self.errors
    
    def get_warnings(self) -> List[str]:
        """Get all warnings"""
        return self.warnings
