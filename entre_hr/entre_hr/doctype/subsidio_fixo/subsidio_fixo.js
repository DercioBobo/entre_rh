// Entre HR — Subsídio Fixo: "Aplicar a Todas as Empresas" action.

frappe.ui.form.on("Subsidio Fixo", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Aplicar a Todas as Empresas"), () => {
			frappe.confirm(
				__(
					"Criar este subsídio ({0} = {1}) em todas as empresas que ainda não o têm? As empresas com um registo próprio ficam como estão.",
					[frm.doc.componente, format_currency(frm.doc.valor)]
				),
				() => {
					frappe.call({
						method: "entre_hr.entre_hr.doctype.subsidio_fixo.subsidio_fixo.aplicar_a_todas",
						args: {
							componente: frm.doc.componente,
							valor: frm.doc.valor,
							descricao: frm.doc.descricao,
						},
						freeze: true,
						callback(r) {
							const n = (r.message || []).length;
							frappe.show_alert({
								message: n
									? __("Criado em {0} empresa(s).", [n])
									: __("Todas as empresas já tinham este subsídio."),
								indicator: "green",
							});
						},
					});
				}
			);
		});
	},
});
