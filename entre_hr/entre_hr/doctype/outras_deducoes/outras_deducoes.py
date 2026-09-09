import frappe
from frappe import _
from frappe.model.document import Document

from entre_hr.utils import (
	derivar_periodo_pagamento,
	herdar_empresa,
	validar_mes_nao_passado,
)


class OutrasDeducoes(Document):
	def validate(self):
		herdar_empresa(self)
		validar_mes_nao_passado(self)
		derivar_periodo_pagamento(self)
		self._validar_tipo()

	def _validar_tipo(self):
		if frappe.db.get_value("Salary Component", self.tipo, "type") != "Deduction":
			frappe.throw(
				_("O componente {0} não é uma Dedução (Deduction).").format(self.tipo)
			)
