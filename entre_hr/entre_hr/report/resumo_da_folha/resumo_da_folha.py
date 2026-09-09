"""Resumo da Folha — monthly payroll register from submitted Salary Slips.

One row per slip: the employee, the period, one Currency column for every Salary
Component that actually carries a value in the filtered set (empty components are
dropped, not shown), then Bruto / Total Descontos / Líquido. Earnings columns come
first, then deductions, each ordered by component name. `add_total_row` sums it.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from entre_hr.utils import MESES


def execute(filters=None):
	filters = frappe._dict(filters or {})
	slips = _slips(filters)
	if not slips:
		return _colunas([]), []

	detalhes = _detalhes([s.name for s in slips])
	componentes = _componentes_com_valor(slips, detalhes)
	return (
		_colunas(componentes),
		_linhas(slips, detalhes, componentes),
		None,
		None,
		_resumo(slips),
	)


def _colunas(componentes):
	colunas = [
		{"label": _("Funcionário"), "fieldname": "funcionario", "fieldtype": "Link",
		 "options": "Employee", "width": 130},
		{"label": _("Nome"), "fieldname": "nome", "fieldtype": "Data", "width": 200},
		{"label": _("Empresa"), "fieldname": "empresa", "fieldtype": "Link",
		 "options": "Company", "width": 150},
		{"label": _("Mês"), "fieldname": "mes", "fieldtype": "Data", "width": 130},
	]
	for comp, _tipo in componentes:
		colunas.append({
			"label": comp, "fieldname": "c_" + frappe.scrub(comp),
			"fieldtype": "Currency", "width": 130,
		})
	colunas += [
		{"label": _("Bruto"), "fieldname": "bruto", "fieldtype": "Currency", "width": 130},
		{"label": _("Total Descontos"), "fieldname": "descontos", "fieldtype": "Currency",
		 "width": 140},
		{"label": _("Líquido"), "fieldname": "liquido", "fieldtype": "Currency", "width": 140},
	]
	return colunas


def _slips(filters):
	cond = [["Salary Slip", "docstatus", "=", 1]]
	if filters.get("from_date"):
		cond.append(["Salary Slip", "start_date", ">=", filters.from_date])
	if filters.get("to_date"):
		cond.append(["Salary Slip", "start_date", "<=", filters.to_date])
	if filters.get("company"):
		cond.append(["Salary Slip", "company", "=", filters.company])
	if filters.get("funcionario"):
		cond.append(["Salary Slip", "employee", "=", filters.funcionario])
	return frappe.get_all(
		"Salary Slip",
		filters=cond,
		fields=["name", "employee", "employee_name", "company", "start_date",
				"gross_pay", "total_deduction", "net_pay"],
		order_by="company asc, employee_name asc, start_date asc",
	)


def _detalhes(nomes):
	out = {}
	for row in frappe.get_all(
		"Salary Detail",
		filters={"parent": ["in", nomes], "parentfield": ["in", ["earnings", "deductions"]]},
		fields=["parent", "salary_component", "parentfield", "amount"],
	):
		comps = out.setdefault(row.parent, {})
		atual = comps.get(row.salary_component)
		if atual:
			atual["amount"] += flt(row.amount)
		else:
			comps[row.salary_component] = {"amount": flt(row.amount), "tipo": row.parentfield}
	return out


def _componentes_com_valor(slips, detalhes):
	totais, tipos = {}, {}
	for slip in slips:
		for comp, info in detalhes.get(slip.name, {}).items():
			totais[comp] = totais.get(comp, 0.0) + info["amount"]
			tipos[comp] = info["tipo"]
	vivos = [c for c, t in totais.items() if abs(t) >= 0.005]
	ordenados = sorted(c for c in vivos if tipos[c] == "earnings")
	ordenados += sorted(c for c in vivos if tipos[c] == "deductions")
	return [(c, tipos[c]) for c in ordenados]


def _linhas(slips, detalhes, componentes):
	chaves = [("c_" + frappe.scrub(c), c) for c, _t in componentes]
	linhas = []
	for slip in slips:
		d = detalhes.get(slip.name, {})
		linha = {
			"funcionario": slip.employee,
			"nome": slip.employee_name,
			"empresa": slip.company,
			"mes": _rotulo_mes(slip.start_date),
			"bruto": flt(slip.gross_pay),
			"descontos": flt(slip.total_deduction),
			"liquido": flt(slip.net_pay),
		}
		for fieldname, comp in chaves:
			linha[fieldname] = flt(d.get(comp, {}).get("amount"))
		linhas.append(linha)
	return linhas


def _rotulo_mes(data):
	d = getdate(data)
	return f"{MESES[d.month - 1]} {d.year}"


def _resumo(slips):
	return [
		{"label": _("Funcionários"), "value": len(slips), "datatype": "Int"},
		{"label": _("Total Bruto"), "value": sum(flt(s.gross_pay) for s in slips),
		 "datatype": "Currency"},
		{"label": _("Total Descontos"), "value": sum(flt(s.total_deduction) for s in slips),
		 "datatype": "Currency"},
		{"label": _("Total Líquido"), "value": sum(flt(s.net_pay) for s in slips),
		 "datatype": "Currency"},
	]
