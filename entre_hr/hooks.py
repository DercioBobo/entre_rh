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

doctype_js = {
    "Employee": "public/js/employee.js",
}

# Fixtures
# --------

fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Aprovador RH", "RH Manager"]]]},
    {
        "dt": "Custom Field",
        "filters": [
            [
                "name",
                "in",
                [
                    "Employee-custom_salario_base_manual",
                    "Employee-custom_data_antiguidade_ferias",
                    "Employee-custom_ultima_acumulacao_ferias",
                    "Salary Slip-custom_dias_de_trabalho",
                    "Salary Slip-custom_dias_trabalhados",
                    "Salary Detail-custom_origem_entre_hr",
                ],
            ]
        ],
    },
]

# Document Events
# ---------------

doc_events = {
    "Salary Slip": {
        "before_insert": "entre_hr.payroll.salary_slip_hooks.before_insert",
        "before_validate": "entre_hr.payroll.salary_slip_hooks.before_validate",
        "before_submit": "entre_hr.payroll.salary_slip_hooks.before_submit",
        "on_submit": "entre_hr.payroll.salary_slip_hooks.on_submit",
        "on_cancel": "entre_hr.payroll.salary_slip_hooks.on_cancel",
    },
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": [
        "entre_hr.ferias.acumular_ferias_diario",
    ],
}
