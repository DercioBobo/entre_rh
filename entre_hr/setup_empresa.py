"""Per-company payroll bootstrap.

A Mozambique payroll company needs, on top of the chart of accounts ERPNext builds
itself: a Salary Structure with the base-salary earning, a payroll payable account,
an employee-advance account, GL accounts for the statutory withholdings, every Entre
HR Salary Component wired to an account for the accrual entry, and a holiday list.

`configurar_empresa` creates all of it, idempotently — find-or-create everywhere, so
it is safe to re-run. It is wired to Company `on_update` (fires once the chart of
accounts exists) and looped over every existing company on install/migrate. After it
runs the only manual steps left are: create the Employee and click "Definir Salário".

Everything national/legal (INSS + IRPS rates and tables, minimum wage, absence rules,
13º month, vacation policy) stays site-wide in Entre HR Settings — it is not per
company and is seeded by entre_hr.install.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate, today

from entre_hr.utils import ROLES_GESTAO_RH, ensure_salary_component, nome_estrutura_base

COMPONENTE_BASE = "Salario Base"  # unaccented, matching "13o Salario" / "Adiantamento de Salario"

# Accounts this module ensures per company: (account_name, root_type, account_type).
CONTA_SALARIOS = ("Salarios", "Expense", "Expense Account")
CONTA_INSS = ("INSS a Pagar", "Liability", "")
CONTA_IRPS = ("IRPS a Pagar", "Liability", "")
CONTA_ADIANTAMENTOS = ("Adiantamentos a Funcionarios", "Asset", "")
CONTA_PAYABLE = ("Folha a Pagar", "Liability", "Payable")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def on_update(doc, method=None):
	"""Company doc_event. Runs after the controller's own on_update, so the default
	chart of accounts already exists. Never blocks saving the company — a failure is
	logged and surfaced as a warning."""
	if _ja_configurada(doc.name):
		return
	try:
		configurar_empresa(doc.name)
	except Exception:
		frappe.log_error(title=f"Entre HR: configuração da empresa {doc.name} falhou")
		frappe.msgprint(
			_("A configuração automática de folha para {0} falhou — verifique o Error Log.").format(
				doc.name
			),
			indicator="orange",
			alert=True,
		)


def _ja_configurada(company):
	return bool(
		frappe.db.exists("Salary Structure", nome_estrutura_base(company))
		and frappe.db.get_value("Company", company, "default_payroll_payable_account")
		and frappe.db.get_value("Company", company, "default_holiday_list")
	)


@frappe.whitelist()
def configurar_empresa_manual(company):
	"""'Configurar Folha' button on the Company form. Role-gated wrapper."""
	if not ROLES_GESTAO_RH & set(frappe.get_roles()):
		frappe.throw(_("Sem permissão para configurar a folha."), frappe.PermissionError)
	return configurar_empresa(company)


def configurar_empresa(company):
	"""Idempotently bootstrap `company` for Entre HR payroll. Returns the structure name."""
	if not frappe.db.exists("Account", {"company": company, "is_group": 1}):
		# Chart of accounts not built yet — nothing to hang GL accounts off.
		return None

	contas = _contas(company)
	_defaults_da_empresa(company, contas)
	estrutura = _estrutura_base(company)
	_mapear_componentes(company, contas)
	_holiday_list(company)
	return estrutura


def configurar_todas():
	"""Run the bootstrap for every company (install/migrate)."""
	for company in frappe.get_all("Company", pluck="name"):
		configurar_empresa(company)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def _grupo_raiz(company, root_type):
	"""A non-root group account of the given root_type to parent new accounts under
	(the shallowest one), falling back to the root group itself."""
	filtros = {"company": company, "root_type": root_type, "is_group": 1}
	return frappe.db.get_value(
		"Account", {**filtros, "parent_account": ["is", "set"]}, "name", order_by="lft asc"
	) or frappe.db.get_value("Account", filtros, "name", order_by="lft asc")


def _conta(company, spec):
	nome, root_type, account_type = spec
	existente = frappe.db.get_value(
		"Account", {"company": company, "account_name": nome}, "name"
	)
	if existente:
		return existente
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": nome,
			"company": company,
			"parent_account": _grupo_raiz(company, root_type),
			"root_type": root_type,
			"account_type": account_type or None,
			"is_group": 0,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def _contas(company):
	return {
		"salarios": _conta(company, CONTA_SALARIOS),
		"inss": _conta(company, CONTA_INSS),
		"irps": _conta(company, CONTA_IRPS),
		"adiantamentos": _conta(company, CONTA_ADIANTAMENTOS),
		"payable": _conta(company, CONTA_PAYABLE),
	}


def _defaults_da_empresa(company, contas):
	valores = {}
	if not frappe.db.get_value("Company", company, "default_payroll_payable_account"):
		valores["default_payroll_payable_account"] = contas["payable"]
	if not frappe.db.get_value("Company", company, "default_employee_advance_account"):
		valores["default_employee_advance_account"] = contas["adiantamentos"]
	if valores:
		frappe.db.set_value("Company", company, valores)


# ---------------------------------------------------------------------------
# Salary Structure + component -> account mapping
# ---------------------------------------------------------------------------


def _estrutura_base(company):
	"""Create + submit 'Base - <abbr>': one earning row, the 'Salario Base' component,
	amount = formula `base` (HRMS resolves it to the SSA base on every slip). Taxable
	so INSS/IRPS build on it, and `depends_on_payment_days` so HRMS prorates it for a
	mid-month admission/termination (and any HRMS leave/attendance).

	Deductions stay out of the structure: INSS, IRPS, Faltas, Emprestimo and
	Adiantamento are appended by salary_slip_hooks at assembly time."""
	_fixar_base_payment_days()
	nome = nome_estrutura_base(company)
	if frappe.db.exists("Salary Structure", nome):
		return nome

	componente = ensure_salary_component(
		COMPONENTE_BASE,
		"Earning",
		amount_based_on_formula=1,
		formula="base",
		is_tax_applicable=1,
		depends_on_payment_days=1,
	)
	estrutura = frappe.new_doc("Salary Structure")
	estrutura.name = nome
	estrutura.company = company
	estrutura.is_active = "Yes"
	estrutura.payroll_frequency = "Monthly"
	moeda = frappe.get_cached_value("Company", company, "default_currency")
	if moeda:
		estrutura.currency = moeda
	estrutura.append(
		"earnings",
		{
			"salary_component": componente,
			"amount_based_on_formula": 1,
			"formula": "base",
			"depends_on_payment_days": 1,
		},
	)
	estrutura.flags.ignore_permissions = True
	estrutura.insert()
	estrutura.submit()
	return estrutura.name


def _fixar_base_payment_days():
	"""Ensure the base component and every 'Base - *' structure earning row are
	payment-day dependent — for installs whose structure predates this."""
	if not frappe.db.exists("Salary Component", COMPONENTE_BASE):
		return
	if not frappe.db.get_value("Salary Component", COMPONENTE_BASE, "depends_on_payment_days"):
		frappe.db.set_value(
			"Salary Component", COMPONENTE_BASE, "depends_on_payment_days", 1
		)
	linhas = frappe.get_all(
		"Salary Detail",
		filters={
			"parenttype": "Salary Structure",
			"salary_component": COMPONENTE_BASE,
			"depends_on_payment_days": 0,
		},
		pluck="name",
	)
	for linha in linhas:
		frappe.db.set_value("Salary Detail", linha, "depends_on_payment_days", 1)


def _mapear_componentes(company, contas):
	"""Add one `accounts` row per component so the accrual Journal Entry has somewhere
	to book each line. Earnings and Faltas hit the salary expense; the statutory
	withholdings their payable accounts; loans/advances the advance asset."""
	settings = frappe.get_cached_doc("Entre HR Settings")
	destino = {
		COMPONENTE_BASE: contas["salarios"],
		settings.get("componente_retroativo"): contas["salarios"],
		settings.get("componente_13o_salario"): contas["salarios"],
		settings.get("componente_faltas"): contas["salarios"],
		settings.get("componente_proporcional"): contas["salarios"],
		settings.get("componente_inss"): contas["inss"],
		settings.get("componente_irps"): contas["irps"],
		settings.get("componente_emprestimo"): contas["adiantamentos"],
		settings.get("componente_adiantamento"): contas["adiantamentos"],
	}
	for componente, conta in destino.items():
		_mapear_um(componente, company, conta)


def _mapear_um(componente, company, conta):
	if not componente or not conta or not frappe.db.exists("Salary Component", componente):
		return
	if frappe.db.exists("Salary Component Account", {"parent": componente, "company": company}):
		return
	doc = frappe.get_doc("Salary Component", componente)
	doc.append("accounts", {"company": company, "account": conta})
	doc.flags.ignore_permissions = True
	doc.save()


def mapear_novo_componente(doc, method=None):
	"""Salary Component doc_event: a component added later (a new subsídio, a new
	deduction) is wired to every company automatically — earnings to the salary
	expense, deductions to the payroll payable — so it books without manual setup.
	Re-point it in the component's own Accounts table when it belongs elsewhere.
	Never blocks creating the component — a failure is logged only."""
	if doc.get("accounts"):
		return
	try:
		for company in frappe.get_all("Company", pluck="name"):
			if not frappe.db.exists("Account", {"company": company, "is_group": 1}):
				continue
			contas = _contas(company)
			conta = contas["salarios"] if doc.type == "Earning" else contas["payable"]
			_mapear_um(doc.name, company, conta)
	except Exception:
		frappe.log_error(title=f"Entre HR: mapeamento GL do componente {doc.name} falhou")


# ---------------------------------------------------------------------------
# Holiday list
# ---------------------------------------------------------------------------


def _holiday_list(company):
	"""A Mon–Fri weekly-off holiday list for the current year, set as the company
	default when it has none. Public holidays are added by the operator; a new year's
	list is created the same way (this only ever seeds, never overwrites)."""
	ano = getdate(today()).year
	abbr = frappe.get_cached_value("Company", company, "abbr") or company
	nome = f"{abbr} {ano}"
	if not frappe.db.exists("Holiday List", nome):
		doc = frappe.new_doc("Holiday List")
		doc.holiday_list_name = nome
		doc.from_date = date(ano, 1, 1)
		doc.to_date = date(ano, 12, 31)
		for dia in ("Saturday", "Sunday"):
			doc.weekly_off = dia
			doc.get_weekly_off_dates()
		doc.flags.ignore_permissions = True
		doc.insert()
	if not frappe.db.get_value("Company", company, "default_holiday_list"):
		frappe.db.set_value("Company", company, "default_holiday_list", nome)
