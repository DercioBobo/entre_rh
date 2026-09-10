"""Saldos de Férias — per-employee annual-leave position from the Leave Ledger.

The bookable balance is the SUM of the employee's Leave Ledger Entries — never
`Leave Allocation.total_leaves_allocated`. It is broken down as:

    Saldo = Acumulado − Expirado − Gozado − Agendado

- **Acumulado**  — every accrual entry (transaction_type "Leave Allocation", is_expired 0)
                    dated up to the reference date.
- **Expirado**   — anniversary cap trims (is_expired 1), shown positive.
- **Gozado**     — approved Leave Applications that have already started (from_date < ref).
- **Agendado**   — approved Leave Applications still in the future (already deducted from
                   the balance, just not yet taken).
- **Pendente**   — draft Leave Applications, NOT yet in the ledger. "Saldo s/ Pendentes"
                   is Saldo − Pendente, i.e. the balance if every pending request is approved.
- **Provisão**   — rough Metical liability: Saldo ÷ 30 × base salary (30 dias de férias =
                   um salário base).
"""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, today

from entre_hr.ferias import _meses_completos, get_settings
from entre_hr.salario import resolver_salario_base

DIVISOR_PROVISAO = 30.0


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.get("data_referencia") or today())
	leave_type = filters.get("leave_type") or get_settings().leave_type_ferias
	if not leave_type:
		frappe.throw(_("Defina o Tipo de Licença (Férias) em Entre HR Settings ou escolha um no filtro."))

	funcionarios = _funcionarios(filters)
	if not funcionarios:
		return _colunas(), []

	nomes = [f.name for f in funcionarios]
	ledger = _ledger_por_funcionario(nomes, leave_type, as_of)
	apps = _aplicacoes_por_funcionario(nomes, leave_type, as_of)

	linhas = []
	for f in funcionarios:
		lg = ledger.get(f.name, {})
		ap = apps.get(f.name, {})

		acumulado = flt(lg.get("acumulado"), 2)
		expirado = flt(lg.get("expirado"), 2)
		gozado = flt(ap.get("gozado"), 2)
		agendado = flt(ap.get("agendado"), 2)
		pendente = flt(ap.get("pendente"), 2)
		saldo = flt(acumulado - expirado - gozado - agendado, 2)

		ancora = f.custom_data_antiguidade_ferias or f.date_of_joining
		meses = _meses_completos(getdate(ancora), as_of) if ancora else 0
		base = resolver_salario_base(f.name)

		linhas.append(
			{
				"funcionario": f.name,
				"nome": f.employee_name,
				"empresa": f.company,
				"antiguidade": getdate(ancora) if ancora else None,
				"meses_servico": meses,
				"taxa": _("2,5 dias/mês") if meses >= 12 else _("1 dia/mês"),
				"acumulado": acumulado,
				"expirado": expirado,
				"gozado": gozado,
				"agendado": agendado,
				"saldo": saldo,
				"saldo_projectado": flt(saldo - pendente, 2),
				"pendente": pendente,
				"agendado_datas": ap.get("agendado_datas", ""),
				"pendente_datas": ap.get("pendente_datas", ""),
				"provisao": flt(saldo / DIVISOR_PROVISAO * base, 2) if base else 0.0,
			}
		)

	return _colunas(), linhas, None, None, _resumo(linhas)


def _funcionarios(filters):
	cond = {}
	if not filters.get("incluir_inactivos"):
		cond["status"] = "Active"
	if filters.get("company"):
		cond["company"] = filters.company
	if filters.get("funcionario"):
		cond["name"] = filters.funcionario
	return frappe.get_all(
		"Employee",
		filters=cond,
		fields=[
			"name",
			"employee_name",
			"company",
			"date_of_joining",
			"custom_data_antiguidade_ferias",
		],
		order_by="company asc, employee_name asc",
	)


