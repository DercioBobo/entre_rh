"""Salary Slip auto-assembly — BUILD_PLAN Phases 5 & 6.

Wired via doc_events (before_insert / before_validate / before_submit, plus
on_submit / on_cancel for the Reclamação applied-marker), gated by Settings.folha_activo.
Every computation is keyed on the slip's `employee`.

Idempotent assembly: every row this app adds is tagged via the hidden Salary Detail
field `custom_origem_entre_hr`. Each run strips all tagged rows and re-adds them fresh,
so structure-defined rows are never touched, cancelled sources vanish from drafts, and
re-validation never duplicates.
"""

from datetime import date

import frappe
from frappe.utils import cint, flt, get_last_day, getdate

from entre_hr.payroll.statutory import calcular_13o, calcular_inss, calcular_irps
from entre_hr.salario import base_para_data
from entre_hr.utils import calcular_faltas, ensure_salary_component

ORIGEM = "entre_hr"


def before_insert(doc, method=None):
	_assemble(doc)


def before_validate(doc, method=None):
	_assemble(doc)


def before_submit(doc, method=None):
	# Re-run so the slip is fresh even if source documents changed since the last save.
	_assemble(doc)


def on_submit(doc, method=None):
	_marcar_reclamacoes(doc)


def on_cancel(doc, method=None):
	_desmarcar_reclamacoes(doc)


def _settings():
	return frappe.get_cached_doc("Entre HR Settings")


def _assemble(slip):
	settings = _settings()
	if not cint(settings.folha_activo):
		return
	if not (slip.employee and slip.start_date and slip.end_date):
		return

	_clear_managed(slip)

	# 1. Base from the latest submitted SSA effective for the period.
	base = base_para_data(slip.employee, slip.end_date)

	# 2. Divisor from Settings.divisor_dias.
	divisor = _divisor(settings, slip)
	slip.custom_dias_de_trabalho = divisor

	# 3. Net faltas in the slip period.
	faltas = calcular_faltas(slip.employee, slip.start_date, slip.end_date)
	slip.custom_dias_trabalhados = max(divisor - faltas, 0)

	# 4. Managed components.
	_add_faltas(slip, settings, base, divisor, faltas)
	_add_deducoes(slip)
	_add_remuneracoes(slip)
	_add_emprestimos(slip, settings)
	_add_reclamacoes(slip, settings)

	# 5. Statutory — after all earnings are in, so the taxable base is complete.
	_add_estatutarios(slip, settings, base)


def _divisor(settings, slip):
	"""'Dias do Mês' = calendar days of the slip's month; 'Dias Úteis' = its Mon-Fri days."""
	inicio = getdate(slip.start_date)
	ultimo = get_last_day(inicio)
	if settings.divisor_dias == "Dias Úteis":
		return sum(
			1
			for d in range(1, ultimo.day + 1)
			if date(inicio.year, inicio.month, d).weekday() < 5
		)
	return ultimo.day


# ---------------------------------------------------------------------------
# Managed-row plumbing
# ---------------------------------------------------------------------------


def _clear_managed(slip):
	for parentfield in ("earnings", "deductions"):
		slip.set(
			parentfield,
			[d for d in slip.get(parentfield) or [] if not d.get("custom_origem_entre_hr")],
		)


def _append_managed(slip, parentfield, componente, amount):
	"""Append one tagged component row (only when the component exists and amount > 0)."""
	if not componente or not frappe.db.exists("Salary Component", componente):
		return  # skip silently (per spec)
	if flt(amount) <= 0:
		return
	slip.append(
		parentfield,
		{
			"salary_component": componente,
			"amount": flt(amount),
			"amount_based_on_formula": 0,
			"depends_on_payment_days": 0,
			"custom_origem_entre_hr": ORIGEM,
		},
	)


# ---------------------------------------------------------------------------
# Component adders
# ---------------------------------------------------------------------------


def _add_faltas(slip, settings, base, divisor, faltas):
	if settings.metodo_calculo_faltas == "Valor Fixo por Falta":
		amount = flt(faltas) * flt(settings.valor_fixo_por_falta)
	else:  # Proporcional ao Salário
		amount = (flt(base) / divisor * flt(faltas)) if divisor else 0.0
	_append_managed(slip, "deductions", settings.componente_faltas, amount)


