frappe.listview_settings["Production Plan"] = {
  refresh(listview) {
    console.log("-- ListView Refresh --");
  },
  onload(listview) {
    console.log("-- ListView Onload --");
    uploadExcel(listview);
  },
};

function uploadExcel(listview) {
  listview.page.add_inner_button(__("Upload OPT/DST"), () => {
    let d = new frappe.ui.Dialog({
      title: __("Select Excel File"),
      fields: [
        {
          label: "File",
          fieldname: "file",
          fieldtype: "Attach",
          reqd: 1,
        },
      ],
      size: "small",
      primary_action_label: __("Submit"),
      primary_action(values) {
        console.log(values);
        callUploadFileApi(values);
        d.hide();
      },
    });
    d.show();
  });
}

function callUploadFileApi(values) {
  frappe.call({
    method: "ozerpan_ercom_sync.custom_api.file_upload.upload_file.upload_file",
    args: {
      file_url: values.file,
    },
    freeze: true,
    callback: (r) => {
      if (r.message) {
        console.log(r.message);
        frappe.msgprint({
          title: __("Success"),
          indicator: "green",
          message: __("File processed successfully."),
        });
      }
    },
    error: (r) => {
      frappe.msgprint({
        title: __("Error"),
        indicator: "red",
        message: __("An error occurred while processing the file."),
      });
    },
  });
}
