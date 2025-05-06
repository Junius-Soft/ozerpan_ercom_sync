import frappe


def delete_related_capacity_docs(production_plan_docname: str) -> None:
    capacity_docs = frappe.get_all(
        "Capacity", filters={"production_plan_ref": production_plan_docname}
    )
    for capacity_doc in capacity_docs:
        frappe.delete_doc("Capacity", capacity_doc.name)
