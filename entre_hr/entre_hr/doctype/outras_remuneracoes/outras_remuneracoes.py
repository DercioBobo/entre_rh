import frappe
from frappe import _
from frappe.model.document import Document

from entre_hr.utils import derivar_periodo_pagamento, validar_mes_nao_passado


class OutrasRemuneracoes(Document):
	def validate(self):
		validar_mes_nao_passado(self)
		derivar_periodo_pagamento(self)
		self._validar_tipo()

	def _validar_tipo(self):
		if frappe.db.get_value("Salary Component", self.tipo_de_subsidios, "type") != "Earning":
			frappe.throw(
				_("O componente {0} não é uma Remuneração (Earning).").format(
					self.tipo_de_subsidios
				)
			)
