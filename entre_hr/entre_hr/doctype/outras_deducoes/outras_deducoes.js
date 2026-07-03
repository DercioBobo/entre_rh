frappe.ui.form.on("Outras Deducoes", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.ano) {
			frm.set_value("ano", new Date().getFullYear());
		}
	},
});
