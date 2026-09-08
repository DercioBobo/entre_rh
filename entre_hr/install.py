import frappe
from frappe.utils import flt

ROLES = ["Aprovador RH", "RH Manager"]


def after_install():
	ensure_roles()
	seed_padroes()
	backfill_idades()


def after_migrate():
	ensure_roles()
	seed_padroes()
	backfill_idades()


def backfill_idades():
	"""Fill Employee.custom_idade right away (the daily scheduler keeps it fresh
	afterwards). No-op when every age is already current."""
	from entre_hr.utils import actualizar_idades

	actualizar_idades()


def ensure_roles():
	"""Create the app's roles if missing (idempotent; fixtures also ship them)."""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role, "desk_access": 1}
			).insert(ignore_permissions=True)


# Operational components: (Settings link field, component name, component type).
# Each is created and linked only while its Settings field is empty, so an operator
# who points the field at a different component is never overridden.
COMPONENTES_PADRAO = [
	("componente_faltas", "Faltas", "Deduction"),
	("componente_retroativo", "Retroativo", "Earning"),
	("componente_emprestimo", "Emprestimo", "Deduction"),
]

ESTRUTURA_PADRAO = "Base"
COMPONENTE_BASE = "Salario Base"  # unaccented, matching "13o Salario" / "Adiantamento de Salario"


def _ensure_estrutura_base():
	"""Create + submit the default 'Base' Salary Structure and return its name.

	One earning row — the 'Salario Base' component, amount = formula `base`, which HRMS
	resolves to the employee's Salary Structure Assignment base on every slip. Taxable
	(INSS/IRPS build on it) and NOT payment-day dependent — absences are the hook's
	separate 'Faltas' deduction, so prorating base here too would deduct them twice.

	Deductions stay out: INSS, IRPS, Faltas, Emprestimo and Adiantamento are appended
	by salary_slip_hooks at assembly time. Returns None when no default company is set
	yet (the operator then points estrutura_salarial_padrao at a structure by hand)."""
	from entre_hr.utils import ensure_salary_component

	if frappe.db.exists("Salary Structure", ESTRUTURA_PADRAO):
		return ESTRUTURA_PADRAO

	import erpnext

	company = erpnext.get_default_company()
	if not company:
		return None

	componente = ensure_salary_component(
		COMPONENTE_BASE, "Earning", amount_based_on_formula=1, formula="base", is_tax_applicable=1
	)

	estrutura = frappe.new_doc("Salary Structure")
	estrutura.name = ESTRUTURA_PADRAO
	estrutura.company = company
	estrutura.is_active = "Yes"
	estrutura.payroll_frequency = "Monthly"
	moeda = frappe.get_cached_value("Company", company, "default_currency")
	if moeda:
		estrutura.currency = moeda
	estrutura.append(
		"earnings",
		{"salary_component": componente, "amount_based_on_formula": 1, "formula": "base"},
	)
	estrutura.flags.ignore_permissions = True
	estrutura.insert()
	estrutura.submit()
	return estrutura.name


def seed_padroes():
	"""Default components and statutory parameters self-configure on install/migrate.

	Statutory (INSS, IRPS, 13º) each seed only on their own first run (INSS: rate
	unset; IRPS: bracket table empty; 13º: payment month unset), so later operator
	edits — including deliberately turning one off — are never overwritten. When the
	law changes, the operator updates the rate / table / month in Settings; no deploy.

	The default "Base" Salary Structure is seeded the same way — only while
	estrutura_salarial_padrao is empty and a default company exists."""
	from entre_hr.payroll.statutory import (
		TABELA_IRPS_OFICIAL,
		TAXA_INSS_EMPREGADOR,
		TAXA_INSS_TRABALHADOR,
	)
	from entre_hr.utils import ensure_salary_component

	settings = frappe.get_doc("Entre HR Settings")
	mudou = False

	for campo, nome, tipo in COMPONENTES_PADRAO:
		if not settings.get(campo):
			settings.set(campo, ensure_salary_component(nome, tipo))
			mudou = True

	if not settings.get("estrutura_salarial_padrao"):
		estrutura = _ensure_estrutura_base()
		if estrutura:
			settings.estrutura_salarial_padrao = estrutura
			mudou = True

	if not settings.get("metodo_emprestimo"):
		settings.metodo_emprestimo = "Saldo Devedor"
		mudou = True

	if not settings.get("modo_registo_faltas"):
		settings.modo_registo_faltas = "Por Dias"
		mudou = True

	if not settings.get("componente_adiantamento"):
		from entre_hr.utils import ADIANTAMENTO_PERCENTAGEM_PADRAO

		settings.componente_adiantamento = ensure_salary_component(
			"Adiantamento de Salario", "Deduction"
		)
		if flt(settings.get("adiantamento_max_percentagem")) <= 0:
			settings.adiantamento_max_percentagem = ADIANTAMENTO_PERCENTAGEM_PADRAO
		mudou = True

	if flt(settings.inss_taxa_trabalhador) <= 0:
		settings.inss_taxa_trabalhador = TAXA_INSS_TRABALHADOR
		settings.activo_inss = 1
		if not settings.componente_inss:
			settings.componente_inss = ensure_salary_component("INSS", "Deduction")
		mudou = True

	if flt(settings.get("inss_taxa_empregador")) <= 0:
		settings.inss_taxa_empregador = TAXA_INSS_EMPREGADOR
		mudou = True

	if not settings.get("irps_tabela"):
		for dependentes, inferior, superior, taxa, fixa in TABELA_IRPS_OFICIAL:
			settings.append(
				"irps_tabela",
				{
					"dependentes": dependentes,
					"limite_inferior": inferior,
					"limite_superior": superior,
					"taxa": taxa,
					"parcela_fixa": fixa,
				},
			)
		settings.activo_irps = 1
		if not settings.componente_irps:
			settings.componente_irps = ensure_salary_component("IRPS", "Deduction")
		mudou = True

	if not settings.get("mes_13o_salario"):
		settings.mes_13o_salario = "Dezembro"
		settings.activo_13o_salario = 1
		if not settings.componente_13o_salario:
			settings.componente_13o_salario = ensure_salary_component("13o Salario", "Earning")
		mudou = True

	if mudou:
		settings.save(ignore_permissions=True)
