import frappe

ROLES = ["Aprovador RH", "RH Manager"]


def after_install():
	ensure_roles()


def after_migrate():
	ensure_roles()


def ensure_roles():
	"""Create the app's roles if missing (idempotent; fixtures also ship them)."""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role, "desk_access": 1}
			).insert(ignore_permissions=True)
