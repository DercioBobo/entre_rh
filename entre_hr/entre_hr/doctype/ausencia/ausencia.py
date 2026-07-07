import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, formatdate, getdate

from entre_hr.utils import MESES, mes_ano_para_periodo, validar_mes_nao_passado


def modo_registo_faltas():
	"""Company policy: 'Por Dias' (each record IS one concrete day — the day you
	register is the day, so the same day can never be marked twice; register daily,
	weekly or monthly by creating one record per day) or 'Por Total' (records carry a
	plain sum for the month; several records per month add up, capped at its days)."""
	return (
		frappe.get_cached_doc("Entre HR Settings").get("modo_registo_faltas") or "Por Dias"
	)


class Ausencia(Document):
	"""One absence entry. Several entries per employee/month are allowed on purpose,
	so HR can register incrementally; payroll SUMs them (utils.calcular_faltas)."""

	def validate(self):
		self._derivar_periodo()
		validar_mes_nao_passado(self)
		self._validar_registo()
		self._validar_total_do_mes()

	def _derivar_periodo(self):
		"""Por Dias: the record's mês/ano/n_de_faltas are derived from `data` — the
		day you register IS the day, so there is nothing else to enter. Por Total:
		mês/ano/n_de_faltas are entered directly (no specific day)."""
		if modo_registo_faltas() != "Por Dias":
			return
		if not self.data:
			frappe.throw(
				_("Indique o dia da falta — o modo de registo configurado é 'Por Dias'.")
			)
		data = getdate(self.data)
		self.mes = MESES[data.month - 1]
		self.ano = data.year
		self.n_de_faltas = 1

	def _validar_registo(self):
		if modo_registo_faltas() == "Por Dias":
			self._validar_dia_unico()
		else:
			_inicio, fim = mes_ano_para_periodo(self.mes, self.ano)
			if cint(self.n_de_faltas) < 1 or cint(self.n_de_faltas) > fim.day:
				frappe.throw(
					_("Nº de Faltas deve estar entre 1 e {0} ({1} de {2}).").format(
						fim.day, self.mes, self.ano
					)
				)

	def _validar_dia_unico(self):
		"""The same day can never be marked twice for the same employee — checked
		directly on Ausencia.data, no child table involved."""
		duplicado = frappe.db.exists(
			"Ausencia",
			{
				"funcionario": self.funcionario,
				"data": self.data,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
		)
		if duplicado:
			frappe.throw(
				_("O dia {0} já está marcado na Ausência {1} deste funcionário.").format(
					formatdate(getdate(self.data)), duplicado
				)
			)

	def _validar_total_do_mes(self):
		"""Whatever the mode, the month's registered absences (all records summed)
		can never exceed the month's days."""
		_inicio, fim = mes_ano_para_periodo(self.mes, self.ano)
		outros = frappe.get_all(
			"Ausencia",
			filters={
				"funcionario": self.funcionario,
				"mes": self.mes,
				"ano": self.ano,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
			pluck="n_de_faltas",
		)
		total = cint(self.n_de_faltas) + sum(cint(n) for n in outros)
		if total > fim.day:
			frappe.throw(
				_("Com este registo, {0} teria {1} faltas em {2} de {3} — mais do que os {4} dias do mês.").format(
					self.funcionario_nome or self.funcionario, total, self.mes, self.ano, fim.day
				)
			)