def _ledger_por_funcionario(nomes, leave_type, as_of):
	"""Accrued / expired days per employee, from the accrual side of the Leave Ledger."""
	out = {}
	for r in frappe.get_all(
		"Leave Ledger Entry",
		filters={
			"employee": ["in", nomes],
			"leave_type": leave_type,
			"docstatus": 1,
			"transaction_type": "Leave Allocation",
			"from_date": ["<=", as_of],
		},
		fields=["employee", "leaves", "is_expired"],
	):
		d = out.setdefault(r.employee, {"acumulado": 0.0, "expirado": 0.0})
		if r.is_expired:
			d["expirado"] += -flt(r.leaves)  # stored negative → show positive
		else:
			d["acumulado"] += flt(r.leaves)
	return out


def _aplicacoes_por_funcionario(nomes, leave_type, as_of):
	"""Taken / scheduled / pending days per employee, with a compact date list for the
	scheduled and pending buckets."""
	out = {}
	for r in frappe.get_all(
		"Leave Application",
		filters={
			"employee": ["in", nomes],
			"leave_type": leave_type,
			"docstatus": ["<", 2],
		},
		fields=["employee", "from_date", "to_date", "total_leave_days", "docstatus"],
		order_by="from_date asc",
	):
		d = out.setdefault(
			r.employee,
			{
				"gozado": 0.0,
				"agendado": 0.0,
				"pendente": 0.0,
				"agendado_datas": [],
				"pendente_datas": [],
			},
		)
		dias = flt(r.total_leave_days)
		etiqueta = "{0}–{1} ({2:g}d)".format(
			formatdate(r.from_date, "dd/MM"), formatdate(r.to_date, "dd/MM"), dias
		)
		if r.docstatus == 1:
			if getdate(r.from_date) >= as_of:
				d["agendado"] += dias
				d["agendado_datas"].append(etiqueta)
			else:
				d["gozado"] += dias
		else:
			d["pendente"] += dias
			d["pendente_datas"].append(etiqueta)

	for d in out.values():
		d["agendado_datas"] = " | ".join(d["agendado_datas"])
		d["pendente_datas"] = " | ".join(d["pendente_datas"])
	return out


def _colunas():
	def c(fieldname, label, fieldtype, width, **extra):
		return dict(fieldname=fieldname, label=_(label), fieldtype=fieldtype, width=width, **extra)

	return [
		c("funcionario", "Funcionário", "Link", 120, options="Employee"),
		c("nome", "Nome", "Data", 180),
		c("empresa", "Empresa", "Link", 130, options="Company"),
		c("antiguidade", "Antiguidade", "Date", 100),
		c("meses_servico", "Meses", "Int", 70),
		c("taxa", "Taxa", "Data", 100),
		c("acumulado", "Acumulado", "Float", 100, precision=2),
		c("expirado", "Expirado", "Float", 90, precision=2),
		c("gozado", "Gozado", "Float", 90, precision=2),
		c("agendado", "Agendado", "Float", 90, precision=2),
		c("saldo", "Saldo", "Float", 90, precision=2),
		c("saldo_projectado", "Saldo s/ Pendentes", "Float", 120, precision=2),
		c("pendente", "Pendente", "Float", 90, precision=2),
		c("agendado_datas", "Férias Agendadas", "Data", 210),
		c("pendente_datas", "Pedidos Pendentes", "Data", 210),
		c("provisao", "Provisão (MZN)", "Currency", 130),
	]


def _resumo(linhas):
	def total(chave):
		return flt(sum(flt(l[chave]) for l in linhas), 2)

	return [
		{"label": _("Funcionários"), "value": len(linhas), "datatype": "Int"},
		{"label": _("Saldo Total (dias)"), "value": total("saldo"), "datatype": "Float"},
		{"label": _("Agendado (dias)"), "value": total("agendado"), "datatype": "Float"},
		{"label": _("Pendente (dias)"), "value": total("pendente"), "datatype": "Float"},
		{"label": _("Provisão Total"), "value": total("provisao"), "datatype": "Currency"},
	]
