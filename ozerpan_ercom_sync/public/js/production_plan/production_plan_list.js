frappe.listview_settings["Production Plan"] = {
  refresh(listview) {
    console.log("-- ListView refresh --");
  },
  onload(listview) {
    console.log("-- ListView Onload --");
    fileProcessor(listview);
  },
};

function fileProcessor(listview) {
  listview.page.add_inner_button(__("Process File"), () => {
    frappe.call({
      method: "ozerpan_ercom_sync.custom_api.api.process_file",
      callback: function (r) {
        if (r.message) {
          frappe.msgprint(r.message);
        }
      },
    });
  });
}
