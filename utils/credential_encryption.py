"""Credential encryption utilities for storing sensitive data"""
import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Get encryption key from environment or generate a default (for development only)
ENCRYPTION_KEY = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "").strip()

def _get_encryption_key() -> bytes:
    """Get or generate encryption key"""
    if ENCRYPTION_KEY:
        # Use provided key (should be base64 encoded)
        try:
            return base64.urlsafe_b64decode(ENCRYPTION_KEY.encode())
        except:
            # If not base64, use it directly (less secure)
            key = ENCRYPTION_KEY.encode()
            # Pad or truncate to 32 bytes for Fernet
            if len(key) < 32:
                key = key.ljust(32, b'0')
            elif len(key) > 32:
                key = key[:32]
            return base64.urlsafe_b64encode(key)
    else:
        # Generate a default key for development (NOT SECURE FOR PRODUCTION)
        # In production, set CREDENTIAL_ENCRYPTION_KEY environment variable
        logger.warning("Using default encryption key. Set CREDENTIAL_ENCRYPTION_KEY for production!")
        default_key = b'default_key_for_development_only_32bytes!!'
        return base64.urlsafe_b64encode(default_key)

def encrypt_credential(credential: str) -> str:
    """
    Encrypt a credential string using Fernet symmetric encryption
    
    Args:
        credential: The credential string to encrypt
        
    Returns:
        Base64-encoded encrypted string
    """
    try:
        if not credential:
            return ""
        
        # Get encryption key
        key = _get_encryption_key()
        fernet = Fernet(key)
        
        # Encrypt the credential
        encrypted = fernet.encrypt(credential.encode())
        
        # Return as base64 string for easy storage
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {str(e)}")
        raise

def decrypt_credential(encrypted_credential: str) -> str:
    """
    Decrypt a credential string
    
    Args:
        encrypted_credential: Base64-encoded encrypted string
        
    Returns:
        Decrypted credential string
    """
    try:
        if not encrypted_credential:
            return ""
        
        # Get decryption key
        key = _get_encryption_key()
        fernet = Fernet(key)
        
        # Decode from base64
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_credential.encode())
        
        # Decrypt
        decrypted = fernet.decrypt(encrypted_bytes)
        
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Decryption failed: {str(e)}")
        raise

def mask_credential(credential: str, visible_chars: int = 4) -> str:
    """
    Mask a credential for display (shows first N characters, masks the rest)
    
    Args:
        credential: The credential to mask
        visible_chars: Number of characters to show at the start
        
    Returns:
        Masked credential string (e.g., "pass****")
    """
    if not credential:
        return "****"
    
    if len(credential) <= visible_chars:
        return "*" * len(credential)
    
    return credential[:visible_chars] + "*" * (len(credential) - visible_chars)

