"""Server side of the Simulador de Salário desk page.

The page mirrors the statutory math client-side for instant feedback, but every
parameter comes from Entre HR Settings via `parametros()` — a legal change edited
in Settings updates the simulator with no deploy, and the semantics match payroll
(INSS on taxable earnings, IRPS on the post-INSS base).
"""

import frappe
from frappe.utils import cint, flt

from entre_hr.payroll.statutory import (
	MAX_DEPENDENTES,
	TAXA_INSS_EMPREGADOR,
	TAXA_INSS_TRABALHADOR,
)
from entre_hr.salario import resolver_salario_base

PAPEIS = ("System Manager", "RH Manager", "Aprovador RH")


@frappe.whitelist()
def parametros():
	"""Statutory parameters for the client-side mirror."""
	frappe.only_for(PAPEIS)
	settings = frappe.get_cached_doc("Entre HR Settings")
	return {
		"taxa_inss": flt(settings.inss_taxa_trabalhador) or TAXA_INSS_TRABALHADOR,
		"taxa_inss_empregador": flt(settings.get("inss_taxa_empregador"))
		or TAXA_INSS_EMPREGADOR,
		"max_dependentes": MAX_DEPENDENTES,
		"irps_tabela": [
			{
				"dependentes": cint(row.dependentes),
				"limite_inferior": flt(row.limite_inferior),
				"taxa": flt(row.taxa),
				"parcela_fixa": flt(row.parcela_fixa),
			}
			for row in settings.irps_tabela or []
		],
	}


def _dados(funcionario):
	return {
		"funcionario": funcionario.name,
		"nome": funcionario.employee_name or funcionario.name,
		"dependentes": min(cint(funcionario.custom_numero_de_dependentes), MAX_DEPENDENTES),
		"base": flt(resolver_salario_base(funcionario.name)),
	}


@frappe.whitelist()
def dados_funcionario(funcionario):
	"""One employee's simulation inputs: resolved base salary + dependents."""
	frappe.only_for(PAPEIS)
	row = frappe.get_doc("Employee", funcionario)
	return _dados(row)


@frappe.whitelist()
def funcionarios_activos():
	"""All active employees with their simulation inputs, for the Folha tab."""
	frappe.only_for(PAPEIS)
	rows = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "custom_numero_de_dependentes"],
		order_by="employee_name asc",
	)
	return [_dados(row) for row in rows]
