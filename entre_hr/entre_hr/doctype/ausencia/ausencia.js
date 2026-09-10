frappe.ui.form.on("Ausencia", {
	onload(frm) {
		if (frm.is_new()) {
			const hoje = new Date();
			if (!frm.doc.ano) frm.set_value("ano", hoje.getFullYear());
			if (!frm.doc.mes) frm.set_value("mes", entre_hr.periodo.MESES[hoje.getMonth()]);
		}
	},
});
