from dataclasses import dataclass

from ..constants import BarcodeStatus


@dataclass
class BarcodeInfo:
    barcode: str
    model: str
    sanal_adet: str
    tesdetay_ref: str
    job_card_ref: str
    status: BarcodeStatus
