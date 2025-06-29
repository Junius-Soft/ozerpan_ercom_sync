app_name = "ozerpan_ercom_sync"
app_title = "Ozerpan Ercom Sync"
app_publisher = "juniustech"
app_description = "Ercom DB Sync for Ozerpan"
app_email = "junius@tech.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Fixtures
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "Ozerpan Ercom Sync"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "Ozerpan Ercom Sync"]]},
    # {"dt": "Workflow"},
    # {"dt": "Workflow State"},
    # {"dt": "Item", "filters": [["custom_poz_id", "=", ""], ["custom_serial", "=", ""]]},
    # {"dt": "Item Group"},
    # {"dt": "Workstation"},
    # {"dt": "Operation"},
    # {"dt": "UOM"},
    # {"dt": "Cam"},
    # {"dt": "Profile Type"},
    # {"dt": "Cam Recipe"},
]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "ozerpan_ercom_sync",
# 		"logo": "/assets/ozerpan_ercom_sync/logo.png",
# 		"title": "Ozerpan Ercom Sync",
# 		"route": "/ozerpan_ercom_sync",
# 		"has_permission": "ozerpan_ercom_sync.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/ozerpan_ercom_sync/css/ozerpan_ercom_sync.css"
# app_include_js = "/assets/ozerpan_ercom_sync/js/ozerpan_ercom_sync.js"

# include js, css files in header of web template
# web_include_css = "/assets/ozerpan_ercom_sync/css/ozerpan_ercom_sync.css"
# web_include_js = "/assets/ozerpan_ercom_sync/js/ozerpan_ercom_sync.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "ozerpan_ercom_sync/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Sales Order": "public/js/sales_order/sales_order.js",
    "Customer": "public/js/customer/customer.js",
    # "Production Plan": "public/js/production_plan/production_plan.js",
}
doctype_list_js = {
    # "Customer": "public/js/customer/customer_list.js",
    # "Item": "public/js/item/item_list.js",
    # "BOM": "public/js/bom/bom_list.js",
    "Sales Order": "public/js/sales_order/sales_order_list.js",
    "Production Plan": "public/js/production_plan/production_plan_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "ozerpan_ercom_sync/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "ozerpan_ercom_sync.utils.jinja_methods",
# 	"filters": "ozerpan_ercom_sync.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "ozerpan_ercom_sync.install.before_install"
# after_install = "ozerpan_ercom_sync.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "ozerpan_ercom_sync.uninstall.before_uninstall"
# after_uninstall = "ozerpan_ercom_sync.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "ozerpan_ercom_sync.utils.before_app_install"
# after_app_install = "ozerpan_ercom_sync.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "ozerpan_ercom_sync.utils.before_app_uninstall"
# after_app_uninstall = "ozerpan_ercom_sync.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ozerpan_ercom_sync.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Sales Order": {
        "validate": "ozerpan_ercom_sync.custom_hooks.sales_order_hooks.validate.validate",
        "before_save": "ozerpan_ercom_sync.custom_hooks.sales_order_hooks.before_save.before_save",
    },
    "Job Card": {
        "after_insert": "ozerpan_ercom_sync.custom_hooks.job_card_hooks.after_insert.after_insert",
        "on_trash": "ozerpan_ercom_sync.custom_hooks.job_card_hooks.on_trash.on_trash",
    },
    "Production Plan": {
        "on_update": "ozerpan_ercom_sync.custom_hooks.production_plan_hooks.on_update.on_update",
        "on_submit": "ozerpan_ercom_sync.custom_hooks.production_plan_hooks.on_submit.on_submit",
    },
    # "DocType":{
    #     "before_insert": "", # Before a new document is inserted into the DB
    #     "after_insert": "", # Right after a new document is inserted
    #     "validate": "", # Before saving; good for checking data consistency
    #     "before_save": "", # Just before a document is saved (both new + update)
    #     "on_update": "", # After saving a document
    #     "before_submit": "", # Before document is submitted
    #     "on_submit": "", # After document is submitted
    #     "before_cancel": "", # Before a document is canceled
    #     "on_cancel": "", # After document is canceled
    #     "before_update_after_submit": "", # When updating a submitted document
    #     "on_update_after_submit": "", # After updating a submitted document
    #     "on_trash": "", # Before deleting a document
    #     "after_delete": "", # After deleting a document
    # }
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    # "hourly": [
    #     "ozerpan_ercom_sync.tasks.process_xls_files.process_xls_files",
    # ],
    # "cron": {
    #         "15 18 * * *": [
    #             "app.scheduled_tasks.delete_all_barcodes_for_users"
    #         ],
    #         "*/6 * * * *": [
    #             "app.scheduled_tasks.collect_error_snapshots"
    #         ],
    #         "annual": [
    #             "app.scheduled_tasks.collect_error_snapshots"
    #         ]
    # }
    # "all": [
    # 	"ozerpan_ercom_sync.tasks.all"
    # ],
    # "daily": [
    # 	"ozerpan_ercom_sync.tasks.daily"
    # ],
    # "hourly": [
    # 	"ozerpan_ercom_sync.tasks.hourly"
    # ],
    # "weekly": [
    # 	"ozerpan_ercom_sync.tasks.weekly"
    # ],
    # "monthly": [
    # 	"ozerpan_ercom_sync.tasks.monthly"
    # ],
}

# Testing
# -------

# before_tests = "ozerpan_ercom_sync.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "ozerpan_ercom_sync.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps

# override_doctype_dashboards = {
#     # "Task": "ozerpan_ercom_sync.task.get_dashboard_data"
#     # "Production Plan": "ozerpan_ercom_sync.production_plan_hooks.get_dashboard_data.get_dashboard_data",
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["ozerpan_ercom_sync.utils.before_request"]
# after_request = ["ozerpan_ercom_sync.utils.after_request"]

# Job Events
# ----------
# before_job = ["ozerpan_ercom_sync.utils.before_job"]
# after_job = ["ozerpan_ercom_sync.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"ozerpan_ercom_sync.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
