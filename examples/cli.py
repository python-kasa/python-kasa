import sys
import logging
from pprint import pformat as pf

from pyHS100 import SmartPlug

logging.basicConfig(level=logging.DEBUG)

if len(sys.argv) < 2:
    print("%s <ip>" % sys.argv[0])
    sys.exit(1)

hs = SmartPlug(sys.argv[1])

logging.info("Identify: %s", hs.identify())
logging.info("Sysinfo: %s", pf(hs.get_sysinfo()))
has_emeter = hs.has_emeter
if has_emeter:
    logging.info("== Emeter ==")
    logging.info("- Current: %s", hs.get_emeter_realtime())
    logging.info("== Monthly ==")
    logging.info(hs.get_emeter_monthly())
    logging.info("== Daily ==")
    logging.info(hs.get_emeter_daily(month=11, year=2016))
