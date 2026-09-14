"""Shared helpers and conventions for Entre HR."""

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_last_day, getdate, today

# Link-filter convention: every Link -> Employee field created by this app carries
# this filter so terminated staff never appear in pickers (see BUILD_PLAN Phase 1).
EMPLOYEE_LINK_FILTERS = '[["Employee","status","!=","Left"]]'

# Roles allowed to manage salaries / run HR admin actions.
ROLES_GESTAO_RH = {"RH Manager", "System Manager"}

# Salary-advance cap (% of base salary). The cap is ALWAYS enforced: when
# Settings.adiantamento_max_percentagem is blank/0 this default applies — there is
# deliberately no "no limit" configuration.
ADIANTAMENTO_PERCENTAGEM_PADRAO = 50.0


def calcular_idade(data_nascimento, em=None):
	"""Complete years between `data_nascimento` and `em` (default: today)."""
	if not data_nascimento:
		return None
	nascimento = getdate(data_nascimento)
	referencia = getdate(em or today())
	return (
		referencia.year
		- nascimento.year
		- ((referencia.month, referencia.day) < (nascimento.month, nascimento.day))
	)


def definir_idade(doc, method=None):
	"""Employee.validate doc_event: keep custom_idade in sync the moment the birth
	date is entered or changed."""
	doc.custom_idade = calcular_idade(doc.date_of_birth)


def actualizar_idades():
	"""Daily scheduler: refresh Employee.custom_idade, writing only the rows whose
	age actually changed (i.e. the day after a birthday), so the job is a no-op on
	most days."""
	rows = frappe.get_all(
		"Employee",
		filters={"date_of_birth": ["is", "set"]},
		fields=["name", "date_of_birth", "custom_idade"],
	)
	for row in rows:
		idade = calcular_idade(row.date_of_birth)
		if idade != cint(row.custom_idade):
			frappe.db.set_value("Employee", row.name, "custom_idade", idade, update_modified=False)


def nome_estrutura_base(company):
	"""Canonical name of a company's default Salary Structure: 'Base - <abbr>'."""
	abbr = frappe.get_cached_value("Company", company, "abbr") or company
	return f"Base - {abbr}"


def herdar_empresa(doc):
	"""Employee-primary doctypes carry a read-only `company` fetched from the
	employee. `fetch_from` handles the desk; this stamps it server-side too, so
	records created via API/scripts and older rows stay consistent. Call from
	validate()."""
	if doc.get("funcionario"):
		doc.company = frappe.db.get_value("Employee", doc.funcionario, "company")


def ensure_salary_component(nome, tipo, **campos):
	"""Return the component name, auto-creating it with the given type ('Earning' /
	'Deduction') on first use. Returns None when no name is configured.

	`campos` overrides fields on the created doc (e.g. amount_based_on_formula=1,
	formula="base"); it is ignored when the component already exists."""
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
				**campos,
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


def derivar_periodo_pagamento(doc):
	"""Shared by Outras Deducoes / Outras Remuneracoes: apply the Tipo de Pagamento
	rule (Único = exactly 1 month, forced; Periódico = 2+), derive the date bounds,
	and resolve the amounts according to Base de Cálculo:
	- "Valor Mensal" (default): valor_total = valor_mensal × meses;
	- "Valor Total": the operator knows the total owed (e.g. damage of 15000) and the
	  months; valor_mensal = total / meses (2 decimals). The FINAL month's installment
	  absorbs the rounding remainder (see prestacao_do_mes) so the sum is exact.
	Mirrored live in JS (entre_hr.periodo) — this server side is authoritative."""
	if cint(doc.numero_de_meses) < 1:
		frappe.throw(_("Número de Meses deve ser pelo menos 1."))

	# Records from before the field existed: infer from the month count.
	if not doc.get("tipo_de_pagamento"):
		doc.tipo_de_pagamento = "Único" if cint(doc.numero_de_meses) == 1 else "Periódico"

	if doc.tipo_de_pagamento == "Único":
		doc.numero_de_meses = 1
	elif cint(doc.numero_de_meses) < 2:
		frappe.throw(
			_("Pagamento Periódico requer Número de Meses de pelo menos 2 — para um só mês use o tipo Único.")
		)

	meses = cint(doc.numero_de_meses)
	if doc.get("base_de_calculo") == "Valor Total":
		if flt(doc.valor_total) <= 0:
			frappe.throw(_("Valor Total deve ser maior que zero."))
		doc.valor_mensal = flt(flt(doc.valor_total) / meses, 2)
	else:
		if flt(doc.valor_mensal) <= 0:
			frappe.throw(_("Valor Mensal deve ser maior que zero."))
		doc.valor_total = flt(flt(doc.valor_mensal) * meses, 2)

	inicio, _fim = mes_ano_para_periodo(doc.mes, doc.ano)
	doc.data_de_inicio = inicio
	doc.data_de_fim = get_last_day(add_months(inicio, meses - 1))

	# Payment tracking (written by salary_slip_hooks on slip submit/cancel).
	doc.valor_pago = flt(doc.get("valor_pago"))
	doc.valor_pendente = flt(doc.valor_total) - doc.valor_pago
	doc.status = "Pago" if doc.valor_pendente <= 0.005 else "Em Curso"


