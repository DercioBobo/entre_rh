"""Shared helpers and conventions for Entre HR."""

import frappe
from frappe import _
from frappe.utils import cint, get_last_day, getdate, today

# Link-filter convention: every Link -> Employee field created by this app carries
# this filter so terminated staff never appear in pickers (see BUILD_PLAN Phase 1).
EMPLOYEE_LINK_FILTERS = '[["Employee","status","!=","Left"]]'

# Roles allowed to manage salaries / run HR admin actions.
ROLES_GESTAO_RH = {"RH Manager", "System Manager"}

# Salary-advance cap (% of base salary). The cap is ALWAYS enforced: when
# Settings.adiantamento_max_percentagem is blank/0 this default applies — there is
# deliberately no "no limit" configuration.
ADIANTAMENTO_PERCENTAGEM_PADRAO = 50.0


def ensure_salary_component(nome, tipo):
	"""Return the component name, auto-creating it with the given type ('Earning' /
	'Deduction') on first use. Returns None when no name is configured."""
	if not nome:
		return None
	if not frappe.db.exists("Salary Component", nome):
		doc = frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": nome,
				"salary_component_abbr": "".join(p[0] for p in nome.split()).upper() or nome[:3].upper(),
				"type": tipo,
				"amount_based_on_formula": 0,
				"depends_on_payment_days": 0,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
	return nome

MESES = [
	"Janeiro",
	"Fevereiro",
	"Março",
	"Abril",
	"Maio",
	"Junho",
	"Julho",
	"Agosto",
	"Setembro",
	"Outubro",
	"Novembro",
	"Dezembro",
]


def mes_para_numero(mes):
	if mes not in MESES:
		frappe.throw(_("Mês inválido: {0}").format(mes))
	return MESES.index(mes) + 1


def mes_ano_para_periodo(mes, ano):
	"""(mes, ano) -> (first day, last day) of that month."""
	inicio = getdate(f"{cint(ano)}-{mes_para_numero(mes):02d}-01")
	return inicio, get_last_day(inicio)


def validar_mes_nao_passado(doc):
	"""No-past-months rule (BUILD_PLAN Phase 4; reused by Outras Deducoes in Phase 6).

	Valid: a month >= the current month in the current year, or January of next year
	only while we are in December. Anything earlier is rejected. Fires only for new
	records or when the month/year changes.
	"""
	if not (doc.is_new() or doc.has_value_changed("mes") or doc.has_value_changed("ano")):
		return

	hoje = getdate(today())
	mes = mes_para_numero(doc.mes)
	ano = cint(doc.ano)

	if ano == hoje.year and mes >= hoje.month:
		return
	if ano == hoje.year + 1 and mes == 1 and hoje.month == 12:
		return

	frappe.throw(
		_("Mês inválido: {0} de {1} já passou (ou está demasiado no futuro). Apenas o mês corrente ou meses seguintes do ano corrente são permitidos — Janeiro do próximo ano apenas em Dezembro.").format(
			doc.mes, ano
		)
	)


def calcular_faltas(employee, start, end):
	"""Net unjustified absence days for the employee in [start, end]:
	SUM(Ausencia.n_de_faltas) − SUM(Justificacao De Faltas.dias_justificados), both sides
	matched on the same employee, over submitted records whose month overlaps the period.
	Clamped at 0."""
	start, end = getdate(start), getdate(end)

	def _soma(doctype, campo):
		total = 0
		rows = frappe.get_all(
			doctype,
			filters={"funcionario": employee, "docstatus": 1},
			fields=["mes", "ano", campo],
		)
		for row in rows:
			p_inicio, p_fim = mes_ano_para_periodo(row.mes, row.ano)
			if p_inicio <= end and p_fim >= start:
				total += cint(row.get(campo))
		return total

	faltas = _soma("Ausencia", "n_de_faltas") - _soma(
		"Justificacao De Faltas", "dias_justificados"
	)
	return max(faltas, 0)
