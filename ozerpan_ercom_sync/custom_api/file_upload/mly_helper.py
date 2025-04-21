OPERATION_TYPES = {
    "ACILI": "ACILI",
    "SURME": "SURME",
    "KEMERLI": "KEMERLI",
    "NORMAL": "NORMAL",
}

MIDDLE_OPERATIONS = {
    "NORMAL": {
        "KASA": ["Kaynak Köşe Temizleme"],
        "KASA_KANAT": ["Kaynak Köşe Temizleme", "Kanat Hazırlık", "Kanat Bağlama"],
        "KASA_KAYIT": ["Kaynak Köşe Temizleme", "Orta Kayıt"],
        "KASA_KAYIT_KANAT": [
            "Kaynak Köşe Temizleme",
            "Orta Kayıt",
            "Kanat Hazırlık",
            "Kanat Bağlama",
        ],
        "KANAT": ["Kaynak Köşe Temizleme", "Kanat Hazırlık"],
        "KAYIT": ["Kaynak Köşe Temizleme", "Orta Kayıt"],
        "KAYIT_KANAT": [
            "Kaynak Köşe Temizleme",
            "Orta Kayıt",
            "Kanat Hazırlık",
            "Kanat Bağlama",
        ],
    },
    "ACILI": {
        "KASA": ["Sürme Hazırlık"],
        "KASA_KANAT": ["Sürme Hazırlık", "Kanat Hazırlık", "Kanat Bağlama"],
        "KASA_KAYIT": ["Sürme Hazırlık", "Orta Kayıt"],
        "KASA_KAYIT_KANAT": [
            "Sürme Hazırlık",
            "Orta Kayıt",
            "Kanat Hazırlık",
            "Kanat Bağlama",
        ],
        "KANAT": ["Sürme Hazırlık", "Kanat Hazırlık"],
    },
    "SURME": {
        "KASA_KAYIT_KANAT": [
            "Kaynak Köşe Temizleme",
            "Sürme Hazırlık",
            "Sürme Bağlama",
            "Orta Kayıt",
        ],
        "KASA_KANAT": [
            "Kaynak Köşe Temizleme",
            "Sürme Hazırlık",
            "Sürme Bağlama",
        ],
    },
}

ACILI_ITEMS = ["AÇILI KASA", "AÇILI KANAT", "AÇILI ORTAKAYIT"]
SURME_ITEMS = ["SÜRME KASA", "SÜRME KANAT", "SÜRME ORTAKAYIT"]
KEMERLI_ITEMS = ["KEMERLİ KASA", "KEMERLİ KANAT", "KEMERLİ ORTAKAYIT"]
NORMAL_ITEMS = ["KASA", "KANAT", "KAYIT"]


def define_operation_type(profile_group):
    if any(item in SURME_ITEMS for item in profile_group):
        return OPERATION_TYPES["SURME"]
    if any(item in ACILI_ITEMS for item in profile_group):
        return OPERATION_TYPES["ACILI"]
    if any(item in KEMERLI_ITEMS for item in profile_group):
        return OPERATION_TYPES["KEMERLI"]
    return OPERATION_TYPES["NORMAL"]


def get_middle_operations(profile_group):
    operation_type = define_operation_type(profile_group)
    profiles = []
    for profile in profile_group:
        if "KASA" in profile and "KASA" not in profiles:
            profiles.append("KASA")
        if "KAYIT" in profile and "KAYIT" not in profiles:
            profiles.append("KAYIT")
        if "KANAT" in profile and "KANAT" not in profiles:
            profiles.append("KANAT")

    if "KASA" in profiles and "KAYIT" in profiles and "KANAT" in profiles:
        return MIDDLE_OPERATIONS[operation_type]["KASA_KAYIT_KANAT"]
    elif "KASA" in profiles and "KAYIT" in profiles:
        return MIDDLE_OPERATIONS[operation_type]["KASA_KAYIT"]
    elif "KASA" in profiles and "KANAT" in profiles:
        return MIDDLE_OPERATIONS[operation_type]["KASA_KANAT"]
    elif "KASA" in profiles:
        return MIDDLE_OPERATIONS[operation_type]["KASA"]
    elif "KANAT" in profiles:
        return MIDDLE_OPERATIONS[operation_type]["KANAT"]
    elif "KAYIT" in profiles:
        return MIDDLE_OPERATIONS[operation_type]["KAYIT"]
    elif "KAYIT_KANAT" in profiles:
        return MIDDLE_OPERATIONS[operation_type]["KAYIT_KANAT"]
