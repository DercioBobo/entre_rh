import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from entre_hr.utils import mes_ano_para_periodo, validar_mes_nao_passado


class Ausencia(Document):
	def validate(self):
		validar_mes_nao_passado(self)
		self._validar_n_de_faltas()
		self._validar_duplicado()

	def _validar_n_de_faltas(self):
		inicio, fim = mes_ano_para_periodo(self.mes, self.ano)
		dias_do_mes = fim.day
		if cint(self.n_de_faltas) < 1 or cint(self.n_de_faltas) > dias_do_mes:
			frappe.throw(
				_("Nº de Faltas deve estar entre 1 e {0} ({1} de {2}).").format(
					dias_do_mes, self.mes, self.ano
				)
			)

	def _validar_duplicado(self):
		duplicado = frappe.db.exists(
			"Ausencia",
			{
				"funcionario": self.funcionario,
				"mes": self.mes,
				"ano": self.ano,
				"docstatus": ["<", 2],
				"name": ["!=", self.name],
			},
		)
		if duplicado:
			frappe.throw(
				_("Já existe a Ausência {0} para {1} em {2} de {3}.").format(
					duplicado, self.funcionario_nome or self.funcionario, self.mes, self.ano
				)
			)
