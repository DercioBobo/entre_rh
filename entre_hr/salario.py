"""Base salary via Salary Structure Assignment (SSA) — BUILD_PLAN Phase 2.

Base pay lives in the HRMS Salary Structure Assignment.base. This module resolves an
employee's base (manual override -> current SSA -> minimum, floored at the minimum) and
applies it idempotently as a submitted SSA.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

ROLES_GESTAO_SALARIO = {"RH Manager", "System Manager"}


def get_settings():
	return frappe.get_cached_doc("Entre HR Settings")


def get_latest_ssa(employee):
	"""Latest submitted SSA for the employee, or None."""
	rows = frappe.get_all(
		"Salary Structure Assignment",
		filters={"employee": employee, "docstatus": 1},
		fields=["name", "base", "from_date", "salary_structure"],
		order_by="from_date desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def resolver_salario_base(employee):
	"""Resolve the employee's base salary.

	1. Employee.custom_salario_base_manual, if set.
	2. Else the current submitted SSA base, if any; else the minimum.
	3. Floored at Settings.salario_minimo_padrao when > 0.
	"""
	settings = get_settings()
	minimo = flt(settings.salario_minimo_padrao)

	base = flt(frappe.db.get_value("Employee", employee, "custom_salario_base_manual"))
	if not base:
		ssa = get_latest_ssa(employee)
		base = flt(ssa.base) if ssa else minimo

	if minimo > 0:
		base = max(base, minimo)
	return base


def aplicar_salario_base(employee, silent=False):
	"""Create/refresh the employee's submitted SSA with the resolved base. Idempotent."""
	settings = get_settings()
	if not settings.estrutura_salarial_padrao:
		frappe.throw(
			_("Defina a Estrutura Salarial Padrão em Entre HR Settings antes de aplicar salários.")
		)

	base = resolver_salario_base(employee)
	latest = get_latest_ssa(employee)

	# Idempotent: no-op when the latest SSA already carries this base.
	if latest and flt(latest.base) == flt(base):
		return latest.name

	emp = frappe.db.get_value(
		"Employee", employee, ["date_of_joining", "company"], as_dict=True
	)

	if latest:
		# A raise/change starts today, clamped to never precede joining.
		from_date = getdate(today())
		if emp.date_of_joining and from_date < getdate(emp.date_of_joining):
			from_date = getdate(emp.date_of_joining)
	else:
		# First assignment starts at joining.
		from_date = getdate(emp.date_of_joining or today())

	# Same-day change: cancel the colliding SSA so the new one supersedes it cleanly.
	if latest and getdate(latest.from_date) == from_date:
		old = frappe.get_doc("Salary Structure Assignment", latest.name)
		old.flags.ignore_permissions = True
		old.cancel()

	ssa = frappe.new_doc("Salary Structure Assignment")
	ssa.employee = employee
	ssa.company = emp.company
	ssa.salary_structure = settings.estrutura_salarial_padrao
	ssa.from_date = from_date
	ssa.base = base
	if settings.payroll_payable_account:
		ssa.payroll_payable_account = settings.payroll_payable_account
	ssa.flags.ignore_permissions = True
	ssa.insert()
	ssa.submit()

	if not silent:
		frappe.msgprint(
			_("Salário base {0} aplicado (SSA {1}).").format(
				frappe.format_value(base, {"fieldtype": "Currency"}), ssa.name
			),
			alert=True,
			indicator="green",
		)
	return ssa.name


@frappe.whitelist()
def definir_salario(employee, valor=None, usar_minimo=0, confirmar_reducao=0):
	"""'Definir Salário' button endpoint (Employee form).

	Pay-cut guard: computes prospective vs current resolved base BEFORE mutating; if the
	new value is lower and not yet confirmed, returns {requires_confirm, atual, novo} and
	writes nothing.
	"""
	if not ROLES_GESTAO_SALARIO & set(frappe.get_roles()):
		frappe.throw(_("Sem permissão para definir salários."), frappe.PermissionError)

	usar_minimo = cint(usar_minimo)
	confirmar_reducao = cint(confirmar_reducao)
	settings = get_settings()
	minimo = flt(settings.salario_minimo_padrao)

	if usar_minimo:
		if minimo <= 0:
			frappe.throw(_("Salário Mínimo Padrão não configurado em Entre HR Settings."))
		novo = minimo
	else:
		novo = flt(valor)
		if novo <= 0:
			frappe.throw(_("Indique um valor de salário válido."))
		if minimo > 0:
			novo = max(novo, minimo)

	atual = resolver_salario_base(employee)

	# Server-side pay-cut guard — nothing is written before this point.
	if novo < atual and not confirmar_reducao:
		return {"requires_confirm": True, "atual": atual, "novo": novo}

	frappe.db.set_value("Employee", employee, "custom_salario_base_manual", novo)
	ssa = aplicar_salario_base(employee, silent=True)
	return {"ssa": ssa, "base": novo}
