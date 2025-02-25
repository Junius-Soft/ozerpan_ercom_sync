from dataclasses import dataclass

from ozerpan_ercom_sync.custom_api.barcode_reader.models.quality_data import QualityData

from ..constants import BarcodeStatus


@dataclass
class BarcodeInfo:
    barcode: str
    model: str
    sanal_adet: str
    tesdetay_ref: str
    job_card_ref: str
    status: BarcodeStatus
    quality_data: QualityData
