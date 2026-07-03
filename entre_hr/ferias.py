"""Férias (annual leave) accrual engine — BUILD_PLAN Phase 3.

We own accrual directly via Leave Ledger Entries: the bookable balance is the SUM of
ledger entries (never trust `new_leaves_allocated`). One rolling Leave Allocation per
employee (to_date = 2099-12-31) acts as the container; every accrual (+) and expiry (−)
is an explicit ledger entry.

Policy: < 1 year of service = 1 day/month; >= 1 year = 2.5 days/month. Cap =
Settings.dias_maximos_ferias; the excess expires on the admission anniversary.

History is the backfill's job — the daily scheduler never back-accrues an employee it
has not seen; it initializes the idempotency marker and accrues forward from there.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate, today

from entre_hr.utils import ROLES_GESTAO_RH

FAR_HORIZON = "2099-12-31"


def get_settings():
	return frappe.get_cached_doc("Entre HR Settings")


def _gate(settings):
	return cint(settings.ferias_activo) and settings.leave_type_ferias


def saldo_ferias(employee, leave_type):
	"""Bookable balance = SUM of the employee's submitted Leave Ledger Entries."""
	rows = frappe.get_all(
		"Leave Ledger Entry",
		filters={"employee": employee, "leave_type": leave_type, "docstatus": 1},
		fields=["sum(leaves) as total"],
	)
	return flt(rows[0].total) if rows else 0.0


def get_rolling_allocation(employee, leave_type):
	"""The employee's single rolling allocation (to_date = far horizon), or None."""
	rows = frappe.get_all(
		"Leave Allocation",
		filters={
			"employee": employee,
			"leave_type": leave_type,
			"docstatus": 1,
			"to_date": FAR_HORIZON,
		},
		fields=["name", "total_leaves_allocated"],
		limit=1,
	)
	return rows[0] if rows else None


def _meses_completos(anchor, dia):
	"""Number of full months elapsed from `anchor` to `dia`."""
	n = (dia.year - anchor.year) * 12 + (dia.month - anchor.month)
	if n >= 0 and getdate(add_months(anchor, n)) > dia:
		n -= 1
	return max(n, 0)


def _criar_alocacao(employee, company, leave_type, from_date, dias):
	"""Create + submit the rolling allocation; its on_submit writes the first (+) ledger entry."""
	alloc = frappe.new_doc("Leave Allocation")
	alloc.employee = employee
	alloc.company = company
	alloc.leave_type = leave_type
	alloc.from_date = from_date
	alloc.to_date = FAR_HORIZON
	alloc.carry_forward = 0
	alloc.new_leaves_allocated = dias
	alloc.flags.ignore_permissions = True
	alloc.insert()
	alloc.submit()
	return frappe._dict(name=alloc.name, total_leaves_allocated=alloc.total_leaves_allocated)


def _lancar_ledger(allocation_name, employee, company, leave_type, leaves, data, is_expired=0):
	"""Write one explicit Leave Ledger Entry (+accrual / −expiry) against the allocation."""
	entry = frappe.get_doc(
		{
			"doctype": "Leave Ledger Entry",
			"employee": employee,
			"leave_type": leave_type,
			"transaction_type": "Leave Allocation",
			"transaction_name": allocation_name,
			"leaves": leaves,
			"from_date": data,
			"to_date": FAR_HORIZON,
			"is_carry_forward": 0,
			"is_expired": is_expired,
			"is_lwp": 0,
			"company": company,
		}
	)
	entry.flags.ignore_permissions = True
	entry.submit()


def _ajustar_total_alocado(allocation_name, delta):
	"""Mirror the display field on the allocation (net allocated = accruals − expiries)."""
	atual = flt(frappe.db.get_value("Leave Allocation", allocation_name, "total_leaves_allocated"))
	frappe.db.set_value(
		"Leave Allocation",
		allocation_name,
		"total_leaves_allocated",
		atual + delta,
		update_modified=False,
	)


def _trim_excesso(employee, company, leave_type, allocation_name, cap, data):
	"""On the admission anniversary, expire whatever exceeds the cap."""
	excesso = saldo_ferias(employee, leave_type) - flt(cap)
	if excesso > 0:
		_lancar_ledger(
			allocation_name, employee, company, leave_type, -excesso, data, is_expired=1
		)
		_ajustar_total_alocado(allocation_name, -excesso)
	return max(excesso, 0)


def acumular_funcionario(emp, hoje=None):
	"""Accrue one employee up to `hoje`. `emp` = dict(name, date_of_joining, company,
	custom_data_antiguidade_ferias, custom_ultima_acumulacao_ferias). Returns days accrued.

	Idempotent via Employee.custom_ultima_acumulacao_ferias — a month is never accrued twice.
	"""
	settings = get_settings()
	if not _gate(settings):
		return 0

	leave_type = settings.leave_type_ferias
	cap = cint(settings.dias_maximos_ferias) or 60
	hoje = getdate(hoje or today())
	anchor = getdate(emp.custom_data_antiguidade_ferias or emp.date_of_joining)
	alloc = get_rolling_allocation(emp.name, leave_type)

	if emp.custom_ultima_acumulacao_ferias:
		marker = getdate(emp.custom_ultima_acumulacao_ferias)
		n = _meses_completos(anchor, marker)
	else:
		# First sighting: start fresh from the last completed boundary — no historical
		# catch-up here (that is the backfill's job). Just plant the marker.
		n = _meses_completos(anchor, hoje)
		frappe.db.set_value(
			"Employee",
			emp.name,
			"custom_ultima_acumulacao_ferias",
			add_months(anchor, n),
			update_modified=False,
		)
		return 0

	acumulado = 0.0
	while True:
		proxima = getdate(add_months(anchor, n + 1))
		if proxima > hoje:
			break

		# Tier by tenure at the START of the accrued month: months 1..12 -> 1 day,
		# months 13+ -> 2.5 days.
		rate = 1.0 if n < 12 else 2.5

		if not alloc:
			alloc = _criar_alocacao(emp.name, emp.company, leave_type, anchor, rate)
		else:
			_lancar_ledger(alloc.name, emp.name, emp.company, leave_type, rate, proxima)
			_ajustar_total_alocado(alloc.name, rate)

		n += 1
		acumulado += rate
		frappe.db.set_value(
			"Employee",
			emp.name,
			"custom_ultima_acumulacao_ferias",
			proxima,
			update_modified=False,
		)

		# Admission anniversary: expire the excess above the cap.
		if n % 12 == 0:
			_trim_excesso(emp.name, emp.company, leave_type, alloc.name, cap, proxima)

	return acumulado


