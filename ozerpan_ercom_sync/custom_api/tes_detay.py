import frappe
from frappe import _

from ozerpan_ercom_sync.custom_api.utils import (
    generate_logger,
    get_machine_name,
    show_progress,
)
from ozerpan_ercom_sync.db_pool import DatabaseConnectionPool


@frappe.whitelist()
def sync_tes_detay(order_no=None, opti_no=None):
    print("-- Sync TesDetay -- ")
    logger_dict = generate_logger("tesdetay_sync")
    logger = logger_dict["logger"]

    try:
        logger.info("Starting synchronizing TesDetay.")
        pool = DatabaseConnectionPool()
        logger.info("Connection pool is initializing.")
        data = get_tesdetay_data(pool, order_no, opti_no)
        data_len = len(data)

        def _cleanup_tesdetays(order_no=None, opti_no=None):
            filters = {}
            if order_no:
                filters["siparis_no"] = order_no
            if opti_no:
                filters["oto_no"] = opti_no

            frappe.db.delete("TesDetay", filters)
            return

        if order_no or opti_no:
            _cleanup_tesdetays(order_no, opti_no)

        values = []
        for i, row in enumerate(data):
            show_progress(
                curr_count=i + 1,
                max_count=data_len,
                title="Updating TesDetay",
                desc=_("Syncing TesDetay {0} of {1}").format(i + 1, data_len),
            )

            barcode = generate_barcode(
                araba_no=row.get("ARABANO"),
                eksen=row.get("EKSEN"),
                model=row.get("MODEL"),
                olcu=row.get("OLCU"),
                rc=row.get("RC"),
                stok_kodu=row.get("STOKKODU"),
                yer_no=row.get("YERNO"),
            )

            machine_name = get_machine_name(row.get("MAKINA"))

            now = frappe.utils.now()
            doc_name = row.get("SAYAC") or frappe.generate_hash()
            current_user = frappe.session.user

            values.append(
                (
                    doc_name,  # name
                    current_user,  # owner
                    now,  # creation
                    now,  # modified
                    current_user,  # modified_by
                    0,  # docstatus
                    row.get("OTONO") or 0,  # oto_no
                    row.get("SIPARISNO") or "",  # siparis_no
                    row.get("CARIKOD") or "",  # cari_kod
                    row.get("POZNO") or 0,  # poz_no
                    row.get("STOKKODU") or "",  # stok_kodu
                    row.get("MODEL") or "",  # model
                    row.get("OLCU") or 0,  # olcu
                    row.get("POZISYON") or "",  # pozisyon
                    row.get("ACI1") or 0,  # aci1
                    row.get("ACI2") or 0,  # aci2
                    row.get("ADET") or 0,  # adet
                    row.get("ERCOM") or "",  # ercom
                    row.get("SAYAC") or 0,  # sayac
                    row.get("MONTAJYERI") or "",  # montaj_yeri
                    row.get("KASANO") or "",  # kasa_no
                    row.get("YERNO") or 0,  # yer_no
                    row.get("KANATNO") or 0,  # kanat_no
                    row.get("ARABANO") or 0,  # araba_no
                    row.get("RC") or "",  # rc
                    row.get("PROGRAMNO") or 0,  # program_no
                    row.get("ISLEM") or 0,  # islem
                    row.get("BAYIADI") or "",  # bayi_adi
                    row.get("EKSEN") or 0,  # eksen
                    row.get("YUKSEKLIK") or 0,  # yukseklik
                    row.get("SOLIC") or 0,  # sol_ic
                    row.get("SAGIC") or 0,  # sag_ic
                    row.get("ORTA") or 0,  # orta
                    row.get("DAKAPI") or 0,  # da_kapi
                    row.get("DSKODU") or "",  # ds_kodu
                    row.get("DSBOYU") or 0,  # ds_boyu
                    row.get("PROFILTIPI") or 0,  # profil_tipi
                    row.get("HESAPKODU") or "",  # hesap_kodu
                    row.get("ESIKSIZ") or 0,  # esiksiz
                    row.get("WC") or 0,  # wc
                    row.get("KANATINDEX") or 0,  # kanat_index
                    row.get("SANALADET") or 0,  # sanal_adet
                    row.get("ACIKLAMA") or "",  # aciklama
                    row.get("URETIMSAYAC") or 0,  # uretim_sayac
                    row.get("MUSTERISI") or "",  # musteri
                    machine_name,  # makina_no
                    barcode,  # barkod
                )
            )

        if values:
            sql = """
                INSERT IGNORE INTO `tabTesDetay` (
                    name, owner, creation, modified, modified_by, docstatus,
                    oto_no, siparis_no, cari_kod, poz_no, stok_kodu, model, olcu,
                    pozisyon, aci1, aci2, adet, ercom, sayac, montaj_yeri, kasa_no,
                    yer_no, kanat_no, araba_no, rc, program_no, islem, bayi_adi,
                    eksen, yukseklik, sol_ic, sag_ic, orta, da_kapi, ds_kodu,
                    ds_boyu, profil_tipi, hesap_kodu, esiksiz, wc, kanat_index,
                    sanal_adet, aciklama, uretim_sayac, musteri, makina_no, barkod
                )
                VALUES %s
            """

            # Convert the values list into a string of SQL value placeholders
            placeholders = ", ".join(
                ["(" + ", ".join(["%s"] * len(values[0])) + ")" for _ in values]
            )

            # Insert the placeholders into the SQL query
            sql = sql % placeholders

            # Execute the query with flattened values
            frappe.db.sql(sql, [val for tup in values for val in tup])
            frappe.db.commit()

        return {
            "status": "ok",
            "message": _("TesDetay synchronized successfully."),
            "inserted_doc_count": data_len,
        }

    except (frappe.ValidationError, Exception) as e:
        error_message = f"Error during sync: {str(e)}"
        logger.error(error_message)
        frappe.throw(error_message)
    finally:
        pool.close_all()
        logger.info("Connection pool is closed.")


