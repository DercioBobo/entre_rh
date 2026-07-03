import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from entre_hr.utils import mes_ano_para_periodo


class JustificacaoDeFaltas(Document):
	def validate(self):
		self._validar_dias()

	def _validar_dias(self):
		inicio, fim = mes_ano_para_periodo(self.mes, self.ano)
		dias_do_mes = fim.day
		if cint(self.dias_justificados) < 1 or cint(self.dias_justificados) > dias_do_mes:
			frappe.throw(
				_("Dias Justificados deve estar entre 1 e {0} ({1} de {2}).").format(
					dias_do_mes, self.mes, self.ano
				)
			)

		# A justification can only offset what was actually recorded as absent: the total
		# justified for the month (including this one) may not exceed the recorded faltas.
		faltas = self._total_submetido("Ausencia", "n_de_faltas")
		justificados = self._total_submetido(
			"Justificacao De Faltas", "dias_justificados", excluir=self.name
		)
		if faltas and justificados + cint(self.dias_justificados) > faltas:
			frappe.throw(
				_("Total justificado ({0}) excederia as faltas registadas ({1}) de {2} em {3} de {4}.").format(
					justificados + cint(self.dias_justificados),
					faltas,
					self.funcionario_nome or self.funcionario,
					self.mes,
					self.ano,
				)
			)

	def _total_submetido(self, doctype, campo, excluir=None):
		filters = {
			"funcionario": self.funcionario,
			"mes": self.mes,
			"ano": self.ano,
			"docstatus": 1,
		}
		if excluir:
			filters["name"] = ["!=", excluir]
		rows = frappe.get_all(doctype, filters=filters, fields=[f"sum({campo}) as total"])
		return cint(rows[0].total) if rows else 0
