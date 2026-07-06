"""Bulk entry of Ausências — server side of the "Registar em Massa" dialog.

The data model stays one Ausencia document per entry (so payroll, workflow and the
controller validations are untouched); several entries per employee/month are
allowed and SUM on the slip, so companies can register daily, weekly or monthly.
The company-wide entry mode (Settings.modo_registo_faltas) decides whether entries
list concrete days ("Por Dias") or carry a plain sum ("Por Total").
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

from entre_hr.entre_hr.doctype.ausencia.ausencia import modo_registo_faltas
from entre_hr.utils import mes_ano_para_periodo


def _exigir_permissao(ptype):
	if not frappe.has_permission("Ausencia", ptype):
		frappe.throw(_("Sem permissão para {0} Ausências.").format(ptype), frappe.PermissionError)


@frappe.whitelist()
def dados_registo_massa(mes, ano):
	"""Active employees plus what the month already has registered (records, total
	faltas and — in Por Dias mode — the marked days), for the bulk grid."""
	_exigir_permissao("read")
	funcionarios = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "department"],
		order_by="employee_name asc",
	)

	registos = frappe.get_all(
		"Ausencia",
		filters={"mes": mes, "ano": cint(ano), "docstatus": ["<", 2]},
		fields=["name", "funcionario", "n_de_faltas"],
	)
	existentes = {}
	for row in registos:
		info = existentes.setdefault(
			row.funcionario, {"registos": 0, "total": 0, "dias": []}
		)
		info["registos"] += 1
		info["total"] += cint(row.n_de_faltas)

	if registos:
		for dia in frappe.get_all(
			"Dia De Ausencia",
			filters={"parenttype": "Ausencia", "parent": ["in", [r.name for r in registos]]},
			fields=["parent", "data"],
			order_by="data asc",
		):
			funcionario = next(r.funcionario for r in registos if r.name == dia.parent)
			existentes[funcionario]["dias"].append(cint(str(dia.data)[8:10]))

	for funcionario in funcionarios:
		funcionario["existente"] = existentes.get(funcionario.name)

	return {"modo": modo_registo_faltas(), "funcionarios": funcionarios}


@frappe.whitelist()
def registar_massa(mes, ano, faltas, submeter=0):
	"""Create one new Ausencia per employee in `faltas`. Por Dias mode: values are
	lists of day numbers; Por Total mode: values are counts. Adding to an employee
	who already has records this month is allowed — the controller enforces the
	same-day rule (Por Dias) and the monthly total cap. All-or-nothing: any
	validation error aborts the whole batch. Returns {criadas}."""
	_exigir_permissao("create")
	if isinstance(faltas, str):
		faltas = json.loads(faltas)

	modo = modo_registo_faltas()
	inicio, fim = mes_ano_para_periodo(mes, ano)
	criadas = []
	for funcionario, valor in faltas.items():
		doc = {
			"doctype": "Ausencia",
			"funcionario": funcionario,
			"mes": mes,
			"ano": cint(ano),
		}
		if modo == "Por Dias":
			dias = sorted({cint(d) for d in valor if cint(d) > 0})
			if not dias:
				continue
			if dias[-1] > fim.day:
				frappe.throw(
					_("Dia {0} inválido para {1} de {2} (funcionário {3}).").format(
						dias[-1], mes, ano, funcionario
					)
				)
			doc["dias"] = [{"data": str(inicio.replace(day=dia))} for dia in dias]
		else:
			n = cint(valor)
			if n <= 0:
				continue
			doc["n_de_faltas"] = n

		registo = frappe.get_doc(doc)
		registo.insert()
		if cint(submeter):
			registo.submit()
		criadas.append(registo.name)

	return {"criadas": criadas}
