import frappe
from frappe.utils import flt

ROLES = ["Aprovador RH", "RH Manager"]


def after_install():
	ensure_roles()
	seed_padroes()
	backfill_idades()
	backfill_empresa()


def after_migrate():
	ensure_roles()
	seed_padroes()
	backfill_idades()
	backfill_empresa()


def backfill_idades():
	"""Fill Employee.custom_idade right away (the daily scheduler keeps it fresh
	afterwards). No-op when every age is already current."""
	from entre_hr.utils import actualizar_idades

	actualizar_idades()


# Employee-primary doctypes that carry a denormalized `company` (fetched from the
# employee) for filtering, reports and per-company User Permissions.
DOCTYPES_COM_EMPRESA = (
	"Ausencia",
	"Justificacao De Faltas",
	"Emprestimo",
	"Outras Deducoes",
	"Outras Remuneracoes",
	"Adiantamento De Salario",
	"Reclamacao De Salario",
)


def backfill_empresa():
	"""Stamp `company` on rows created before the field existed. No-op once filled."""
	for doctype in DOCTYPES_COM_EMPRESA:
		rows = frappe.get_all(
			doctype,
			filters={"company": ["in", ("", None)], "funcionario": ["is", "set"]},
			fields=["name", "funcionario"],
		)
		for row in rows:
			empresa = frappe.db.get_value("Employee", row.funcionario, "company")
			if empresa:
				frappe.db.set_value(
					doctype, row.name, "company", empresa, update_modified=False
				)


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
	law changes, the operator updates the rate / table / month in Settings; no deploy.

	Per-company payroll setup (Salary Structure, GL accounts, component mappings,
	holiday list) is handled by entre_hr.setup_empresa, looped over every company at
	the end of this function."""
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

	# Per-company payroll bootstrap — needs the components seeded above to already exist.
	from entre_hr.setup_empresa import configurar_todas

	configurar_todas()

	if not settings.estrutura_salarial_padrao:
		# Site-wide fallback for estrutura_para(): the default company's structure.
		padrao = frappe.db.get_single_value("Global Defaults", "default_company")
		if not padrao and frappe.db.count("Company") == 1:
			padrao = frappe.db.get_value("Company", {}, "name")
		if padrao:
			from entre_hr.utils import nome_estrutura_base

			estrutura = nome_estrutura_base(padrao)
			if frappe.db.exists("Salary Structure", estrutura):
				frappe.db.set_single_value(
					"Entre HR Settings", "estrutura_salarial_padrao", estrutura
				)
