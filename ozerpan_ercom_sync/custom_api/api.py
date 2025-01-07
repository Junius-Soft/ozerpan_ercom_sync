import frappe

from ozerpan_ercom_sync.utils import get_mysql_connection


@frappe.whitelist()
def getData(barcode):
    print("\n\n\n")
    td = frappe.get_doc("TesDetay", {"barkod": barcode})
    print(td.siparis_no)
    print(td.poz_no)
    print(f"expected model: {td.model}")
    data = get_data(td.siparis_no, td.poz_no)
    for row in data:
        print(f"Row data: {row}")

    print("\n\n\n")


def get_data(order_no, poz_no):
    with get_mysql_connection() as connection:
        with connection.cursor() as cursor:
            query = """
                SELECT SAYAC, POZNO, MODEL
                FROM dbtesdetay
                WHERE SIPARISNO = %s
                ORDER BY POZNO ASC
            """
            cursor.execute(query, (order_no,))
            data = cursor.fetchall()
            return data
