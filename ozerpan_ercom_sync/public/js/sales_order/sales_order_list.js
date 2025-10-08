frappe.listview_settings["Sales Order"] = {
  refresh(listview) {
    console.log("-- ListView refresh --");
  },
  onload(listview) {
    console.log("-- ListView Onload --");
    syncErcomDatabase(listview);
    // uploadXLSFile(listview);
    fileProcessor(listview);
    getSingleOrder(listview);
  },
};

function getSingleOrder(listview) {
  listview.page.add_inner_button(__("Get Single Order"), () =>
    callGetSingleOrderApi(),
  );
}

function callGetSingleOrderApi() {
  frappe.prompt(
    {
      label: __("Order No"),
      fieldname: "order_no",
      fieldtype: "Data",
      reqd: 1,
    },
    (values) => {
      frappe.call({
        method: "ozerpan_ercom_sync.custom_api.sync_ercom.get_single_order",
        args: {
          order_no: values.order_no,
        },
        freeze: true,
        callback: (r) => {
          if (r.message) {
            console.log(r.message);
            frappe.msgprint({
              title: __("Success"),
              indicator: "green",
              message: __("Order retrieved successfully."),
            });
          }
        },
        error: (r) => {
          frappe.msgprint({
            title: __("Error"),
            indicator: "red",
            message: __("An error occurred while retrieving the order."),
          });
        },
      });
    },
    __("Enter Order Number"),
    __("Get Order"),
  );
}

function syncErcomDatabase(listview) {
  listview.page.add_inner_button(__("Sync Ercom"), () => callSyncErcomApi());
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

function fileProcessor(listview) {
  listview.page.add_inner_button(__("Process File"), () => {
    frappe.call({
      method: "ozerpan_ercom_sync.custom_api.api.process_file_background_job",
      callback: function (r) {
        if (r.message) {
          frappe.msgprint(r.message);
        }
      },
    });
  });
}
