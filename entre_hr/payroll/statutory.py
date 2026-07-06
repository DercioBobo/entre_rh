"""Statutory contributions (INSS, IRPS, 13º Salário) — BUILD_PLAN Phase 7.

Every formula lives here as ONE pure, replaceable function, so dropping in the official
rates/brackets later touches this file only — never the hook wiring.

Both INSS and IRPS are computed on the slip's TAXABLE earnings — the rows whose
Salary Component has "Is Tax Applicable" checked (ERPNext-native flag, default on;
the operator unchecks it on non-taxable bonuses/subsídios).

INSS: worker share = flat percent of taxable earnings. TAXA_INSS_TRABALHADOR (3% by
law) seeds Settings.inss_taxa_trabalhador at install; the calculation reads Settings
so a legal change is an edit there, not a deploy.

IRPS: real monthly withholding table (retenção na fonte), per number of dependents,
on the post-INSS taxable base. The calculation reads Settings.irps_tabela;
TABELA_IRPS_OFICIAL below is the install-time seed.

13º Salário: one full base salary on the slip of the configured payment month
(Settings.mes_13o_salario, seeded to Dezembro), subject to INSS and IRPS like any
taxable earning.
"""

from frappe.utils import cint, flt, getdate

from entre_hr.utils import MESES

TAXA_INSS_TRABALHADOR = 3.0  # % worker share, by law — install-time seed

MAX_DEPENDENTES = 4  # the official table tops out at "4 ou mais dependentes"

# Official monthly IRPS withholding brackets (Mozambique), per dependents count.
# Row shape: (dependentes, limite_inferior, limite_superior, taxa %, parcela_fixa).
# limite_superior 0 = no upper limit (last bracket). Below the first limite_inferior
# of a dependents group, withholding is 0.
TABELA_IRPS_OFICIAL = [
	# 0 dependentes
	(0, 20250.00, 20749.99, 10, 0),
	(0, 20750.00, 20999.99, 10, 50),
	(0, 21000.00, 21249.99, 10, 75),
	(0, 21250.00, 21749.99, 10, 100),
	(0, 21750.00, 22249.99, 10, 150),
	(0, 22250.00, 32749.99, 15, 200),
	(0, 32750.00, 60749.99, 20, 1775),
	(0, 60750.00, 144749.99, 25, 7375),
	(0, 144750.00, 0, 32, 28375),
	# 1 dependente
	(1, 20750.00, 20999.99, 10, 0),
	(1, 21000.00, 21249.99, 10, 25),
	(1, 21250.00, 21749.99, 10, 50),
	(1, 21750.00, 22249.99, 10, 100),
	(1, 22250.00, 32749.99, 15, 150),
	(1, 32750.00, 60749.99, 20, 1725),
	(1, 60750.00, 144749.99, 25, 7325),
	(1, 144750.00, 0, 32, 28325),
	# 2 dependentes
	(2, 21000.00, 21249.99, 10, 0),
	(2, 21250.00, 21749.99, 10, 25),
	(2, 21750.00, 22249.99, 10, 75),
	(2, 22250.00, 32749.99, 15, 125),
	(2, 32750.00, 60749.99, 20, 1700),
	(2, 60750.00, 144749.99, 25, 7300),
	(2, 144750.00, 0, 32, 28300),
	# 3 dependentes
	(3, 21250.00, 21749.99, 10, 0),
	(3, 21750.00, 22249.99, 10, 50),
	(3, 22250.00, 32749.99, 15, 100),
	(3, 32750.00, 60749.99, 20, 1675),
	(3, 60750.00, 144749.99, 25, 7275),
	(3, 144750.00, 0, 32, 28275),
	# 4 ou mais dependentes
	(4, 21750.00, 22249.99, 10, 0),
	(4, 22250.00, 32749.99, 15, 50),
	(4, 32750.00, 60749.99, 20, 1625),
	(4, 60750.00, 144749.99, 25, 7225),
	(4, 144750.00, 0, 32, 28225),
]


def calcular_inss(base_tributavel, settings):
	"""Worker-side INSS: `inss_taxa_trabalhador` percent (3% by law, seeded at
	install) of the taxable earnings total. No ceiling."""
	taxa = flt(settings.inss_taxa_trabalhador)
	if taxa <= 0:
		return 0.0
	return flt(base_tributavel) * taxa / 100.0


def calcular_irps(base_pos_inss, dependentes, settings):
	"""IRPS monthly withholding on the post-INSS base, per number of dependents.

	Reads Settings.irps_tabela (seeded from TABELA_IRPS_OFICIAL): within the rows for
	`min(dependentes, 4)`, applies `parcela_fixa + taxa% × (base − limite_inferior)`
	of the highest bracket whose limite_inferior ≤ base. Matching on the lower limit
	only makes the 0.01 gaps between published brackets harmless. 0 below the first
	bracket or when the table is empty.
	"""
	base = flt(base_pos_inss)
	grupo = min(max(cint(dependentes), 0), MAX_DEPENDENTES)
	escalao = None
	for row in settings.irps_tabela or []:
		if cint(row.dependentes) != grupo or base < flt(row.limite_inferior):
			continue
		if escalao is None or flt(row.limite_inferior) > flt(escalao.limite_inferior):
			escalao = row
	if escalao is None:
		return 0.0
	return (
		flt(escalao.parcela_fixa)
		+ (base - flt(escalao.limite_inferior)) * flt(escalao.taxa) / 100.0
	)


def calcular_13o(base, slip, settings):
	"""13º Salário: one FULL base salary (no proration by admission date), paid on the
	slip whose month is Settings.mes_13o_salario (seeded to Dezembro). Taxable like any
	earning — it is appended before the taxable base is computed, so INSS and IRPS of
	that month's slip include it. 0 on every other month's slip."""
	mes = settings.get("mes_13o_salario")
	if mes not in MESES or not slip.start_date:
		return 0.0
	if getdate(slip.start_date).month != MESES.index(mes) + 1:
		return 0.0
	return flt(base)
