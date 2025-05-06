import datetime
from collections import defaultdict
from typing import Dict, List

import frappe
from frappe import _


def on_update(doc, method):
    print("\n\n-- Production Plan Before Save -- (Start)")

    # Cleanup old capacity documents
    capacity_docs = frappe.get_all("Capacity", filters={"production_plan_ref": doc.name})
    for capacity_doc in capacity_docs:
        frappe.delete_doc("Capacity", capacity_doc.name)

    processed_dates = _create_capacity_docs(production_plan_doc=doc)

    print("Processed Dates:", processed_dates)
    print("Type:", type(processed_dates[0]))

    result = _calculate_capacity(processed_dates)

    frappe.msgprint(
        title=_("Warning"),
        msg=result,
        wide=True,
        as_list=True,
        is_minimizable=True,
    )

    print("-- Production Plan Before Save -- (End)\n\n")


def _calculate_capacity(processed_dates: List[datetime.date]) -> List[str]:
    capacity_docs = frappe.get_all(
        "Capacity",
        filters={"date": ["in", processed_dates]},
        fields=["name", "date"],
    )

    if not capacity_docs:
        print("Capacity docs not found.")
        return

    capacity_names = [doc["name"] for doc in capacity_docs]
    child_rows = frappe.get_all(
        "Capacity Plan Item",
        filters={
            "parent": ["in", capacity_names],
            "parenttype": "Capacity",
        },
        fields=["parent", "workstation", "used_duration", "daily_max_duration"],
    )

    # (date, workstation) -> [used_durations], [daily_max_durations]
    usage_map = defaultdict(lambda: {"used_total": 0, "max_allowed": 0})
    usage_summary = []

    for row in child_rows:
        parent_date = next(
            doc["date"] for doc in capacity_docs if doc["name"] == row["parent"]
        )
        key = (parent_date, row["workstation"])

        usage_map[key]["used_total"] += row["used_duration"] or 0
        usage_map[key]["max_allowed"] = row["daily_max_duration"] or 0

    print("\n🚦 Daily Capacity Usage Summary:\n")
    for (date, workstation), data in usage_map.items():
        used = data["used_total"]
        max_allowed = data["max_allowed"]

        if used > max_allowed:
            msg = _("❌ {0} | Workstation: {1} | Overused: {2} > {3}").format(
                date, workstation, used, max_allowed
            )
            print(msg)
        else:
            msg = _("✅ {0} | Workstation: {1} | OK: {2} <= {3}").format(
                date, workstation, used, max_allowed
            )
            print(msg)
        usage_summary.append(msg)

    return usage_summary


def _create_capacity_docs(production_plan_doc: Dict) -> List[datetime.date]:
    grouped_items_by_date = {}
    for po_item in production_plan_doc.po_items:
        date_key = frappe.utils.getdate(po_item.get("planned_start_date"))
        if date_key not in grouped_items_by_date:
            grouped_items_by_date[date_key] = []

        grouped_items_by_date[date_key].append(
            {
                "bom": po_item.get("bom_no"),
                "qty": po_item.get("planned_qty"),
            }
        )

    processed_dates = []
    for date_str, bom_list in grouped_items_by_date.items():
        workstation_data = {}
        for entry in bom_list:
            operations = frappe.get_all(
                "BOM Operation",
                filters={"parent": entry["bom"]},
                fields=["operation", "time_in_mins", "workstation"],
            )

            for o in operations:
                ws = o.workstation
                time = (o.time_in_mins or 0) * entry["qty"]
                if ws:
                    if ws not in workstation_data:
                        values = frappe.db.get_value(
                            "Workstation",
                            ws,
                            ["total_working_hours", "production_capacity"],
                            as_dict=1,
                        )

                        total_minutes = (
                            (values.total_working_hours * values.production_capacity) or 0
                        ) * 60
                        workstation_data[ws] = {"time": 0, "capacity": total_minutes}
                    workstation_data[ws]["time"] = workstation_data[ws]["time"] + time

        capacity_doc = frappe.new_doc("Capacity")
        capacity_doc.date = date_str
        capacity_doc.production_plan_ref = production_plan_doc.name

        capacity_plan_items = []
        for ws, info in workstation_data.items():
            percentile_usage = (
                (info["time"] / info["capacity"]) * 100 if info["capacity"] else 0
            )

            capacity_plan_items.append(
                {
                    "workstation": ws,
                    "used_duration": info["time"],
                    "daily_max_duration": info["capacity"],
                    "percentile_usage": percentile_usage,
                }
            )

        capacity_doc.set("capacity_plan_items", capacity_plan_items)
        capacity_doc.save()

        processed_dates.append(date_str)

    print("Grouped Items:", grouped_items_by_date)
    return processed_dates
