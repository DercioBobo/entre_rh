import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from entre_hr.salario import base_para_data
from entre_hr.utils import herdar_empresa, mes_ano_para_periodo, validar_mes_nao_passado

MULT_50 = 1.5
MULT_100 = 2.0


class HorasExtras(Document):
	"""Overtime for one employee in one month. Several records per employee/month are
	allowed (register incrementally); the Salary Slip SUMS them. The slip recomputes
	the amount with the base salary in force that month, so `valor_total` here is a
	preview."""

	def validate(self):
		herdar_empresa(self)
		validar_mes_nao_passado(self)
		if flt(self.horas_50) < 0 or flt(self.horas_100) < 0:
			frappe.throw(_("As horas não podem ser negativas."))
		if flt(self.horas_50) == 0 and flt(self.horas_100) == 0:
			frappe.throw(_("Indique horas a 50% ou a 100%."))
		self._preview()

	def _preview(self):
		horas_mensais = flt(
			frappe.get_cached_doc("Entre HR Settings").get("he_horas_mensais")
		) or 240.0
		_inicio, fim = mes_ano_para_periodo(self.mes, self.ano)
		base = base_para_data(self.funcionario, fim)
		self.taxa_horaria = flt(base) / horas_mensais if horas_mensais else 0.0
		self.valor_total = self.taxa_horaria * (
			flt(self.horas_50) * MULT_50 + flt(self.horas_100) * MULT_100
		)
