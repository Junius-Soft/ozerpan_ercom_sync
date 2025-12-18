from enum import Enum


class MarketOrderOperation(str,Enum):
    Panjur = "Panjur"
    Sineklik = "Sineklik"
    Kepenk = "Kepenk"
    Cam_Balkon = "Cam Balkon"