"""Authentication class for KASA username / passwords."""
from hashlib import md5


class Auth:
    """Authentication for Kasa KLAP authentication."""

    def __init__(self, user: str = "", password: str = ""):
        self.user = user
        self.password = password
        self.md5user = md5(user.encode()).digest()
        self.md5password = md5(password.encode()).digest()
        self.md5auth = md5(self.md5user + self.md5password).digest()

    def authenticator(self):
        """Return the KLAP authenticator for these credentials."""
        return self.md5auth

    def owner(self):
        """Return the MD5 hash of the username in this object."""
        return self.md5user
