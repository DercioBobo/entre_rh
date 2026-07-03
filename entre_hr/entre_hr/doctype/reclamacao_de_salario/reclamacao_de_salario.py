import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from entre_hr.utils import mes_ano_para_periodo


class ReclamacaoDeSalario(Document):
	def validate(self):
		if flt(self.valor_reclamado) <= 0:
			frappe.throw(_("Valor Reclamado deve ser maior que zero."))
		self._resolver_recibo_referencia()

	def _resolver_recibo_referencia(self):
		inicio, fim = mes_ano_para_periodo(self.mes_reclamacao, self.ano_reclamacao)
		slips = frappe.get_all(
			"Salary Slip",
			filters={
				"employee": self.funcionario,
				"docstatus": 1,
				"start_date": ["<=", fim],
				"end_date": [">=", inicio],
			},
			fields=["name", "gross_pay", "net_pay"],
			order_by="start_date desc",
			limit=1,
		)
		if slips:
			self.slip_referencia = slips[0].name
			self.bruto_referencia = slips[0].gross_pay
			self.liquido_referencia = slips[0].net_pay
		else:
			# Blank, not 0 — a claim for a genuinely unpaid month is still valid.
			self.slip_referencia = None
			self.bruto_referencia = None
			self.liquido_referencia = None
			frappe.msgprint(
				_("Não foi encontrado nenhum recibo processado para {0} de {1}. A reclamação continua válida (mês possivelmente não pago).").format(
					self.mes_reclamacao, self.ano_reclamacao
				),
				indicator="orange",
				alert=True,
			)
