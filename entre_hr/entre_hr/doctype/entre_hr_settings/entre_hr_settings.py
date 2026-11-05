from frappe.model.document import Document

from entre_hr.utils import sincronizar_dias_payroll


class EntreHRSettings(Document):
	def on_update(self):
		sincronizar_dias_payroll()
