import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class SubsidioFixo(Document):
	"""A recurring earning paid to every employee of one company, added to each
	Salary Slip by salary_slip_hooks._add_subsidios_fixos while `activo`. The amount
	is per company; taxability comes from the Salary Component itself (a taxable one
	flows into the INSS/IRPS base). Turn it off with `activo` rather than deleting,
	so history stays readable."""

	def validate(self):
		if flt(self.valor) <= 0:
			frappe.throw(_("Valor Mensal deve ser maior que zero."))

		if frappe.db.get_value("Salary Component", self.componente, "type") != "Earning":
			frappe.throw(
				_("O componente {0} não é uma Remuneração (Earning).").format(self.componente)
			)

		duplicado = frappe.db.exists(
			"Subsidio Fixo",
			{
				"company": self.company,
				"componente": self.componente,
				"name": ["!=", self.name or ""],
			},
		)
		if duplicado:
			frappe.throw(
				_("Já existe um Subsídio Fixo de {0} para {1} ({2}). Edite esse registo.").format(
					self.componente, self.company, duplicado
				)
			)


@frappe.whitelist()
def aplicar_a_todas(componente, valor, descricao=None):
	"""Create a Subsídio Fixo for this component in every company that doesn't have
	one yet. Existing records (any amount) are left untouched."""
	if not frappe.has_permission("Subsidio Fixo", "create"):
		frappe.throw(_("Sem permissão."), frappe.PermissionError)

	criados = []
	for company in frappe.get_all("Company", pluck="name"):
		if frappe.db.exists(
			"Subsidio Fixo", {"company": company, "componente": componente}
		):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Subsidio Fixo",
				"company": company,
				"componente": componente,
				"valor": flt(valor),
				"descricao": descricao,
			}
		)
		doc.insert()
		criados.append(doc.name)
	return criados
