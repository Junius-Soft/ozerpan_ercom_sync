from enum import Enum


class BarcodeStatus(Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    IN_CORRECTION = "In Correction"
    COMPLETED = "Completed"


class OperationType(Enum):
    KAYNAK_KOSE = "Kaynak Köşe Temizleme"
    ORTA_KAYIT = "Orta Kayıt"
    KANAT_HAZIRLIK = "Kanat Hazırlık"
    KANAT_BAGLAMA = "Kanat Bağlama"
    CITA = "Çıta"
    KALITE = "Kalite"
