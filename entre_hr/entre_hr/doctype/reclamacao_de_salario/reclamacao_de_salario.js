frappe.ui.form.on("Reclamacao De Salario", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.ano_reclamacao) {
			frm.set_value("ano_reclamacao", new Date().getFullYear());
		}
	},
});
