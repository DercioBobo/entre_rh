import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, flt, get_last_day, getdate

from entre_hr.salario import base_para_data


class Emprestimo(Document):
	def validate(self):
		self._validar_valores()
		self._derivar_campos()
		self._avisar_limite()

	def _validar_valores(self):
		if flt(self.valor_mensal) <= 0:
			frappe.throw(_("Prestação Mensal deve ser maior que zero."))
		if cint(self.numero_de_meses) < 1:
			frappe.throw(_("Número de Meses deve ser pelo menos 1."))

	def _derivar_campos(self):
		inicio = getdate(self.data_de_inicio)
		self.data_de_fim = get_last_day(add_months(inicio, cint(self.numero_de_meses) - 1))
		self.valor_total = flt(self.valor_mensal) * cint(self.numero_de_meses)
		self.salario_base = base_para_data(self.funcionario, inicio)

	def _avisar_limite(self):
		# Non-blocking guidance: installment above 1/3 of the base is usually excessive.
		if self.salario_base and flt(self.valor_mensal) > flt(self.salario_base) / 3:
			frappe.msgprint(
				_("Atenção: a prestação mensal ({0}) excede 1/3 do salário base ({1}).").format(
					frappe.format_value(self.valor_mensal, {"fieldtype": "Currency"}),
					frappe.format_value(self.salario_base, {"fieldtype": "Currency"}),
				),
				indicator="orange",
				alert=True,
			)
