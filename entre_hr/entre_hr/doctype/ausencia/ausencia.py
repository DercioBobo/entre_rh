import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, formatdate, getdate

from entre_hr.utils import mes_ano_para_periodo, validar_mes_nao_passado


def modo_registo_faltas():
	"""Company policy: 'Por Dias' (records list concrete days; register daily/weekly/
	monthly — the same day can never be marked twice) or 'Por Total' (records carry a
	sum; multiple records per month add up, capped at the month's days)."""
	return (
		frappe.get_cached_doc("Entre HR Settings").get("modo_registo_faltas") or "Por Dias"
	)


class Ausencia(Document):
	"""One absence entry. Several entries per employee/month are allowed on purpose,
	so HR can register incrementally; payroll SUMs them (utils.calcular_faltas)."""

	def validate(self):
		validar_mes_nao_passado(self)
		self._validar_registo()
		self._validar_total_do_mes()

	def _validar_registo(self):
		if self.dias:
			self._validar_dias()
		elif modo_registo_faltas() == "Por Dias":
			frappe.throw(
				_("Marque os dias concretos de ausência — o modo de registo configurado é 'Por Dias'.")
			)
		else:
			_inicio, fim = mes_ano_para_periodo(self.mes, self.ano)
			if cint(self.n_de_faltas) < 1 or cint(self.n_de_faltas) > fim.day:
				frappe.throw(
					_("Nº de Faltas deve estar entre 1 e {0} ({1} de {2}).").format(
						fim.day, self.mes, self.ano
					)
				)

	def _validar_dias(self):
		"""Day-listed record: each day must belong to mês/ano, appear only once here,
		and never be marked for the employee in any other record. n_de_faltas is
		derived from the days."""
		inicio, fim = mes_ano_para_periodo(self.mes, self.ano)
		vistos = set()
		for row in self.dias:
			data = getdate(row.data)
			if data < inicio or data > fim:
				frappe.throw(
					_("O dia {0} não pertence a {1} de {2}.").format(
						formatdate(data), self.mes, self.ano
					)
				)
			if data in vistos:
				frappe.throw(
					_("O dia {0} está marcado mais do que uma vez neste registo.").format(
						formatdate(data)
					)
				)
			vistos.add(data)

		self.n_de_faltas = len(vistos)
		self._validar_dias_noutros_registos(vistos)

	def _validar_dias_noutros_registos(self, dias):
		outros = frappe.get_all(
			"Ausencia",
			filters={
				"funcionario": self.funcionario,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
			pluck="name",
		)
		if not outros:
			return
		repetido = frappe.get_all(
			"Dia De Ausencia",
			filters={
				"parenttype": "Ausencia",
				"parent": ["in", outros],
				"data": ["in", [str(d) for d in dias]],
			},
			fields=["data", "parent"],
			limit=1,
		)
		if repetido:
			frappe.throw(
				_("O dia {0} já está marcado na Ausência {1} deste funcionário.").format(
					formatdate(repetido[0].data), repetido[0].parent
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
