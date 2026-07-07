"""Bulk entry of Ausências — server side of the "Registar em Massa" dialog.

The data model is one Ausencia document per entry (so payroll, workflow and the
controller validations are untouched); several entries per employee/month are
allowed and SUM on the slip, so companies can register daily, weekly or monthly.
The company-wide entry mode (Settings.modo_registo_faltas) decides whether each
entry IS one concrete day ("Por Dias" — the day registered is the day; Ausencia.data
drives it, one record per day) or carries a plain sum ("Por Total").
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
	faltas and — in Por Dias mode — the registered days), for the bulk grid."""
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
		fields=["name", "funcionario", "n_de_faltas", "data"],
	)
	existentes = {}
	for row in registos:
		info = existentes.setdefault(
			row.funcionario, {"registos": 0, "total": 0, "dias": []}
		)
		info["registos"] += 1
		info["total"] += cint(row.n_de_faltas)
		if row.data:
			info["dias"].append(cint(str(row.data)[8:10]))

	for funcionario in funcionarios:
		existente = existentes.get(funcionario.name)
		if existente:
			existente["dias"].sort()
		funcionario["existente"] = existente

	return {"modo": modo_registo_faltas(), "funcionarios": funcionarios}


@frappe.whitelist()
def registar_massa(mes, ano, faltas, submeter=0):
	"""Create new Ausencia record(s) per employee in `faltas`. Por Dias mode: one
	record per day number (the day registered IS the day — mês/ano/n_de_faltas are
	derived by the controller from Ausencia.data). Por Total mode: one record
	carrying the count. Adding to an employee who already has records this month is
	allowed — the controller enforces the same-day rule (Por Dias) and the monthly
	total cap. All-or-nothing: any validation error aborts the whole batch."""
	_exigir_permissao("create")
	if isinstance(faltas, str):
		faltas = json.loads(faltas)

	modo = modo_registo_faltas()
	inicio, fim = mes_ano_para_periodo(mes, ano)
	criadas = []
	for funcionario, valor in faltas.items():
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
			for dia in dias:
				registo = frappe.get_doc(
					{
						"doctype": "Ausencia",
						"funcionario": funcionario,
						"data": str(inicio.replace(day=dia)),
					}
				)
				registo.insert()
				if cint(submeter):
					registo.submit()
				criadas.append(registo.name)
		else:
			n = cint(valor)
			if n <= 0:
				continue
			registo = frappe.get_doc(
				{
					"doctype": "Ausencia",
					"funcionario": funcionario,
					"mes": mes,
					"ano": cint(ano),
					"n_de_faltas": n,
				}
			)
			registo.insert()
			if cint(submeter):
				registo.submit()
			criadas.append(registo.name)

	return {"criadas": criadas}
