"""Authentication class for username / passwords."""


class AuthCredentials:
    """Authentication credentials for Kasa authentication."""

    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password
