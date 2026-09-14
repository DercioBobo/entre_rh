frappe.ui.form.on("Justificacao De Faltas", {
	onload(frm) {
		if (frm.is_new()) {
			const hoje = new Date();
			if (!frm.doc.ano) frm.set_value("ano", hoje.getFullYear());
			if (!frm.doc.mes) frm.set_value("mes", entre_hr.periodo.MESES[hoje.getMonth()]);
		}
	},
	refresh: atualizar_faltas_disponiveis,
	funcionario: atualizar_faltas_disponiveis,
	mes: atualizar_faltas_disponiveis,
	ano: atualizar_faltas_disponiveis,
});

function atualizar_faltas_disponiveis(frm) {
	if (!frm.doc.funcionario || !frm.doc.mes || !frm.doc.ano) return;
	frappe.call({
		method: "entre_hr.entre_hr.doctype.justificacao_de_faltas.justificacao_de_faltas.faltas_disponiveis",
		args: { funcionario: frm.doc.funcionario, mes: frm.doc.mes, ano: frm.doc.ano },
		callback(r) {
			if (!r.message) return;
			frm.set_value("faltas_registadas", r.message.faltas_registadas);
			frm.set_value("faltas_disponiveis", r.message.faltas_disponiveis);
		},
	});
}
