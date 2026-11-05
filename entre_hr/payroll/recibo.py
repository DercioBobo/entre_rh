"""Data for the Recibo de Salario print format, exposed to Jinja through hooks.py.

Amounts arrive already formatted, so the template only handles layout. Rows that don't
affect the payable amount (statistical, excluded from totals, or zero) are left out.
"""

import frappe
from frappe.utils import cint, flt, fmt_money, get_url, getdate

from entre_hr.salario import base_para_data
from entre_hr.utils import MESES, morada_da_empresa


def dados_recibo(doc):
	empresa = frappe.get_cached_doc("Company", doc.company)
	morada = morada_da_empresa(doc.company)
	inicio = getdate(doc.start_date)
	logo = empresa.get("company_logo")

	linhas = [
		{"descricao": r.salary_component, "remuneracao": _dinheiro(r.amount), "desconto": ""}
		for r in _pagaveis(doc.earnings)
	] + [
		{"descricao": r.salary_component, "remuneracao": "", "desconto": _dinheiro(r.amount)}
		for r in _pagaveis(doc.deductions)
	]

	return {
		"empresa": empresa.company_name,
		"nuit": empresa.tax_id or "",
		"logo": get_url(logo) if logo else "",
		"endereco": morada.get("endereco", ""),
		"cidade": morada.get("cidade", ""),
		"periodo": f"{MESES[inicio.month - 1]} {inicio.year}",
		"salario_mensal": _dinheiro(base_para_data(doc.employee, doc.end_date)),
		"dias_referencia": _dias(doc.total_working_days),
		"dias_remunerados": _dias(doc.payment_days),
		"faltas": cint(doc.get("custom_faltas_liquidas")),
		"linhas": linhas,
		"total_remuneracoes": _dinheiro(doc.gross_pay),
		"total_descontos": _dinheiro(doc.total_deduction),
		"liquido": _dinheiro(doc.net_pay),
	}


def _pagaveis(linhas):
	return [
		r
		for r in linhas or []
		if flt(r.amount)
		and not cint(r.get("statistical_component"))
		and not cint(r.get("do_not_include_in_total"))
	]


def _dinheiro(valor):
	return fmt_money(flt(valor), precision=2)


def _dias(valor):
	return f"{flt(valor):g}"
