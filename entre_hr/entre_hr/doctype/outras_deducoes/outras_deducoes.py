import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, flt, get_last_day

from entre_hr.utils import mes_ano_para_periodo, validar_mes_nao_passado


class OutrasDeducoes(Document):
	def validate(self):
		validar_mes_nao_passado(self)
		self._validar_valores()
		self._derivar_datas()
		self._validar_tipo()

	def _validar_valores(self):
		if flt(self.valor_mensal) <= 0:
			frappe.throw(_("Valor Mensal deve ser maior que zero."))
		if cint(self.numero_de_meses) < 1:
			frappe.throw(_("Número de Meses deve ser pelo menos 1."))

	def _derivar_datas(self):
		inicio, _fim = mes_ano_para_periodo(self.mes, self.ano)
		self.data_de_inicio = inicio
		self.data_de_fim = get_last_day(add_months(inicio, cint(self.numero_de_meses) - 1))

	def _validar_tipo(self):
		if frappe.db.get_value("Salary Component", self.tipo, "type") != "Deduction":
			frappe.throw(
				_("O componente {0} não é uma Dedução (Deduction).").format(self.tipo)
			)
