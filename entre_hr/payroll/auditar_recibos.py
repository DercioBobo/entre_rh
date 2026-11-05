"""Read-only audit: submitted slips whose base salary differs from the "Dias do Mês" rule.

Rule: salary ÷ the month's real days (28-31) × days paid. Slips processed while HRMS
excluded weekends and holidays from its day count were pro-rated differently, which
only affects partial months (admission, exit, unpaid leave).

Nothing is written. Run it with:

	bench --site <site> execute entre_hr.payroll.auditar_recibos.listar
	bench --site <site> execute entre_hr.payroll.auditar_recibos.listar --kwargs "{'company': 'Fagioli Mozambique Limitada'}"
"""

import frappe
from frappe.utils import cint, date_diff, flt, get_last_day, getdate

from entre_hr.payroll.statutory import calcular_inss, calcular_irps
from entre_hr.salario import base_para_data
from entre_hr.setup_empresa import COMPONENTE_BASE


def listar(company=None):
	settings = frappe.get_cached_doc("Entre HR Settings")
	if settings.divisor_dias == "Dias Úteis":
		frappe.throw("Esta auditoria só se aplica quando o Divisor de Dias é 'Dias do Mês'.")

	filtros = {"docstatus": 1}
	if company:
		filtros["company"] = company
	nomes = frappe.get_all(
		"Salary Slip", filters=filtros, pluck="name", order_by="employee asc, start_date asc"
	)

	resultados = []
	for nome in nomes:
		r = _avaliar(frappe.get_doc("Salary Slip", nome), settings)
		if r:
			resultados.append(r)

	_imprimir(len(nomes), resultados)


def _avaliar(slip, settings):
	"""The slip's current vs. expected figures, or None when it is already right."""
	linhas_base = [r for r in slip.earnings if r.salary_component == COMPONENTE_BASE]
	if not linhas_base:
		return None
	base_actual = sum(flt(r.amount) for r in linhas_base)

	func = frappe.db.get_value(
		"Employee",
		slip.employee,
		["date_of_joining", "relieving_date", "custom_isento_inss", "custom_isento_irps",
		 "custom_numero_de_dependentes"],
		as_dict=True,
	)
	dias_mes = get_last_day(slip.start_date).day
	dias = _dias_a_pagar(slip, func)
	salario = base_para_data(slip.employee, slip.end_date)
	base_nova = flt(salario * dias / dias_mes, 2)
	if abs(base_nova - base_actual) < 0.01:
		return None

	tributavel = base_nova - base_actual + sum(
		flt(r.amount)
		for r in slip.earnings
		if cint(frappe.get_cached_value("Salary Component", r.salary_component, "is_tax_applicable"))
	)
	inss_actual = _deducao(slip, settings.componente_inss)
	irps_actual = _deducao(slip, settings.componente_irps)
	inss_novo = irps_novo = 0.0
	if cint(settings.activo_inss) and not cint(func.custom_isento_inss):
		inss_novo = flt(calcular_inss(tributavel, settings), 2)
	if cint(settings.activo_irps) and not cint(func.custom_isento_irps):
		irps_novo = flt(
			calcular_irps(tributavel, cint(func.custom_numero_de_dependentes), settings), 2
		)

	bruto_novo = flt(slip.gross_pay) - base_actual + base_nova
	deducoes_novas = flt(slip.total_deduction) - inss_actual - irps_actual + inss_novo + irps_novo
	return {
		"recibo": slip.name,
		"funcionario": slip.employee_name,
		"periodo": str(slip.start_date)[:7],
		"dias": f"{flt(slip.payment_days):g}/{flt(slip.total_working_days):g} -> {dias:g}/{dias_mes}",
		"base": (base_actual, base_nova),
		"irps": (irps_actual, irps_novo),
		"inss": (inss_actual, inss_novo),
		"liquido": (flt(slip.net_pay), flt(bruto_novo - deducoes_novas, 2)),
		"payroll_entry": slip.get("payroll_entry") or "",
		"lancamentos": _lancamentos(slip.get("payroll_entry")),
	}


def _dias_a_pagar(slip, func):
	"""Calendar days of the period the employee was on staff, less unpaid days."""
	inicio, fim = getdate(slip.start_date), getdate(slip.end_date)
	if func.date_of_joining:
		inicio = max(inicio, getdate(func.date_of_joining))
	if func.relieving_date:
		fim = min(fim, getdate(func.relieving_date))
	dias = date_diff(fim, inicio) + 1 - flt(slip.get("leave_without_pay")) - flt(slip.get("absent_days"))
	return max(dias, 0)


def _deducao(slip, componente):
	return sum(flt(r.amount) for r in slip.deductions if r.salary_component == componente)


def _lancamentos(payroll_entry):
	"""Submitted Journal Entries booked against the slip's Payroll Entry."""
	if not payroll_entry:
		return []
	return sorted(
		set(
			frappe.get_all(
				"Journal Entry Account",
				filters={
					"reference_type": "Payroll Entry",
					"reference_name": payroll_entry,
					"docstatus": 1,
				},
				pluck="parent",
			)
		)
	)


def _imprimir(analisados, resultados):
	print(f"Recibos submetidos analisados: {analisados}. A corrigir: {len(resultados)}.")
	for r in resultados:
		print(f"\n{r['recibo']} | {r['funcionario']} | {r['periodo']} | Dias {r['dias']}")
		for rotulo, chave in (("Venc. Mensal", "base"), ("IRPS", "irps"), ("INSS", "inss"),
							  ("Liquido", "liquido")):
			actual, novo = r[chave]
			print(f"  {rotulo:<13}{actual:>14,.2f} -> {novo:>14,.2f}")
		print(f"  Payroll Entry: {r['payroll_entry'] or '-'}")
		print(f"  Lancamentos:   {', '.join(r['lancamentos']) or '-'}")
