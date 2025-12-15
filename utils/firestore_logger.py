"""Firestore logging utility for migration operations"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

# Get the standard logger
logger = logging.getLogger(__name__)

# Global Firestore client (will be set from server.py)
_firestore_client = None


def set_firestore_client(client):
    """Set the Firestore client to use for logging"""
    global _firestore_client
    _firestore_client = client


def log_to_firestore(
    message: str,
    level: str,
    operation_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log message to both console and Firestore database
    
    Args:
        message: Log message to store
        level: Log level (info, warning, error, success)
        operation_id: Unique ID for grouping logs from the same operation
        resource_type: Type of resource being migrated (e.g., 'app', 'proxy', 'kvm')
        resource_name: Name of the resource being migrated
        metadata: Additional metadata to store with the log
    """
    # Always log to console first
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message)
    
    # Try to log to Firestore if available
    if _firestore_client is not None:
        try:
            log_entry = {
                "message": message,
                "level": level.upper(),
                "timestamp": datetime.now(timezone.utc),
                "operation_id": operation_id,
                "resource_type": resource_type,
                "resource_name": resource_name,
                "metadata": metadata or {}
            }
            
            # Store in Firestore collection 'migration_logs'
            logs_ref = _firestore_client.collection('migration_logs')
            logs_ref.add(log_entry)
            
        except Exception as e:
            # Don't fail the operation if Firestore logging fails
            # Just log the error to console
            logger.warning(f"Failed to write log to Firestore: {str(e)}")


def log_info(
    message: str,
    operation_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Log info message to console and Firestore"""
    log_to_firestore(message, "info", operation_id, resource_type, resource_name, metadata)


def log_warning(
    message: str,
    operation_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Log warning message to console and Firestore"""
    log_to_firestore(message, "warning", operation_id, resource_type, resource_name, metadata)


def log_error(
    message: str,
    operation_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Log error message to console and Firestore"""
    log_to_firestore(message, "error", operation_id, resource_type, resource_name, metadata)


def log_success(
    message: str,
    operation_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Log success message to console and Firestore"""
    log_to_firestore(message, "info", operation_id, resource_type, resource_name, metadata)


def generate_operation_id() -> str:
    """Generate a unique operation ID for grouping logs"""
    return str(uuid.uuid4())

