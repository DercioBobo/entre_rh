import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from entre_hr.utils import herdar_empresa, mes_ano_para_periodo, soma_submetido, validar_mes_nao_futuro


class JustificacaoDeFaltas(Document):
	def validate(self):
		herdar_empresa(self)
		validar_mes_nao_futuro(self)
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
		# Checked unconditionally — including when faltas is 0 — so nothing can ever be
		# justified without a matching Ausencia.
		faltas = self._total_submetido("Ausencia", "n_de_faltas")
		justificados = self._total_submetido(
			"Justificacao De Faltas", "dias_justificados", excluir=self.name
		)
		self.faltas_registadas = faltas
		self.faltas_disponiveis = max(faltas - justificados, 0)
		if justificados + cint(self.dias_justificados) > faltas:
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
		filters = {"funcionario": self.funcionario, "mes": self.mes, "ano": self.ano}
		if excluir:
			filters["name"] = ["!=", excluir]
		return soma_submetido(doctype, campo, filters)


@frappe.whitelist()
def faltas_disponiveis(funcionario, mes, ano):
	"""Client-side lookup: faltas registadas and still-available-to-justify for the
	given employee/period, so the form shows the real numbers before a value is typed."""
	filters = {"funcionario": funcionario, "mes": mes, "ano": ano}
	registadas = soma_submetido("Ausencia", "n_de_faltas", filters)
	justificados = soma_submetido("Justificacao De Faltas", "dias_justificados", filters)
	return {
		"faltas_registadas": registadas,
		"faltas_disponiveis": max(registadas - justificados, 0),
	}
