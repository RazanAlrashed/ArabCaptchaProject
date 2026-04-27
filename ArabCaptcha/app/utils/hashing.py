"""
utils/hashing.py

Simple hashing utilities for API keys.
We store only the hash, never the raw key.
"""
import hashlib


def hash_api_key(raw_key: str) -> str:
    """Return a SHA-256 hex digest of the given API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Check whether a raw key matches a stored hash."""
    return hash_api_key(raw_key) == stored_hash
