// Copyright (c) 2025, juniustech and contributors
// For license information, please see license.txt

frappe.ui.form.on("CamListe", {
  refresh(frm) {
    displayID(frm);
  },

  onload(frm) {
    displayID(frm);
  },
});

function displayID(frm) {
  frm.doc.items.forEach((row) => {
    frappe.model.set_value(row.doctype, row.name, "row_id", row.name);
  });
}
