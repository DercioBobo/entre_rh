frappe.ui.form.on("Outras Remuneracoes", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.ano) {
			frm.set_value("ano", new Date().getFullYear());
		}
	},
});