def _employees_activos(employee=None):
	filters = {"status": "Active"}
	if employee:
		filters["name"] = employee
	return frappe.get_all(
		"Employee",
		filters=filters,
		fields=[
			"name",
			"date_of_joining",
			"company",
			"custom_data_antiguidade_ferias",
			"custom_ultima_acumulacao_ferias",
		],
	)


def acumular_ferias_diario():
	"""Daily scheduler entrypoint — accrues each active employee on their admission
	day-of-month (with automatic catch-up of missed scheduler days)."""
	settings = get_settings()
	if not _gate(settings):
		return

	for emp in _employees_activos():
		try:
			acumular_funcionario(emp)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				frappe.get_traceback(),
				f"Entre HR: acumulação de férias falhou para {emp.name}",
			)


@frappe.whitelist()
def executar_acumulacao(employee=None, ate=None):
	"""Manual accrual run (RH Manager / System Manager). `ate` allows testing a future
	'as-of' date. Returns days accrued and the resulting ledger balance."""
	if not ROLES_GESTAO_RH & set(frappe.get_roles()):
		frappe.throw(_("Sem permissão."), frappe.PermissionError)

	settings = get_settings()
	if not _gate(settings):
		frappe.throw(_("Active o módulo de Férias e defina o Leave Type em Entre HR Settings."))

	total = 0.0
	for emp in _employees_activos(employee):
		total += acumular_funcionario(emp, ate)

	out = {"acumulado": total}
	if employee:
		out["saldo"] = saldo_ferias(employee, settings.leave_type_ferias)
	return out


# ---------------------------------------------------------------------------
# One-time backfill (button on Entre HR Settings)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def enqueue_backfill_ferias():
	if not ROLES_GESTAO_RH & set(frappe.get_roles()):
		frappe.throw(_("Sem permissão."), frappe.PermissionError)

	settings = get_settings()
	if not settings.leave_type_ferias:
		frappe.throw(_("Defina o Tipo de Licença (Férias) em Entre HR Settings."))

	frappe.enqueue(
		"entre_hr.ferias.backfill_ferias",
		queue="long",
		timeout=3600,
		user=frappe.session.user,
	)
	return _("Backfill de férias em fila — receberá uma notificação ao concluir.")


def backfill_ferias(user=None):
	"""Seed existing employees' starting balance from tenure (theoretical accrued −
	already used, capped). CREATE-ONLY: employees who already have an allocation for the
	leave type are skipped, so it is safe to re-run."""
	settings = get_settings()
	leave_type = settings.leave_type_ferias
	cap = cint(settings.dias_maximos_ferias) or 60
	hoje = getdate(today())

	criados, ignorados, erros = [], [], []

	for emp in _employees_activos():
		try:
			if frappe.db.exists(
				"Leave Allocation",
				{"employee": emp.name, "leave_type": leave_type, "docstatus": ["<", 2]},
			):
				ignorados.append(emp.name)
				continue

			anchor = getdate(emp.custom_data_antiguidade_ferias or emp.date_of_joining)
			n = _meses_completos(anchor, hoje)

			# Theoretical accrual with the anniversary trim applied along the way.
			saldo = 0.0
			for m in range(1, n + 1):
				saldo += 1.0 if m <= 12 else 2.5
				if m % 12 == 0:
					saldo = min(saldo, cap)
			saldo = min(saldo, cap)

			usados = flt(
				frappe.get_all(
					"Leave Application",
					filters={
						"employee": emp.name,
						"leave_type": leave_type,
						"docstatus": 1,
						"status": "Approved",
					},
					fields=["sum(total_leave_days) as total"],
				)[0].total
			)
			seed = max(saldo - usados, 0.0)

			if seed > 0:
				_criar_alocacao(emp.name, emp.company, leave_type, anchor, seed)

			# Plant the marker so the scheduler continues from the last completed month.
			frappe.db.set_value(
				"Employee",
				emp.name,
				"custom_ultima_acumulacao_ferias",
				add_months(anchor, n),
				update_modified=False,
			)
			criados.append(f"{emp.name}: {seed}")
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			erros.append(emp.name)
			frappe.log_error(
				frappe.get_traceback(), f"Entre HR: backfill férias falhou para {emp.name}"
			)

	resumo = _("Backfill de férias concluído. Criados: {0}. Ignorados (já tinham alocação): {1}. Erros: {2}.").format(
		len(criados), len(ignorados), len(erros)
	)
	if erros:
		resumo += " " + _("Com erro: {0} (ver Error Log).").format(", ".join(erros))

	if user:
		frappe.publish_realtime(
			"msgprint",
			{"message": resumo, "title": _("Backfill Férias"), "indicator": "green" if not erros else "orange"},
			user=user,
		)
	return resumo
