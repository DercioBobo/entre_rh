// Entre HR — app-wide scripts

// Shared "Período" behaviour for Outras Deducoes / Outras Remuneracoes (month+year
// start via eventos()) and Emprestimo (date start via eventos_data()).
// The server (entre_hr.utils.derivar_periodo_pagamento / emprestimo.py) stays
// authoritative on save; this mirror only keeps the derived fields and the payment
// simulator live while the user is typing, instead of appearing after the first save.
frappe.provide("entre_hr.periodo");

entre_hr.periodo.MESES = [
	"Janeiro",
	"Fevereiro",
	"Março",
	"Abril",
	"Maio",
	"Junho",
	"Julho",
	"Agosto",
	"Setembro",
	"Outubro",
	"Novembro",
	"Dezembro",
];

// --- Outras Deducoes / Outras Remuneracoes (mes + ano + tipo_de_pagamento) --------

entre_hr.periodo.eventos = function () {
	const actualizar = entre_hr.periodo.actualizar;
	return {
		onload(frm) {
			if (frm.is_new() && !frm.doc.ano) {
				frm.set_value("ano", new Date().getFullYear());
			}
		},
		refresh: actualizar,
		mes: actualizar,
		ano: actualizar,
		valor_mensal: actualizar,
		valor_total: actualizar,
		base_de_calculo: actualizar,
		tipo_de_pagamento(frm) {
			if (frm.doc.tipo_de_pagamento === "Único") {
				frm.set_value("numero_de_meses", 1);
			} else if (cint(frm.doc.numero_de_meses) < 2) {
				frm.set_value("numero_de_meses", 2);
			}
			actualizar(frm);
		},
		numero_de_meses(frm) {
			if (frm.doc.tipo_de_pagamento === "Único" && cint(frm.doc.numero_de_meses) !== 1) {
				frm.set_value("numero_de_meses", 1);
			}
			actualizar(frm);
		},
	};
};

entre_hr.periodo.actualizar = function (frm) {
	const mes_idx = entre_hr.periodo.MESES.indexOf(frm.doc.mes);
	entre_hr.periodo._derivar(frm, mes_idx, cint(frm.doc.ano), { definir_inicio: true });
};

// --- Emprestimo (data_de_inicio, no tipo_de_pagamento) ----------------------------

entre_hr.periodo.eventos_data = function () {
	const actualizar = entre_hr.periodo.actualizar_data;
	return {
		refresh: actualizar,
		data_de_inicio: actualizar,
		numero_de_meses: actualizar,
		valor_mensal: actualizar,
		valor_total: actualizar,
		base_de_calculo: actualizar,
	};
};

entre_hr.periodo.actualizar_data = function (frm) {
	if (!frm.doc.data_de_inicio) {
		entre_hr.periodo.render_simulador(frm, []);
		return;
	}
	const inicio = frappe.datetime.str_to_obj(frm.doc.data_de_inicio);
	entre_hr.periodo._derivar(frm, inicio.getMonth(), inicio.getFullYear(), {
		definir_inicio: false,
	});
};

// --- Shared core -------------------------------------------------------------------

entre_hr.periodo._derivar = function (frm, mes_idx, ano, opts) {
	const doc = frm.doc;
	const n = cint(doc.numero_de_meses);
	if (mes_idx < 0 || !ano || n < 1) {
		entre_hr.periodo.render_simulador(frm, []);
		return;
	}

	const fim_idx = mes_idx + n - 1;
	const fim_ano = ano + Math.floor(fim_idx / 12);
	const fim_mes = fim_idx % 12; // 0-based
	const ultimo_dia = new Date(fim_ano, fim_mes + 1, 0).getDate();
	const pad = (v) => String(v).padStart(2, "0");
	const inicio = `${ano}-${pad(mes_idx + 1)}-01`;
	const fim = `${fim_ano}-${pad(fim_mes + 1)}-${pad(ultimo_dia)}`;

	// Amounts, according to the Base de Cálculo direction: monthly → total, or
	// total (e.g. a loan of 15000, a known damage) → monthly = total / months.
	let mensal, total;
	if (doc.base_de_calculo === "Valor Total") {
		total = flt(doc.valor_total);
		mensal = flt(total / n, 2);
	} else {
		mensal = flt(doc.valor_mensal);
		total = flt(mensal * n, 2);
	}

	// Mirror the derived fields only on editable docs, and only when they changed
	// (so opening a saved/submitted document never marks it dirty).
	if (!doc.docstatus) {
		if (opts.definir_inicio && doc.data_de_inicio !== inicio) {
			frm.set_value("data_de_inicio", inicio);
		}
		if (doc.data_de_fim !== fim) frm.set_value("data_de_fim", fim);
		if (doc.base_de_calculo === "Valor Total") {
			if (flt(doc.valor_mensal) !== mensal) frm.set_value("valor_mensal", mensal);
		} else if (flt(doc.valor_total) !== total) {
			frm.set_value("valor_total", total);
		}
	}

	// The final installment absorbs the rounding remainder so the sum is exact
	// (same rule as entre_hr.utils.prestacao_do_mes).
	const linhas = [];
	for (let k = 0; k < n; k++) {
		const idx = mes_idx + k;
		const ultima = k === n - 1 && n > 1 && total > 0;
		linhas.push({
			mes: `${entre_hr.periodo.MESES[idx % 12]} ${ano + Math.floor(idx / 12)}`,
			valor: ultima ? flt(total - mensal * (n - 1), 2) : mensal,
		});
	}
	entre_hr.periodo.render_simulador(frm, linhas);
};

entre_hr.periodo.render_simulador = function (frm, linhas) {
	const campo = frm.fields_dict.simulador_html;
	if (!campo) return;
	if (!linhas.length) {
		campo.$wrapper.html(
			`<div class="text-muted">${__("Preencha o período e o valor para simular os pagamentos.")}</div>`
		);
		return;
	}
	const moeda = (v) => frappe.format(v, { fieldtype: "Currency" });
	const corpo = linhas
		.map(
			(l) =>
				`<tr><td>${l.mes}</td><td style="text-align:right">${moeda(l.valor)}</td></tr>`
		)
		.join("");
	const total = linhas.reduce((soma, l) => soma + l.valor, 0);
	campo.$wrapper.html(`
		<table class="table table-bordered table-sm" style="max-width: 420px">
			<thead>
				<tr>
					<th>${__("Mês")}</th>
					<th style="text-align:right">${__("Valor")}</th>
				</tr>
			</thead>
			<tbody>${corpo}</tbody>
			<tfoot>
				<tr>
					<th>${__("Total")} (${linhas.length} ${linhas.length === 1 ? __("mês") : __("meses")})</th>
					<th style="text-align:right">${moeda(total)}</th>
				</tr>
			</tfoot>
		</table>`);
};
