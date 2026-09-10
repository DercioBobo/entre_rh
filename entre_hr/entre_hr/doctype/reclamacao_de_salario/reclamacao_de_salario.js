frappe.ui.form.on("Reclamacao De Salario", {
	onload(frm) {
		if (frm.is_new()) {
			const hoje = new Date();
			if (!frm.doc.ano_reclamacao) frm.set_value("ano_reclamacao", hoje.getFullYear());
			if (!frm.doc.mes_reclamacao)
				frm.set_value("mes_reclamacao", entre_hr.periodo.MESES[hoje.getMonth()]);
		}
	},
});
