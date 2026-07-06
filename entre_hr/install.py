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



def seed_padroes():
	"""Default components and statutory parameters self-configure on install/migrate.

	Statutory (INSS, IRPS, 13º) each seed only on their own first run (INSS: rate
	unset; IRPS: bracket table empty; 13º: payment month unset), so later operator
	edits — including deliberately turning one off — are never overwritten. When the
	law changes, the operator updates the rate / table / month in Settings; no deploy."""
	from entre_hr.payroll.statutory import TABELA_IRPS_OFICIAL, TAXA_INSS_TRABALHADOR
	from entre_hr.utils import ensure_salary_component

	settings = frappe.get_doc("Entre HR Settings")
	mudou = False

	for campo, nome, tipo in COMPONENTES_PADRAO:
		if not settings.get(campo):
			settings.set(campo, ensure_salary_component(nome, tipo))
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
