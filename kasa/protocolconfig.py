
from .protocol import TPLinkSmartHomeProtocol, TPLinkProtocol
from .klapprotocol import TPLinkKLAP
from typing import List

class TPLinkProtocolConfig:

    @staticmethod
    def enabled_protocols() -> List[TPLinkProtocol]:
        return [TPLinkSmartHomeProtocol, TPLinkKLAP]
    
    