def _covering(doctype, slip, extra_filters=None):
	filters = {
		"funcionario": slip.employee,
		"docstatus": 1,
		"data_de_inicio": ["<=", slip.end_date],
		"data_de_fim": [">=", slip.start_date],
	}
	filters.update(extra_filters or {})
	return filters


def _add_deducoes(slip):
	"""Outras Deducoes: component read verbatim from `tipo`, summed per component."""
	rows = frappe.get_all(
		"Outras Deducoes",
		filters=_covering("Outras Deducoes", slip),
		fields=["tipo", "valor_mensal"],
	)
	por_componente = {}
	for row in rows:
		por_componente[row.tipo] = por_componente.get(row.tipo, 0.0) + flt(row.valor_mensal)
	for componente, amount in por_componente.items():
		_append_managed(slip, "deductions", componente, amount)


def _add_remuneracoes(slip):
	"""Outras Remuneracoes: earnings mirror, de-duplicated per component."""
	rows = frappe.get_all(
		"Outras Remuneracoes",
		filters=_covering("Outras Remuneracoes", slip),
		fields=["tipo_de_subsidios", "valor_mensal"],
	)
	por_componente = {}
	for row in rows:
		por_componente[row.tipo_de_subsidios] = (
			por_componente.get(row.tipo_de_subsidios, 0.0) + flt(row.valor_mensal)
		)
	for componente, amount in por_componente.items():
		_append_managed(slip, "earnings", componente, amount)


def _add_emprestimos(slip, settings):
	"""Emprestimo: sum of active, date-covering monthly installments."""
	rows = frappe.get_all(
		"Emprestimo",
		filters=_covering("Emprestimo", slip),
		fields=["valor_mensal"],
	)
	total = sum(flt(r.valor_mensal) for r in rows)
	_append_managed(slip, "deductions", settings.componente_emprestimo, total)


def _reclamacoes_pendentes(employee):
	return frappe.get_all(
		"Reclamacao De Salario",
		filters={
			"funcionario": employee,
			"docstatus": 1,
			"aplicado_em": ["is", "not set"],
		},
		fields=["name", "valor_reclamado"],
	)


def _add_reclamacoes(slip, settings):
	"""Reclamacao De Salario: pending (unapplied) claims land on this slip as retroativo."""
	rows = _reclamacoes_pendentes(slip.employee)
	total = sum(flt(r.valor_reclamado) for r in rows)
	_append_managed(slip, "earnings", settings.componente_retroativo, total)


def _add_estatutarios(slip, settings, base):
	"""INSS, IRPS (on the post-INSS base) and 13º Salário — BUILD_PLAN Phase 7.

	Each is gated by its Settings flag; components are auto-created with the right type
	on first use. The formulas live in entre_hr.payroll.statutory (placeholders until
	the official rules are supplied)."""
	base_tributavel = sum(flt(e.amount) for e in slip.get("earnings") or [])

	inss = 0.0
	if cint(settings.activo_inss):
		componente = ensure_salary_component(settings.componente_inss, "Deduction")
		inss = calcular_inss(base_tributavel, settings)
		_append_managed(slip, "deductions", componente, inss)

	if cint(settings.activo_irps):
		componente = ensure_salary_component(settings.componente_irps, "Deduction")
		irps = calcular_irps(base_tributavel - inss, settings)
		_append_managed(slip, "deductions", componente, irps)

	if cint(settings.activo_13o_salario):
		componente = ensure_salary_component(settings.componente_13o_salario, "Earning")
		decimo_terceiro = calcular_13o(base, slip, settings)
		_append_managed(slip, "earnings", componente, decimo_terceiro)


def _marcar_reclamacoes(slip):
	"""On slip submit: mark the pending claims it paid, so they are never paid twice."""
	settings = _settings()
	if not cint(settings.folha_activo):
		return
	for row in _reclamacoes_pendentes(slip.employee):
		frappe.db.set_value(
			"Reclamacao De Salario", row.name, "aplicado_em", slip.name, update_modified=False
		)


def _desmarcar_reclamacoes(slip):
	"""On slip cancel: release its claims so the next slip picks them up again."""
	for name in frappe.get_all(
		"Reclamacao De Salario",
		filters={"aplicado_em": slip.name},
		pluck="name",
	):
		frappe.db.set_value(
			"Reclamacao De Salario", name, "aplicado_em", None, update_modified=False
		)
