from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import frappe


DIM_NDIGITS = 3

"""
Bu yapımız
console da siparişlerin planlı yada planlanmamış cam listelerini görüntülemek için kullanılır.

bench --site ozerpan.localhost execute ozerpan_ercom_sync.custom_api.api.debug_cam_liste_totals_for_order --kwargs "{'order_no': 'S600149'}"
"""
@dataclass(frozen=True)
class CamKey:
    """
    Business key for matching Excel rows vs DB CamListe rows.

    IMPORTANT: CamListe naming/autoname is not stable; we match by these fields.
    """

    poz_no: int
    stok_kodu: str
    sanal_adet: int
    genislik: float
    yukseklik: float
    bm2: float
    tm2: float


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_stock_code(value: Any) -> str:
    """
    Mirrors GlassListProcessor._clean_stock_code():
    - remove '#'
    - strip
    - uppercase
    """

    if value is None:
        return ""
    return str(value).replace("#", "").strip().upper()


def normalize_sanal_adet(value: Any) -> int:
    """
    CamListe.sanal_adet is created as f"{i+1}" in _process_record.
    It can still come from DB as string; split safety for values like "3/10".
    """

    if value is None:
        return 0
    s = str(value).strip()
    if not s:
        return 0
    try:
        return int(s.split("/")[0])
    except ValueError:
        return 0


def round_dims(value: Any, default: float = 0.0) -> float:
    return round(_to_float(value, default=default), DIM_NDIGITS)


def _detect_excel_columns(df: pd.DataFrame) -> Dict[str, str]:
    """
    Detect Excel column names by trying common Turkish variants.
    """

    cols = {c.strip().upper(): c for c in df.columns if isinstance(c, str)}

    def pick(*candidates: str) -> str:
        for cand in candidates:
            if cand.upper() in cols:
                return cols[cand.upper()]
        raise ValueError(
            "Could not detect required excel column(s). Missing one of: "
            + ", ".join(candidates)
        )

    return {
        "order_no": pick("SIPARISNO", "SIPARIS_NO"),
        "poz_no": pick("POZNO", "POZ_NO"),
        "stok_kodu": pick("STOKKODU", "KODU"),
        "adet": pick("ADET"),
        "genislik": pick("GEN", "GENISLIK"),
        "yukseklik": pick("YUK", "YUKSEKLIK"),
        "bm2": pick("BM2"),
        "tm2": pick("TM2"),
        "aciklama": pick("ACIKLAMA"),
    }


def read_cam_list_excel(
    excel_path: str, sheet_name: Optional[str] = None
) -> pd.DataFrame:
    xls = pd.ExcelFile(excel_path)
    if sheet_name is None:
        sheet_name = xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet_name)
    if df is None or df.empty:
        raise ValueError(f"Excel sheet is empty: {sheet_name}")
    return df


def build_expected_cam_keys(
    df: pd.DataFrame,
    order_no: str,
) -> Dict[CamKey, int]:
    """
    Expand each Excel row by ADET into sanal_adet = 1..ADET.
    """

    col_map = _detect_excel_columns(df)

    # Filter by requested order
    df = df.copy()
    df[col_map["order_no"]] = df[col_map["order_no"]].astype(str).str.strip()
    df = df[df[col_map["order_no"]] == str(order_no)]

    expected: Dict[CamKey, int] = {}
    for _, row in df.iterrows():
        poz_no = _to_int(row.get(col_map["poz_no"]), default=0)
        stok_kodu = normalize_stock_code(row.get(col_map["stok_kodu"]))
        adet = _to_int(row.get(col_map["adet"]), default=0)

        genislik = round_dims(row.get(col_map["genislik"]))
        yukseklik = round_dims(row.get(col_map["yukseklik"]))
        bm2 = round_dims(row.get(col_map["bm2"]))
        tm2 = round_dims(row.get(col_map["tm2"]))

        if not stok_kodu or poz_no == 0 or adet <= 0:
            continue

        # Excel ADET => DB has sanal_adet values 1..ADET
        for i in range(1, adet + 1):
            key = CamKey(
                poz_no=poz_no,
                stok_kodu=stok_kodu,
                sanal_adet=i,
                genislik=genislik,
                yukseklik=yukseklik,
                bm2=bm2,
                tm2=tm2,
            )
            expected[key] = expected.get(key, 0) + 1

    return expected