def get_tesdetay_data(pool, order_no=None, opti_no=None):
    print("\n\n\n---Get Tesdetay Data---")

    query = """
        SELECT MIN(td.SAYAC) as SAYAC, td.OTONO, td.SIPARISNO, td.CARIKOD,
               td.POZNO, td.STOKKODU, td.MODEL, td.OLCU, td.POZISYON,
               td.ACI1, td.ACI2, td.ADET, td.ERCOM, td.MONTAJYERI,
               td.KASANO, td.YERNO, td.KANATNO, td.ARABANO, td.RC,
               td.PROGRAMNO, td.ISLEM, td.BAYIADI, td.EKSEN, td.YUKSEKLIK,
               td.SOLIC, td.SAGIC, td.ORTA, td.DAKAPI, td.DSKODU,
               td.DSBOYU, td.PROFILTIPI, td.HESAPKODU, td.ESIKSIZ,
               td.WC, td.KANATINDEX, td.SANALADET, td.ACIKLAMA,
               td.URETIMSAYAC, td.MAKINANO, t.*, s.MUSTERISI
        FROM dbtesdetay td
        LEFT JOIN dbtes t ON td.OTONO = t.OTONO
        LEFT JOIN dbsiparis s ON td.SIPARISNO = s.SIPARISNO
        WHERE td.SIPARISNO = %(order_no)s
        AND td.OTONO = %(opti_no)s
        GROUP BY td.ARABANO, td.MODEL, td.EKSEN, td.OLCU, td.STOKKODU,
                td.RC, td.YERNO, td.POZISYON, td.OTONO, td.POZNO,
                td.SANALADET, td.URETIMSAYAC
    """

    results = pool.execute_query(query, {"order_no": order_no, "opti_no": opti_no})
    return results


def generate_barcode(araba_no, yer_no, stok_kodu, rc, model, olcu, eksen):
    ADJUSTMENT = 6
    MODELS_WITH_ADJUSTMENT = {"KANAT", "KASA"}
    PAD_LENGTH = 2
    MEASUREMENT_LENGTH = 4

    def pad_value(value, length=PAD_LENGTH, leading_zero=False):
        value_str = str(value)
        if len(value_str) < length:
            return ("0" + value_str) if leading_zero else (value_str + "0")
        return value_str

    def process_measurement(value):
        if value is None:
            return 0
        adjustment = ADJUSTMENT if model in MODELS_WITH_ADJUSTMENT else 0
        return max(0, value - adjustment)

    # Format input values
    araba_no_padded = pad_value(araba_no)
    yer_no_padded = pad_value(yer_no, leading_zero=True)

    # Process and format measurements
    olcu_processed = str(int(process_measurement(olcu))).rjust(MEASUREMENT_LENGTH, "0")
    eksen_processed = str(int(process_measurement(eksen))).rjust(MEASUREMENT_LENGTH, "0")

    spacing = " " * 7 if len(stok_kodu) == 5 else " " * 3

    return f"K{araba_no_padded}{yer_no_padded}{stok_kodu}{spacing}{rc}{olcu_processed}00{eksen_processed}00"
