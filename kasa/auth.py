"""Authentication class for username / passwords."""
from kasa.protocol import TPLinkProtocol

class AuthCredentials:
    """Authentication credentials for Kasa authentication."""

    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password

class TPLinkAuthProtocol(TPLinkProtocol):
    """Base class for authenticating protocol"""
    def __init__(self, host: str, port:str, auth_credentials: AuthCredentials = AuthCredentials()):
        super().__init__(host=host, port=port)
        if auth_credentials is None:
            self.auth_credentials = AuthCredentials()
        else:    
            self.auth_credentials = auth_credentials
        self._authentication_failed = False

    @property
    def authentication_failed(self):
        """Will be true if authentication negotiated but failed, false otherwise"""
        return self._authentication_failed
    
    @authentication_failed.setter
    def authentication_failed(self, value):
        self._authentication_failed = value

