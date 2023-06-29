"""Authentication class for KASA username / passwords."""
from hashlib import md5


class Auth:
    """Authentication for Kasa KLAP authentication."""

    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password
       