def fetch_actual_cam_planning_counts(
    order_no: str,
    operation: str = "Cam",
) -> Tuple[
    Dict[CamKey, int],
    Dict[CamKey, int],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    """
    Fetch DB CamListe rows and classify planned/unplanned using:
    - existence of `CamListe Job Card` row with (operation = operation)
    """

    # One row per CamListe doc (CamListe is parent), group join determines planned existence.
    rows = frappe.db.sql(
        """
        SELECT
            cl.name,
            cl.order_no,
            cl.stok_kodu,
            cl.poz_no,
            cl.sanal_adet,
            cl.genislik,
            cl.yukseklik,
            cl.bm2,
            cl.tm2,
            MAX(CASE WHEN jc.name IS NOT NULL THEN 1 ELSE 0 END) AS is_planned,
            GROUP_CONCAT(DISTINCT jc.status ORDER BY jc.status SEPARATOR ',') AS planned_statuses,
            GROUP_CONCAT(DISTINCT jc.job_card_ref ORDER BY jc.job_card_ref SEPARATOR ',') AS planned_job_cards
        FROM `tabCamListe` cl
        LEFT JOIN `tabCamListe Job Card` jc
            ON jc.parent = cl.name
            AND jc.operation = %s
        WHERE cl.order_no = %s
        GROUP BY
            cl.name,
            cl.order_no,
            cl.stok_kodu,
            cl.poz_no,
            cl.sanal_adet,
            cl.genislik,
            cl.yukseklik,
            cl.bm2,
            cl.tm2
        """,
        (operation, order_no),
        as_dict=True,
    )

    total_counts: Dict[CamKey, int] = {}
    planned_counts: Dict[CamKey, int] = {}

    planned_rows_sample: List[Dict[str, Any]] = []
    unplanned_rows_sample: List[Dict[str, Any]] = []

    for r in rows:
        poz_no = _to_int(r.get("poz_no"), default=0)
        stok_kodu = normalize_stock_code(r.get("stok_kodu"))
        sanal_adet = normalize_sanal_adet(r.get("sanal_adet"))

        genislik = round_dims(r.get("genislik"))
        yukseklik = round_dims(r.get("yukseklik"))
        bm2 = round_dims(r.get("bm2"))
        tm2 = round_dims(r.get("tm2"))

        if not stok_kodu or poz_no == 0 or sanal_adet == 0:
            continue

        key = CamKey(
            poz_no=poz_no,
            stok_kodu=stok_kodu,
            sanal_adet=sanal_adet,
            genislik=genislik,
            yukseklik=yukseklik,
            bm2=bm2,
            tm2=tm2,
        )

        total_counts[key] = total_counts.get(key, 0) + 1

        is_planned = bool(r.get("is_planned"))
        if is_planned:
            planned_counts[key] = planned_counts.get(key, 0) + 1
            if len(planned_rows_sample) < 50:
                planned_rows_sample.append(
                    {
                        "cam_name": r.get("name"),
                        "poz_no": poz_no,
                        "stok_kodu": stok_kodu,
                        "sanal_adet": sanal_adet,
                        "status_samples": r.get("planned_statuses"),
                        "job_cards_samples": r.get("planned_job_cards"),
                    }
                )
        else:
            if len(unplanned_rows_sample) < 50:
                unplanned_rows_sample.append(
                    {
                        "cam_name": r.get("name"),
                        "poz_no": poz_no,
                        "stok_kodu": stok_kodu,
                        "sanal_adet": sanal_adet,
                    }
                )

    return total_counts, planned_counts, planned_rows_sample, unplanned_rows_sample


def print_cam_db_planning_summary(order_no: str, operation: str = "Cam") -> Dict[str, Any]:
    (
        actual_total_counts,
        actual_planned_counts,
        planned_rows_sample,
        unplanned_rows_sample,
    ) = fetch_actual_cam_planning_counts(order_no=order_no, operation=operation)

    actual_total = sum(actual_total_counts.values())
    actual_planned_total = sum(actual_planned_counts.values())
    actual_unplanned_total = actual_total - actual_planned_total

    # Derive unplanned key counts (total - planned)
    actual_unplanned_counts: Dict[CamKey, int] = {}
    for key, total_cnt in actual_total_counts.items():
        planned_cnt = actual_planned_counts.get(key, 0)
        unplanned_cnt = total_cnt - planned_cnt
        if unplanned_cnt > 0:
            actual_unplanned_counts[key] = unplanned_cnt

    # Aggregate by (poz_no, stok_kodu, bm2, tm2) => "adet" for planned/unplanned.
    def _agg_by_bm2_tm2(counts: Dict[CamKey, int]) -> Dict[Tuple[int, str, float, float], int]:
        agg: Dict[Tuple[int, str, float, float], int] = {}
        for key, cnt in counts.items():
            combo_key = (key.poz_no, key.stok_kodu, key.bm2, key.tm2)
            agg[combo_key] = agg.get(combo_key, 0) + cnt
        return agg

    planned_combo_counts = _agg_by_bm2_tm2(actual_planned_counts)
    unplanned_combo_counts = _agg_by_bm2_tm2(actual_unplanned_counts)

    print("\n--- DB Cam Liste Planning Summary ---")
    print(f"order_no: {order_no}")
    print(f"operation: {operation}")
    print(f"DB total CamListe count:     {actual_total}")
    print(f"DB planned (job-card) count: {actual_planned_total}")
    print(f"DB unplanned count:           {actual_unplanned_total}")

    print("\n--- Planned breakdown by BM2/TM2 ---")
    if planned_combo_counts:
        for (poz_no, stok_kodu, bm2, tm2), cnt in sorted(
            planned_combo_counts.items(),
            key=lambda x: (-x[1], x[0][0], x[0][1], x[0][2], x[0][3]),
        )[:50]:
            print(f"poz={poz_no} stok={stok_kodu} bm2={bm2} tm2={tm2} adet={cnt}")
    else:
        print("(none)")

    print("\n--- Unplanned breakdown by BM2/TM2 ---")
    if unplanned_combo_counts:
        for (poz_no, stok_kodu, bm2, tm2), cnt in sorted(
            unplanned_combo_counts.items(),
            key=lambda x: (-x[1], x[0][0], x[0][1], x[0][2], x[0][3]),
        )[:50]:
            print(f"poz={poz_no} stok={stok_kodu} bm2={bm2} tm2={tm2} adet={cnt}")
    else:
        print("(none)")

    print("--- End Summary ---\n")

    return {
        "order_no": order_no,
        "actual_total": actual_total,
        "actual_planned_total": actual_planned_total,
        "actual_unplanned_total": actual_unplanned_total,
        "planned_combo_counts": [
            {
                "poz_no": poz_no,
                "stok_kodu": stok_kodu,
                "bm2": bm2,
                "tm2": tm2,
                "adet": cnt,
            }
            for (poz_no, stok_kodu, bm2, tm2), cnt in sorted(
                planned_combo_counts.items(),
                key=lambda x: (-x[1], x[0][0], x[0][1], x[0][2], x[0][3]),
            )
        ],
        "unplanned_combo_counts": [
            {
                "poz_no": poz_no,
                "stok_kodu": stok_kodu,
                "bm2": bm2,
                "tm2": tm2,
                "adet": cnt,
            }
            for (poz_no, stok_kodu, bm2, tm2), cnt in sorted(
                unplanned_combo_counts.items(),
                key=lambda x: (-x[1], x[0][0], x[0][1], x[0][2], x[0][3]),
            )
        ],
        "planned_rows_sample": planned_rows_sample,
        "unplanned_rows_sample": unplanned_rows_sample,
    }


def print_cam_list_planning_diff(
    order_no: str,
    excel_path: str,
    excel_sheet_name: Optional[str] = None,
    operation: str = "Cam",
) -> Dict[str, Any]:
    """
    Excel Cam Liste (expected) vs DB CamListe (+ planned/unplanned via CamListe Job Card).
    """

    print("\n--- Cam Liste Planning Compare (START) ---")
    print(f"order_no: {order_no}")
    print(f"excel_path: {excel_path}")
    print(f"operation: {operation}")

    df = read_cam_list_excel(excel_path, sheet_name=excel_sheet_name)
    expected_counts = build_expected_cam_keys(df=df, order_no=order_no)

    (
        actual_total_counts,
        actual_planned_counts,
        planned_rows_sample,
        unplanned_rows_sample,
    ) = fetch_actual_cam_planning_counts(order_no=order_no, operation=operation)

    expected_total = sum(expected_counts.values())
    actual_total = sum(actual_total_counts.values())
    actual_planned_total = sum(actual_planned_counts.values())
    actual_unplanned_total = actual_total - actual_planned_total

    print("--- Summary ---")
    print(f"Excel expected glass count: {expected_total}")
    print(f"DB total CamListe count:     {actual_total}")
    print(f"DB planned (job-card) count: {actual_planned_total}")
    print(f"DB unplanned count:           {actual_unplanned_total}")

    mismatches: List[Dict[str, Any]] = []
    all_keys = set(expected_counts.keys()) | set(actual_total_counts.keys())
    for key in all_keys:
        exp = expected_counts.get(key, 0)
        act = actual_total_counts.get(key, 0)
        if exp != act:
            mismatches.append(
                {
                    "poz_no": key.poz_no,
                    "stok_kodu": key.stok_kodu,
                    "sanal_adet": key.sanal_adet,
                    "genislik": key.genislik,
                    "yukseklik": key.yukseklik,
                    "bm2": key.bm2,
                    "tm2": key.tm2,
                    "expected_count": exp,
                    "actual_count": act,
                }
            )

    print("--- Expected vs Actual (key-level) ---")
    print(f"Mismatched keys (count !=): {len(mismatches)}")
    if mismatches:
        print("First 10 mismatches:")
        for m in mismatches[:10]:
            print(
                f"  poz_no={m['poz_no']} stok={m['stok_kodu']} sanal={m['sanal_adet']} "
                f"exp={m['expected_count']} act={m['actual_count']} "
                f"dims=({m['genislik']},{m['yukseklik']},{m['bm2']},{m['tm2']})"
            )

    print("--- Planned sample ---")
    for r in planned_rows_sample:
        print(
            f"  Cam={r['cam_name']} poz={r['poz_no']} stok={r['stok_kodu']} "
            f"sanal={r['sanal_adet']} status={r.get('status_samples')}"
        )

    print("--- Unplanned sample ---")
    for r in unplanned_rows_sample:
        print(
            f"  Cam={r['cam_name']} poz={r['poz_no']} stok={r['stok_kodu']} "
            f"sanal={r['sanal_adet']}"
        )

    print("--- Cam Liste Planning Compare (END) ---\n")

    return {
        "order_no": order_no,
        "expected_total": expected_total,
        "actual_total": actual_total,
        "actual_planned_total": actual_planned_total,
        "actual_unplanned_total": actual_unplanned_total,
        "mismatch_count": len(mismatches),
        "mismatches_first_10": mismatches[:10],
    }


def test_cam_list_planning_compare(
    order_no: str,
    excel_path: str,
    excel_sheet_name: Optional[str] = None,
    operation: str = "Cam",
) -> None:
    try:
        diff = print_cam_list_planning_diff(
            order_no=order_no,
            excel_path=excel_path,
            excel_sheet_name=excel_sheet_name,
            operation=operation,
        )
        print(f"[OK] Test finished. mismatch_count={diff['mismatch_count']}")
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        raise


def get_loaded_sales_orders_for_cam(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Return Sales Orders where required CAM excel files have been uploaded.
    """

    orders = frappe.db.get_all(
        "Sales Order",
        filters={
            "custom_has_glass_item": 1,
            "custom_mly_list_uploaded": 1,
            "custom_price_list_uploaded": 1,
            "custom_glass_list_uploaded": 1,
        },
        fields=["name", "custom_ercom_order_no"],
        limit_page_length=limit,
    )
    return [o for o in orders if o.get("custom_ercom_order_no")]


def test_cam_planning_db_only(order_no: str, operation: str = "Cam") -> None:
    try:
        print_cam_db_planning_summary(order_no=order_no, operation=operation)
        print("[OK] DB-only summary printed.")
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        raise


def test_cam_planning_for_loaded_orders(
    excel_path: str,
    excel_sheet_name: Optional[str] = None,
    operation: str = "Cam",
    limit: int = 50,
) -> None:
    """
    Iterate through system loaded orders and compare each against the same Excel file.
    (Excel can contain multiple orders; expected matching is filtered by order_no.)
    """

    loaded_orders = get_loaded_sales_orders_for_cam(limit=limit)
    if not loaded_orders:
        print("[WARN] No loaded Sales Orders found for CAM flags.")
        return

    print(f"[INFO] Loaded orders for CAM: {len(loaded_orders)}")
    for o in loaded_orders:
        order_no = o.get("custom_ercom_order_no")
        print(f"\n\n[INFO] Comparing order_no={order_no}")
        test_cam_list_planning_compare(
            order_no=order_no,
            excel_path=excel_path,
            excel_sheet_name=excel_sheet_name,
            operation=operation,
        )

