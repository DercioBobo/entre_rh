frappe.ui.form.on("Justificacao De Faltas", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.ano) {
			frm.set_value("ano", new Date().getFullYear());
		}
	},
});