def prestacao_do_mes(row, data_referencia):
	"""Installment a schedule row contributes to the month containing
	`data_referencia`: valor_mensal, except the FINAL month of a multi-month
	schedule, which pays valor_total − valor_mensal × (n−1) so the installments sum
	exactly to valor_total despite the 2-decimal rounding of valor_mensal.
	Rows from before valor_total existed fall back to valor_mensal."""
	meses = cint(row.numero_de_meses)
	if (
		meses > 1
		and flt(row.valor_total) > 0
		and row.data_de_fim
		and getdate(row.data_de_fim) <= getdate(data_referencia)
	):
		return flt(flt(row.valor_total) - flt(row.valor_mensal) * (meses - 1), 2)
	return flt(row.valor_mensal)


def validar_mes_nao_futuro(doc, campo_mes="mes", campo_ano="ano"):
	"""No-future-months rule (BUILD_PLAN Phase 4; reused across Ausencia, Horas Extras,
	Outras Deducoes/Remuneracoes, Justificacao De Faltas and Reclamacao De Salario).

	Valid: the current month or any past month — a record can never be dated for a
	month that hasn't arrived yet. Fires only for new records or when the month/year
	changes. `campo_mes`/`campo_ano` let callers whose fields aren't named mes/ano
	(e.g. Reclamacao De Salario's mes_reclamacao/ano_reclamacao) reuse this as-is.
	"""
	if not (
		doc.is_new()
		or doc.has_value_changed(campo_mes)
		or doc.has_value_changed(campo_ano)
	):
		return

	hoje = getdate(today())
	mes_valor = doc.get(campo_mes)
	ano_valor = doc.get(campo_ano)
	mes = mes_para_numero(mes_valor)
	ano = cint(ano_valor)

	if (ano, mes) > (hoje.year, hoje.month):
		frappe.throw(
			_("Mês inválido: {0} de {1} ainda não chegou. Apenas o mês corrente ou meses anteriores são permitidos.").format(
				mes_valor, ano
			)
		)


def soma_submetido(doctype, campo, filters):
	"""SUM(campo) over submitted (docstatus=1) rows of `doctype` matching `filters`."""
	rows = frappe.get_all(doctype, filters={**filters, "docstatus": 1}, fields=[f"sum({campo}) as total"])
	return cint(rows[0].total) if rows else 0


def calcular_faltas_detalhado(employee, start, end):
	"""(faltas registadas, faltas justificadas, faltas líquidas) for the employee in
	[start, end]: registadas = SUM(Ausencia.n_de_faltas); justificadas =
	SUM(Justificacao De Faltas.dias_justificados), capped at registadas (a justification
	can never offset more than was actually recorded); líquidas = registadas −
	justificadas. Both sums are over submitted records whose month overlaps the period."""
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

	registadas = _soma("Ausencia", "n_de_faltas")
	justificadas = min(_soma("Justificacao De Faltas", "dias_justificados"), registadas)
	return registadas, justificadas, max(registadas - justificadas, 0)
