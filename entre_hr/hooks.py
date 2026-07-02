app_name = "entre_hr"
app_title = "Entre HR"
app_publisher = "Dércio Bobo"
app_description = "HR + payroll app for Mozambique, built on Frappe / ERPNext / HRMS"
app_email = "derciobob@gmail.com"
app_license = "mit"

required_apps = ["frappe", "erpnext", "hrms"]

# Installation
# ------------

after_install = "entre_hr.install.after_install"
after_migrate = "entre_hr.install.after_migrate"

# Includes in <head>
# ------------------

app_include_css = "/assets/entre_hr/css/entre_hr.css"
app_include_js = "/assets/entre_hr/js/entre_hr.js"

# Fixtures
# --------

fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Aprovador RH", "RH Manager"]]]},
]

# Document Events
# ---------------
# (wired per phase — see BUILD_PLAN.md)

# doc_events = {}

# Scheduled Tasks
# ---------------
# (Phase 3: daily férias accrual)

# scheduler_events = {}
