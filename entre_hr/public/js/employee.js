// Entre HR — "Definir Salário" button on the Employee form (BUILD_PLAN Phase 2).

frappe.ui.form.on("Employee", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (
			!frappe.user.has_role("RH Manager") &&
			!frappe.user.has_role("System Manager")
		)
			return;

		frm.add_custom_button(
			__("Definir Salário"),
			() => entre_hr_definir_salario_dialog(frm),
			__("Entre HR")
		);
	},
});

function entre_hr_definir_salario_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Definir Salário — {0}", [frm.doc.employee_name]),
		fields: [
			{
				fieldname: "usar_minimo",
				fieldtype: "Check",
				label: __("Usar salário mínimo"),
			},
			{
				fieldname: "valor",
				fieldtype: "Currency",
				label: __("Salário Base"),
				depends_on: "eval:!doc.usar_minimo",
				mandatory_depends_on: "eval:!doc.usar_minimo",
			},
		],
		primary_action_label: __("Aplicar"),
		primary_action(values) {
			d.hide();
			entre_hr_chamar_definir_salario(frm, values, 0);
		},
	});
	d.show();
}

function entre_hr_chamar_definir_salario(frm, values, confirmar_reducao) {
	frappe.call({
		method: "entre_hr.salario.definir_salario",
		args: {
			employee: frm.doc.name,
			valor: values.valor,
			usar_minimo: values.usar_minimo ? 1 : 0,
			confirmar_reducao: confirmar_reducao,
		},
		freeze: true,
		freeze_message: __("A aplicar salário..."),
		callback(r) {
			const m = r.message || {};
			if (m.requires_confirm) {
				frappe.confirm(
					__(
						"O novo salário ({0}) é inferior ao atual ({1}). Confirmar a redução?",
						[format_currency(m.novo), format_currency(m.atual)]
					),
					() => entre_hr_chamar_definir_salario(frm, values, 1)
				);
				return;
			}
			frappe.show_alert({
				message: __("Salário base aplicado."),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}
