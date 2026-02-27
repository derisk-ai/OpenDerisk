from enum import Enum


class OpenRcaScene(str, Enum):
    BANK = "bank"
    TELECOM = "telecom"
    MARKET = "market"