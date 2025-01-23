frappe.listview_settings["TesDetay"] = {
  refresh(listview) {
    console.log("-- ListView Refresh --");
  },
  onload(listview) {
    console.log("-- ListView Onload --");
    syncTesDetayBtn(listview);
    readBarcode(listview);
    getPozData(listview);
  },
};

function syncTesDetayBtn(listview) {
  listview.page.add_inner_button(__("Sync TesDetay"), () =>
    callSyncTesDetayApi(),
  );
}

function readBarcode(listview) {
  listview.page.add_inner_button(__("Read Barcode"), () =>
    callReadBarcodeAPI(),
  );
}

function getPozData(listview) {
  listview.page.add_inner_button(__("Sync PozData"), () => callGetPozDataAPI());
}

function callGetPozDataAPI() {
  frappe.call({
    method: "ozerpan_ercom_sync.custom_api.poz_data.get_poz_data",
    args: {
      barcode: "K400310324   11127000000000",
    },
    callback: (r) => {
      if (r.message) {
        console.log(r.message);
        frappe.msgprint({
          title: __("Success"),
          indicator: "green",
          message: __("Poz data success."),
        });
      }
    },
    error: (r) => {
      console.log(r.message);
      frappe.msgprint({
        title: __("Error"),
        indicator: "red",
        message: __("An error occurred while getting Poz Data."),
      });
    },
  });
}

function callReadBarcodeAPI() {
  frappe.call({
    method: "ozerpan_ercom_sync.custom_api.api.read_barcode",
    args: {
      barcode: "K400310324   11127000000000",
      employee: "HR-EMP-00001",
      // operation: "Kaynak Köşe Temizleme",
      operation: "Kalite",
    },
    callback: (r) => {
      if (r.message) {
        console.log(r.message);
        frappe.msgprint({
          title: __("Success"),
          indicator: "green",
          message: __("Barcode data success."),
        });
      }
    },
    error: (r) => {
      console.log(r.message);
      frappe.msgprint({
        title: __("Error"),
        indicator: "red",
        message: __("An error occurred while reading Barcode."),
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
