from .protocol import TPLinkSmartHomeProtocol, TPLinkProtocol
from .klapprotocol import TPLinkKlap
from typing import List


class TPLinkProtocolConfig:
    @staticmethod
    def enabled_protocols() -> List[TPLinkProtocol]:
        return [TPLinkSmartHomeProtocol, TPLinkKlap]
