"""Bulk entry of Horas Extras — server side of the "Registar em Massa" dialog.

One Horas Extras document per employee/month (so payroll, workflow and controller
validations are untouched). Several records per employee/month are allowed and SUM
on the slip, so overtime can be topped up during the month.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt


def _exigir_permissao(ptype):
	if not frappe.has_permission("Horas Extras", ptype):
		frappe.throw(
			_("Sem permissão para {0} Horas Extras.").format(ptype), frappe.PermissionError
		)


@frappe.whitelist()
def dados_registo_massa(mes, ano):
	"""Active employees plus what the month already has registered (records + summed
	hours), for the bulk grid."""
	_exigir_permissao("read")
	funcionarios = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "department"],
		order_by="employee_name asc",
	)

	registos = frappe.get_all(
		"Horas Extras",
		filters={"mes": mes, "ano": cint(ano), "docstatus": ["<", 2]},
		fields=["funcionario", "horas_50", "horas_100"],
	)
	existentes = {}
	for row in registos:
		info = existentes.setdefault(
			row.funcionario, {"registos": 0, "horas_50": 0.0, "horas_100": 0.0}
		)
		info["registos"] += 1
		info["horas_50"] += flt(row.horas_50)
		info["horas_100"] += flt(row.horas_100)

	for funcionario in funcionarios:
		funcionario["existente"] = existentes.get(funcionario.name)

	return {"funcionarios": funcionarios}


@frappe.whitelist()
def registar_massa(mes, ano, horas, submeter=0):
	"""Create one Horas Extras record per employee in `horas` (a map of
	funcionario -> {h50, h100}). Adding to an employee who already has records this
	month is allowed — they sum on the slip. All-or-nothing: any validation error
	aborts the whole batch."""
	_exigir_permissao("create")
	if isinstance(horas, str):
		horas = json.loads(horas)

	criadas = []
	for funcionario, valores in horas.items():
		h50 = flt((valores or {}).get("h50"))
		h100 = flt((valores or {}).get("h100"))
		if h50 <= 0 and h100 <= 0:
			continue
		registo = frappe.get_doc(
			{
				"doctype": "Horas Extras",
				"funcionario": funcionario,
				"mes": mes,
				"ano": cint(ano),
				"horas_50": h50,
				"horas_100": h100,
			}
		)
		registo.insert()
		if cint(submeter):
			registo.submit()
		criadas.append(registo.name)

	return {"criadas": criadas}
