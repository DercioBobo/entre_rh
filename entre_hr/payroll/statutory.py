"""Statutory contributions (INSS, IRPS, 13º Salário) — BUILD_PLAN Phase 7.

Every formula lives here as ONE pure, replaceable function, so dropping in the official
rates/brackets later touches this file only — never the hook wiring.

PLACEHOLDERS: the official formulas are still to be supplied. Until then:
- INSS uses the flat worker rate from Settings (0 when unset);
- IRPS walks the Settings bracket table (0 when the table is empty);
- 13º returns 0.
Do not invent statutory numbers — configure them in Entre HR Settings when provided.
"""

from frappe.utils import flt


def calcular_inss(base_tributavel, settings):
	"""Worker-side INSS on the taxable base.

	TODO: real INSS formula (official rate / any ceiling) to be supplied.
	Placeholder: flat `inss_taxa_trabalhador` percent from Settings.
	"""
	taxa = flt(settings.inss_taxa_trabalhador)
	if taxa <= 0:
		return 0.0
	return flt(base_tributavel) * taxa / 100.0


def calcular_irps(base_pos_inss, settings):
	"""IRPS withholding on the post-INSS base.

	TODO: real IRPS table/semantics to be supplied. Placeholder: progressive bracket
	walk over Settings.irps_tabela assuming the common withholding-table form
	`parcela_fixa + taxa% × (base − limite_inferior)`; 0 when no bracket matches.
	"""
	base = flt(base_pos_inss)
	for row in settings.irps_tabela or []:
		inferior = flt(row.limite_inferior)
		superior = flt(row.limite_superior)  # 0 = no upper limit (last bracket)
		if base >= inferior and (superior == 0 or base <= superior):
			return flt(row.parcela_fixa) + (base - inferior) * flt(row.taxa) / 100.0
	return 0.0


def calcular_13o(base, slip, settings):
	"""13º Salário earning for this slip.

	TODO: real rule to be supplied (amount and timing — one annual payment vs monthly
	accrual). Placeholder: 0 (no earning line is added while this returns 0).
	"""
	return 0.0
