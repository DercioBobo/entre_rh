"""Folha de Salário — the printable monthly payroll sheet the Administração signs.

Fixed layout modelled on the company's paper sheet (FOLHA_DE_SALARIO.pdf), built
from one company's submitted Salary Slips for one month:

	Nº · Nome · Salário Base · Dias do Mês · Dias Trab. · Venc. Mensal · <other earnings> · HE 50% (h/valor) ·
	HE 100% (h/valor) · Total Remunerações · Faltas (dias/valor) · <other deductions> ·
	IRPS · INSS · Total Deduções · Líquido

Every column whose values are all zero for the month is dropped, so the sheet only
shows what this payroll actually used.

Salário Base is the contract base (SSA effective on the slip's end date); Venc. Mensal
is the slip's base earning row, which HRMS pro-rates by payment days — so on every
row Salário Base × Dias Trab. ÷ Dias do Mês = Venc. Mensal (Dias do Mês / Dias Trab.
are the slip's own total_working_days / payment_days). Below the table, the Resumo dos Encargos:
INSS trabalhador, INSS empresa (employer rate from Settings, charged only on slips
that carry INSS — an INSS-exempt employee costs no employer share either), Total INSS,
Total IRPS, Total Encargos (INSS + IRPS, i.e. what is remitted) and Total Custos
(gross + employer INSS).

The print template (folha_de_salario.html) reads the header, layout and encargos from
the hidden `_` keys of the final (is_total) row; the on-screen grid ignores them.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from entre_hr.payroll.statutory import TAXA_INSS_EMPREGADOR, TAXA_INSS_TRABALHADOR
from entre_hr.salario import base_para_data
from entre_hr.setup_empresa import COMPONENTE_BASE
from entre_hr.utils import MESES, mes_ano_para_periodo


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.get("company") and filters.get("mes") and filters.get("ano")):
		return [], []

	settings = frappe.get_cached_doc("Entre HR Settings")
	inicio, fim = mes_ano_para_periodo(filters.mes, filters.ano)
	slips = _slips(filters.company, inicio, fim)
	if not slips:
		return [], []

	papeis = _papeis(settings)
	detalhes = _detalhes([s.name for s in slips])
	horas = _horas_extras(slips, filters.mes, filters.ano)
	taxa_emp = flt(settings.get("inss_taxa_empregador")) or TAXA_INSS_EMPREGADOR

	linhas = [
		_linha(i, slip, detalhes.get(slip.name, {}), horas.get(slip.employee, {}), papeis, taxa_emp)
		for i, slip in enumerate(slips, start=1)
	]
	layout = _layout(linhas, detalhes, papeis, settings)
	total = _total(linhas, layout)
	total.update(_meta(filters, slips, layout, total, settings, taxa_emp))

	colunas = [
		{"label": _("Nº"), "fieldname": "n", "fieldtype": "Int", "width": 50},
		{"label": _("Funcionário"), "fieldname": "funcionario", "fieldtype": "Link",
		 "options": "Employee", "width": 120},
		{"label": _("Nome"), "fieldname": "nome", "fieldtype": "Data", "width": 200},
	] + [_coluna(c) for c in layout]
	return colunas, linhas + [total], None, None, _resumo(total)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def _slips(company, inicio, fim):
	return frappe.get_all(
		"Salary Slip",
		filters={
			"docstatus": 1,
			"company": company,
			"start_date": ["between", [inicio, fim]],
		},
		fields=["name", "employee", "employee_name", "posting_date", "gross_pay",
				"total_deduction", "net_pay", "end_date", "total_working_days",
				"payment_days", "custom_faltas_liquidas"],
		order_by="employee_name asc, start_date asc",
	)


def _papeis(settings):
	"""Components that get a dedicated place on the sheet (not a generic column)."""
	return frappe._dict(
		base=COMPONENTE_BASE,
		he50=settings.get("componente_horas_extras_50"),
		he100=settings.get("componente_horas_extras_100"),
		faltas=settings.get("componente_faltas"),
		irps=settings.get("componente_irps"),
		inss=settings.get("componente_inss"),
	)


def _detalhes(nomes):
	"""{slip: {(parentfield, component): amount}}"""
	out = {}
	for row in frappe.get_all(
		"Salary Detail",
		filters={"parent": ["in", nomes], "parentfield": ["in", ["earnings", "deductions"]]},
		fields=["parent", "salary_component", "parentfield", "amount"],
	):
		comps = out.setdefault(row.parent, {})
		chave = (row.parentfield, row.salary_component)
		comps[chave] = comps.get(chave, 0.0) + flt(row.amount)
	return out


def _horas_extras(slips, mes, ano):
	"""{employee: {"horas_50": h, "horas_100": h}} from submitted Horas Extras."""
	out = {}
	for row in frappe.get_all(
		"Horas Extras",
		filters={
			"funcionario": ["in", list({s.employee for s in slips})],
			"docstatus": 1,
			"mes": mes,
			"ano": cint(ano),
		},
		fields=["funcionario", "horas_50", "horas_100"],
	):
		h = out.setdefault(row.funcionario, {"horas_50": 0.0, "horas_100": 0.0})
		h["horas_50"] += flt(row.horas_50)
		h["horas_100"] += flt(row.horas_100)
	return out


def _tributavel(componente):
	return cint(frappe.get_cached_value("Salary Component", componente, "is_tax_applicable"))


def _linha(n, slip, det, horas, papeis, taxa_emp):
	def valor(parentfield, componente):
		return flt(det.get((parentfield, componente))) if componente else 0.0

	linha = {
		"n": n,
		"funcionario": slip.employee,
		"nome": slip.employee_name,
		"base": base_para_data(slip.employee, slip.end_date),
		"dias_mes": flt(slip.total_working_days),
		"dias": flt(slip.payment_days),
		"venc_mensal": valor("earnings", papeis.base),
		"he50_horas": flt(horas.get("horas_50")),
		"he50_valor": valor("earnings", papeis.he50),
		"he100_horas": flt(horas.get("horas_100")),
		"he100_valor": valor("earnings", papeis.he100),
		"total_remuneracoes": flt(slip.gross_pay),
		"faltas_dias": cint(slip.custom_faltas_liquidas),
		"faltas_valor": valor("deductions", papeis.faltas),
		"irps": valor("deductions", papeis.irps),
		"inss": valor("deductions", papeis.inss),
		"total_deducoes": flt(slip.total_deduction),
		"liquido": flt(slip.net_pay),
	}
	dedicados = {
		("earnings", papeis.base), ("earnings", papeis.he50), ("earnings", papeis.he100),
		("deductions", papeis.faltas), ("deductions", papeis.irps), ("deductions", papeis.inss),
	}
	for (parentfield, comp), amount in det.items():
		if (parentfield, comp) not in dedicados:
			linha[_campo(parentfield, comp)] = flt(amount)

	# Employer INSS: only where the worker's INSS was charged (an exemption removes both
	# shares), on the same taxable base.
	if linha["inss"] > 0:
		base_tributavel = sum(
			flt(amount)
			for (parentfield, comp), amount in det.items()
			if parentfield == "earnings" and _tributavel(comp)
		)
		linha["_inss_empresa"] = flt(base_tributavel * taxa_emp / 100, 2)
	else:
		linha["_inss_empresa"] = 0.0
	return linha


def _campo(parentfield, componente):
	return ("r_" if parentfield == "earnings" else "d_") + frappe.scrub(componente)


# ---------------------------------------------------------------------------
# Layout (columns that survive the "drop if empty" rule)
# ---------------------------------------------------------------------------


def _layout(linhas, detalhes, papeis, settings):
	"""Ordered column specs: {fieldname, label, grupo, tipo}. `grupo` pairs the
	hours/days column with its amount under one header in print."""
	taxa_trab = flt(settings.inss_taxa_trabalhador) or TAXA_INSS_TRABALHADOR

	extras = {}
	for det in detalhes.values():
		for parentfield, comp in det:
			campo = _campo(parentfield, comp)
			if any(campo in linha for linha in linhas):
				extras[campo] = (parentfield, comp)
	outras_rem = sorted((c for c, (pf, _c) in extras.items() if pf == "earnings"),
						key=lambda c: extras[c][1])
	outras_ded = sorted((c for c, (pf, _c) in extras.items() if pf == "deductions"),
						key=lambda c: extras[c][1])

	candidatos = [
		("base", _("Salário Base"), None, "Currency"),
		("dias_mes", _("Dias do Mês"), None, "Float"),
		("dias", _("Dias Trab."), None, "Float"),
		("venc_mensal", _("Venc. Mensal"), None, "Currency"),
		*[(c, extras[c][1], None, "Currency") for c in outras_rem],
		("he50_horas", _("Horas"), _("Horas Extras 50%"), "Float"),
		("he50_valor", _("Valor"), _("Horas Extras 50%"), "Currency"),
		("he100_horas", _("Horas"), _("Horas Extras 100%"), "Float"),
		("he100_valor", _("Valor"), _("Horas Extras 100%"), "Currency"),
		("total_remuneracoes", _("Total Remunerações"), None, "Currency"),
		("faltas_dias", _("Dias"), _("Faltas"), "Int"),
		("faltas_valor", _("Valor"), _("Faltas"), "Currency"),
		*[(c, extras[c][1], None, "Currency") for c in outras_ded],
		("irps", _("IRPS"), None, "Currency"),
		("inss", _("INSS {0}%").format(_pct(taxa_trab)), None, "Currency"),
		("total_deducoes", _("Total Deduções"), None, "Currency"),
		("liquido", _("Líquido a Receber"), None, "Currency"),
	]
	sempre = {"total_remuneracoes", "total_deducoes", "liquido"}
	vivos = {f for f, *_r in candidatos if any(flt(linha.get(f)) for linha in linhas)}
	# A group shown by half reads oddly (hours without value or vice-versa): keep both.
	grupos = {grupo for f, _l, grupo, _t in candidatos if grupo and f in vivos}
	return [
		{"fieldname": f, "label": label, "grupo": grupo, "tipo": tipo}
		for f, label, grupo, tipo in candidatos
		if f in sempre or f in vivos or (grupo and grupo in grupos)
	]


def _pct(valor):
	return f"{flt(valor):g}"


def _coluna(spec):
	label = f"{spec['grupo']} — {spec['label']}" if spec["grupo"] else spec["label"]
	return {
		"label": label,
		"fieldname": spec["fieldname"],
		"fieldtype": spec["tipo"],
		"width": 120,
	}


# ---------------------------------------------------------------------------
# Totals, header and encargos
# ---------------------------------------------------------------------------


def _total(linhas, layout):
	total = {"is_total": 1, "nome": _("Total")}
	for spec in layout:
		if spec["fieldname"] in ("dias_mes", "dias"):
			continue  # per-person day counts don't add up to anything meaningful
		total[spec["fieldname"]] = sum(flt(linha.get(spec["fieldname"])) for linha in linhas)
	total["_inss_empresa"] = sum(flt(linha["_inss_empresa"]) for linha in linhas)
	return total


def _meta(filters, slips, layout, total, settings, taxa_emp):
	empresa = frappe.get_cached_doc("Company", filters.company)
	morada = _morada(filters.company)
	taxa_trab = flt(settings.inss_taxa_trabalhador) or TAXA_INSS_TRABALHADOR

	inss_trab = flt(total.get("inss"))
	inss_emp = flt(total["_inss_empresa"])
	irps = flt(total.get("irps"))
	data = max(getdate(s.posting_date) for s in slips)
	cidade = morada.get("cidade")
	return {
		"_empresa": empresa.company_name,
		"_nuit": empresa.tax_id or "",
		"_endereco": morada.get("endereco", ""),
		"_cidade": cidade or "",
		"_periodo": f"{filters.mes} {cint(filters.ano)}",
		"_local_data": "{0}aos {1} de {2} de {3}".format(
			f"{cidade}, " if cidade else "", data.day, MESES[data.month - 1], data.year
		),
		"_layout": layout,
		"_encargos": {
			"taxa_trab": _pct(taxa_trab),
			"taxa_emp": _pct(taxa_emp),
			"taxa_total": _pct(taxa_trab + taxa_emp),
			"inss_trab": inss_trab,
			"inss_emp": inss_emp,
			"inss_total": inss_trab + inss_emp,
			"irps": irps,
			"total_encargos": inss_trab + inss_emp + irps,
			"total_custos": flt(total.get("total_remuneracoes")) + inss_emp,
		},
	}


def _morada(company):
	"""The company's primary (or any) Address, as street line(s) + city."""
	from frappe.contacts.doctype.address.address import get_company_address

	nome = (get_company_address(company) or {}).get("company_address")
	if not nome:
		return {}
	a = frappe.db.get_value(
		"Address", nome, ["address_line1", "address_line2", "city"], as_dict=True
	)
	if not a:
		return {}
	return {
		"endereco": ", ".join(p for p in (a.address_line1, a.address_line2) if p),
		"cidade": a.city,
	}


def _resumo(total):
	e = total["_encargos"]
	return [
		{"label": _("Total Remunerações"), "value": total.get("total_remuneracoes"),
		 "datatype": "Currency"},
		{"label": _("Líquido a Receber"), "value": total.get("liquido"), "datatype": "Currency"},
		{"label": _("Total INSS ({0}%)").format(e["taxa_total"]), "value": e["inss_total"],
		 "datatype": "Currency"},
		{"label": _("Total IRPS"), "value": e["irps"], "datatype": "Currency"},
		{"label": _("Total Custos"), "value": e["total_custos"], "datatype": "Currency"},
	]
