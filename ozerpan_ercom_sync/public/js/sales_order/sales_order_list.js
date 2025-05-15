frappe.listview_settings["Sales Order"] = {
  refresh(listview) {
    console.log("-- ListView refresh --");
  },
  onload(listview) {
    console.log("-- ListView Onload --");
    syncErcomDatabase(listview);
    // uploadXLSFile(listview);
    fileProcessor(listview);
  },
};

function syncErcomDatabase(listview) {
  listview.page.add_inner_button(__("Sync Ercom"), () => callSyncErcomApi());
}

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
    //   let d = new frappe.ui.Dialog({
    //     title: __("Select Excel File"),
    //     fields: [
    //       {
    //         label: "File",
    //         fieldname: "file",
    //         fieldtype: "Attach",
    //         reqd: 1,
    //       },
    //     ],
    //     size: "small",
    //     primary_action_label: __("Submit"),
    //     primary_action(values) {
    //       console.log(values);
    //       callProcessFileAPI(values);
    //       d.hide();
    //     },
    //   });
    //   d.show();
  });
}

function uploadXLSFile(listview) {
  listview.page.add_inner_button(__("Upload Excel"), () => {
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

function callProcessFileAPI(values) {
  frappe.call({
    method: "ozerpan_ercom_sync.custom_api.api.process_excel_file",
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

function callSyncErcomApi() {
  frappe.call({
    method: "ozerpan_ercom_sync.custom_api.sync_ercom.sync_ercom",
    freeze: true,
    callback: (r) => {
      if (r.message) {
        console.log(r.message);
        frappe.msgprint({
          title: __("Success"),
          indicator: "green",
          message: __("Customers synchronized successfully."),
        });
      }
    },
    error: (r) => {
      frappe.msgprint({
        title: __("Error"),
        indicator: "red",
        message: __("An error occurred while synchronizing customers."),
      });
    },
  });
}
