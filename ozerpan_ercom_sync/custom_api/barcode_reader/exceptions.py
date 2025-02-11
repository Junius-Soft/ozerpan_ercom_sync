from typing import Dict, Optional


class BarcodeError(Exception):
    """Base exception for barcode operations"""

    pass


class InvalidBarcodeError(BarcodeError):
    """Raised when barcode is invalid"""

    pass


class BarcodeStateError(BarcodeError):
    """Raised when barcode state transition is invalid"""

    pass


class QualityControlError(Exception):
    def __init__(self, message: str, error_type: str, data: Optional[Dict] = None):
        self.message = message
        self.error_type = error_type
        self.data = data or {}
        super().__init__(message)
