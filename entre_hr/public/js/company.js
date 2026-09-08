// Entre HR — "Configurar Folha" button on the Company form.
// Re-runs the per-company payroll bootstrap (entre_hr/setup_empresa.py): Salary
// Structure, GL accounts, salary-component account mappings, holiday list. Idempotent.

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (
			!frappe.user.has_role("RH Manager") &&
			!frappe.user.has_role("System Manager")
		)
			return;

		frm.add_custom_button(
			__("Configurar Folha"),
			() => {
				frappe.call({
					method: "entre_hr.setup_empresa.configurar_empresa_manual",
					args: { company: frm.doc.name },
					freeze: true,
					freeze_message: __("A configurar a folha de pagamento..."),
					callback(r) {
						if (!r.message) {
							frappe.msgprint(
								__("Plano de contas ainda não criado — guarde a empresa e tente de novo.")
							);
							return;
						}
						frappe.show_alert({
							message: __("Folha configurada — estrutura {0}.", [r.message]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			},
			__("Entre HR")
		);
	},
});
