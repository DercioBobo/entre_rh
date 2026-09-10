import frappe
from frappe.model.document import Document


class AcumulacaoFeriasLog(Document):
	"""Audit trail for the férias accrual engine (entre_hr.ferias). One row per
	automatic action — creation of the rolling allocation, a monthly accrual, an
	anniversary expiry, or a one-time backfill seed. Written by the engine with
	ignore_permissions; never edited by hand."""

	pass
