import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from entre_hr.salario import base_para_data, get_settings
from entre_hr.utils import ADIANTAMENTO_PERCENTAGEM_PADRAO


class AdiantamentoDeSalario(Document):
	"""Salary advance: cash given before payday, deducted in full from the next
	processed Salary Slip (see salary_slip_hooks._add_adiantamentos). The cap —
	Settings.adiantamento_max_percentagem × base salary — is enforced server-side
	across ALL pending (not yet deducted) advances of the employee, so payroll
	cannot go negative by stacking advances. The cap can NEVER be disabled: a
	blank/0 setting falls back to ADIANTAMENTO_PERCENTAGEM_PADRAO."""

	def validate(self):
		if flt(self.valor) <= 0:
			frappe.throw(_("Valor deve ser maior que zero."))
		self._validar_limite()

	def on_cancel(self):
		if self.aplicado_em:
			frappe.throw(
				_("Este adiantamento já foi deduzido no recibo {0}. Cancele primeiro esse recibo.").format(
					self.aplicado_em
				)
			)

	def _validar_limite(self):
		settings = get_settings()
		base = base_para_data(self.funcionario, self.data_do_adiantamento)
		self.salario_base_referencia = base

		percentagem = flt(settings.get("adiantamento_max_percentagem"))
		if percentagem <= 0:
			percentagem = ADIANTAMENTO_PERCENTAGEM_PADRAO

		if flt(base) <= 0:
			frappe.throw(
				_("O funcionário não tem salário base atribuído em {0} — não é possível calcular o limite do adiantamento.").format(
					frappe.format_value(self.data_do_adiantamento, {"fieldtype": "Date"})
				)
			)

		pendentes = frappe.get_all(
			"Adiantamento De Salario",
			filters={
				"funcionario": self.funcionario,
				"docstatus": 1,
				"aplicado_em": ["is", "not set"],
				"name": ["!=", self.name],
			},
			pluck="valor",
		)
		limite = base * percentagem / 100.0 - sum(flt(v) for v in pendentes)
		self.limite_maximo = max(limite, 0)

		if flt(self.valor) > flt(self.limite_maximo):
			frappe.throw(
				_(
					"Valor ({0}) excede o limite de adiantamento ({1} = {2}% do salário base {3}, descontando adiantamentos pendentes)."
				).format(
					frappe.format_value(flt(self.valor), {"fieldtype": "Currency"}),
					frappe.format_value(flt(self.limite_maximo), {"fieldtype": "Currency"}),
					flt(percentagem),
					frappe.format_value(flt(base), {"fieldtype": "Currency"}),
				)
			)
