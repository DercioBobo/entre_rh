frappe.ui.form.on("Ausencia", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.ano) {
			frm.set_value("ano", new Date().getFullYear());
		}
	},
});
