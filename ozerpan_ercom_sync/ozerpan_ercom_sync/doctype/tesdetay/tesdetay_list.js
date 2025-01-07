frappe.listview_settings["TesDetay"] = {
  refresh(listview) {
    console.log("-- ListView Refresh --");
  },
  onload(listview) {
    console.log("-- ListView Onload --");
    syncTesDetayBtn(listview);
    getData(listview);
  },
};

function syncTesDetayBtn(listview) {
  listview.page.add_inner_button(__("Sync TesDetay"), () =>
    callSyncTesDetayApi(),
  );
}

function getData(listview) {
  listview.page.add_inner_button(__("Barcode Data"), () =>
    callBarcodeDataApi(),
  );
}

function callBarcodeDataApi() {
  frappe.call({
    method: "ozerpan_ercom_sync.custom_api.api.getData",
    args: {
      barcode: "K2001124913404   14211400086700",
    },
    callback: (r) => {
      if (r.message) {
        console.log(r.message);
        frappe.msgprint({
          title: __("Success"),
          indicator: "green",
          message: __("Barcode data successfully."),
        });
      }
    },
    error: (r) => {
      console.log(r.message);
      frappe.msgprint({
        title: __("Error"),
        indicator: "red",
        message: __("An error occurred while synchronizing TesDetay."),
      });
    },
  });
}

function callSyncTesDetayApi() {
  frappe.call({
    method: "ozerpan_ercom_sync.custom_api.tes_detay.sync_tes_detay",
    freeze: true,
    callback: (r) => {
      if (r.message) {
        console.log(r.message);
        frappe.msgprint({
          title: __("Success"),
          indicator: "green",
          message: __("TesDetay synchronized successfully."),
        });
      }
    },
    error: (r) => {
      console.log(r.message);
      frappe.msgprint({
        title: __("Error"),
        indicator: "red",
        message: __("An error occurred while synchronizing TesDetay."),
      });
    },
  });
}
