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
		if cint(self.numero_de_meses) < 1:
			frappe.throw(_("Número de Meses deve ser pelo menos 1."))
		if self.get("base_de_calculo") == "Valor Total":
			if flt(self.valor_total) <= 0:
				frappe.throw(_("Valor Total deve ser maior que zero."))
		elif flt(self.valor_mensal) <= 0:
			frappe.throw(_("Prestação Mensal deve ser maior que zero."))

	def _derivar_campos(self):
		# Base de Cálculo: the amount typed drives the other (same rules as Outras
		# Deducoes/Remuneracoes; the FINAL installment absorbs the 2-decimal rounding
		# — see entre_hr.utils.prestacao_do_mes, used by the slip assembler).
		meses = cint(self.numero_de_meses)
		if self.get("base_de_calculo") == "Valor Total":
			self.valor_mensal = flt(flt(self.valor_total) / meses, 2)
		else:
			self.valor_total = flt(flt(self.valor_mensal) * meses, 2)
		inicio = getdate(self.data_de_inicio)
		self.data_de_fim = get_last_day(add_months(inicio, meses - 1))
		self.salario_base = base_para_data(self.funcionario, inicio)
		self.saldo_devedor = flt(self.valor_total) - flt(self.valor_pago)
		self.status = "Pago" if flt(self.saldo_devedor) <= 0.005 else "Em Curso"

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
