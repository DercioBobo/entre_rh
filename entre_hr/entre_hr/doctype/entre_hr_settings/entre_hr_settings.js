// Entre HR Settings — admin actions (BUILD_PLAN Phase 3).

frappe.ui.form.on("Entre HR Settings", {
	refresh(frm) {
		frm.add_custom_button(
			__("Backfill Férias"),
			() => {
				frappe.confirm(
					__(
						"Criar as alocações iniciais de férias para os funcionários existentes (a partir da antiguidade)? Funcionários que já têm alocação são ignorados — é seguro re-executar."
					),
					() => {
						frappe.call({
							method: "entre_hr.ferias.enqueue_backfill_ferias",
							freeze: true,
							callback(r) {
								frappe.show_alert({
									message: r.message || __("Backfill em fila."),
									indicator: "blue",
								});
							},
						});
					}
				);
			},
			__("Férias")
		);
	},
});
