from typing import Optional, TypedDict

from ..barcode_reader.models.quality_data import QualityData


class GlassOperationRequest(TypedDict):
    operation: str
    employee: str
    glass_name: str
    quality_data: Optional[QualityData]
