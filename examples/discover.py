import logging
from pprint import pprint as pp

from pyHS100 import TPLinkSmartHomeProtocol
logging.basicConfig(level=logging.DEBUG)

for dev in TPLinkSmartHomeProtocol.discover():
    print("Found device!")
    pp(dev)
