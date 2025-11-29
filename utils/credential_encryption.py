"""Utility for encrypting and decrypting sensitive credentials"""
import os
import base64
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)

# Use environment variable for encryption key, or generate a default one
# In production, this should be set via environment variable
_ENCRYPTION_KEY = os.environ.get("APIGEE_ENCRYPTION_KEY", None)


def _get_encryption_key() -> bytes:
    """Get or generate encryption key"""
    global _ENCRYPTION_KEY
    
    if _ENCRYPTION_KEY:
        # If provided as env var, use it directly (should be base64 encoded)
        try:
            return base64.urlsafe_b64decode(_ENCRYPTION_KEY.encode())
        except:
            # If not base64, derive from it
            pass
    
    # Generate a key from a default salt (NOT SECURE FOR PRODUCTION)
    # In production, use a proper key management system
    default_salt = b'apigee_migration_default_salt_change_in_production'
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=default_salt,
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(b'default_key_change_in_production'))
    return key


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt a credential string.
    
    Args:
        plaintext: The plaintext credential to encrypt
        
    Returns:
        Base64-encoded encrypted string
    """
    try:
        key = _get_encryption_key()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {str(e)}")
        # Fallback: return masked value (not encrypted, but at least not plaintext)
        return f"***MASKED_{len(plaintext)}_CHARS***"


def decrypt_credential(encrypted_text: str) -> Optional[str]:
    """
    Decrypt a credential string.
    
    Args:
        encrypted_text: The base64-encoded encrypted string
        
    Returns:
        Decrypted plaintext, or None if decryption fails
    """
    try:
        # Check if it's a masked value (fallback)
        if encrypted_text.startswith("***MASKED_"):
            logger.warning("Attempted to decrypt a masked value - encryption key may have changed")
            return None
            
        key = _get_encryption_key()
        fernet = Fernet(key)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_text.encode())
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Decryption failed: {str(e)}")
        return None


def mask_credential(credential: str, show_chars: int = 4) -> str:
    """
    Mask a credential for display purposes (non-reversible).
    
    Args:
        credential: The credential to mask
        show_chars: Number of characters to show at the start
        
    Returns:
        Masked string (e.g., "pass****")
    """
    if not credential or len(credential) <= show_chars:
        return "****"
    return credential[:show_chars] + "*" * (len(credential) - show_chars)

