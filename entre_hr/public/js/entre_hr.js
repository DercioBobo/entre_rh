// Entre HR — app-wide scripts

// Shared "Período" behaviour for Outras Deducoes / Outras Remuneracoes (month+year
// start via eventos()) and Emprestimo (date start via eventos_data()).
// The server (entre_hr.utils.derivar_periodo_pagamento / emprestimo.py) stays
// authoritative on save; this mirror only keeps the derived fields and the payment
// plan live while the user is typing, instead of appearing after the first save.
// The form handlers are registered at the bottom of this file (not in per-doctype
// .js files) so nothing depends on this asset being loaded first.
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
		entre_hr.periodo.render_plano(frm, []);
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
		entre_hr.periodo.render_plano(frm, []);
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

	// Payment plan: months already settled (from the pagamentos history written on
	// slip submit) in green with their slip, remaining months forecast in orange.
	// A pending month takes min(prestação, restante), so the final installment
	// carries the exact remainder (same rule as entre_hr.utils.prestacao_do_mes),
	// and months skipped in Saldo Devedor mode extend the plan past the schedule.
	const pagos_por_mes = {};
	let pago_total = 0;
	(doc.pagamentos || []).forEach((p) => {
		const chave = (p.data || "").slice(0, 7); // YYYY-MM
		(pagos_por_mes[chave] = pagos_por_mes[chave] || []).push(p);
		pago_total += flt(p.valor);
	});

	const linhas = [];
	let restante = flt(total - pago_total, 2);
	for (let k = 0; k < n + 36; k++) {
		if (k >= n && restante <= 0.005) break;
		const idx = mes_idx + k;
		const ano_k = ano + Math.floor(idx / 12);
		const chave = `${ano_k}-${pad((idx % 12) + 1)}`;
		const nome_mes = `${entre_hr.periodo.MESES[idx % 12]} ${ano_k}`;
		const pagos = pagos_por_mes[chave];
		if (pagos) {
			linhas.push({
				mes: nome_mes,
				valor: pagos.reduce((soma, p) => soma + flt(p.valor), 0),
				estado: "Pago",
				recibos: pagos.map((p) => p.recibo).filter(Boolean),
			});
		} else if (restante > 0.005) {
			const valor = flt(Math.min(flt(mensal), restante), 2);
			linhas.push({ mes: nome_mes, valor: valor, estado: "Pendente" });
			restante = flt(restante - valor, 2);
		}
	}
	entre_hr.periodo.render_plano(frm, linhas, {
		pago: pago_total,
		pendente: flt(total - pago_total, 2),
	});
};

entre_hr.periodo.render_plano = function (frm, linhas, resumo) {
	const campo = frm.fields_dict.simulador_html;
	if (!campo) return;
	if (!linhas.length) {
		campo.$wrapper.html(
			`<div class="text-muted">${__("Preencha o período e o valor para simular os pagamentos.")}</div>`
		);
		return;
	}
	const moeda = (v) => frappe.format(v, { fieldtype: "Currency" });
	const cabecalho = resumo
		? `<p><b>${__("Pago")}:</b> ${moeda(resumo.pago)} &nbsp;•&nbsp; <b>${__("Pendente")}:</b> ${moeda(resumo.pendente)}</p>`
		: "";
	const corpo = linhas
		.map((l) => {
			const estado =
				l.estado === "Pago"
					? `<span class="indicator-pill green">${__("Pago")}</span>${
							l.recibos && l.recibos.length
								? ` <small class="text-muted">${l.recibos.join(", ")}</small>`
								: ""
						}`
					: `<span class="indicator-pill orange">${__("Pendente")}</span>`;
			return `<tr><td>${l.mes}</td><td style="text-align:right">${moeda(l.valor)}</td><td>${estado}</td></tr>`;
		})
		.join("");
	const total = linhas.reduce((soma, l) => soma + l.valor, 0);
	campo.$wrapper.html(`
		${cabecalho}
		<table class="table table-bordered table-sm" style="max-width: 560px">
			<thead>
				<tr>
					<th>${__("Mês")}</th>
					<th style="text-align:right">${__("Valor")}</th>
					<th>${__("Estado")}</th>
				</tr>
			</thead>
			<tbody>${corpo}</tbody>
			<tfoot>
				<tr>
					<th>${__("Total")} (${linhas.length} ${linhas.length === 1 ? __("mês") : __("meses")})</th>
					<th style="text-align:right">${moeda(total)}</th>
					<th></th>
				</tr>
			</tfoot>
		</table>`);
};

// --- Ausencia: registo em massa ---------------------------------------------------
// One dialog, many employees: pick mês/ano, type faltas only where needed, and one
// click creates the individual Ausencia documents (the per-record data model, the
// controller validations and the approval workflow stay exactly as they are).

frappe.provide("entre_hr.ausencias");

entre_hr.ausencias.abrir = function (listview) {
	const hoje = new Date();
	const dialogo = new frappe.ui.Dialog({
		title: __("Registar Faltas em Massa"),
		size: "large",
		fields: [
			{
				fieldname: "mes",
				fieldtype: "Select",
				label: __("Mês"),
				options: entre_hr.periodo.MESES.join("\n"),
				default: entre_hr.periodo.MESES[hoje.getMonth()],
				reqd: 1,
				onchange: () => entre_hr.ausencias.carregar(dialogo),
			},
			{ fieldname: "col_1", fieldtype: "Column Break" },
			{
				fieldname: "ano",
				fieldtype: "Int",
				label: __("Ano"),
				default: hoje.getFullYear(),
				reqd: 1,
				onchange: () => entre_hr.ausencias.carregar(dialogo),
			},
			{ fieldname: "col_2", fieldtype: "Column Break" },
			{
				fieldname: "submeter",
				fieldtype: "Check",
				label: __("Submeter imediatamente"),
				default: 0,
				description: __("Sem passar pelo fluxo de aprovação — os registos ficam logo efectivos."),
			},
			{ fieldname: "sec_1", fieldtype: "Section Break" },
			{ fieldname: "grelha", fieldtype: "HTML" },
		],
		primary_action_label: __("Criar Registos"),
		primary_action: () => entre_hr.ausencias.criar(dialogo, listview),
	});
	dialogo.show();
	entre_hr.ausencias.carregar(dialogo);
};

entre_hr.ausencias.carregar = function (dialogo) {
	const mes = dialogo.get_value("mes");
	const ano = cint(dialogo.get_value("ano"));
	if (!mes || !ano) return;
	dialogo.fields_dict.grelha.$wrapper.html(
		`<div class="text-muted">${__("A carregar...")}</div>`
	);
	frappe.call({
		method: "entre_hr.ausencias.dados_registo_massa",
		args: { mes: mes, ano: ano },
		callback: (r) => entre_hr.ausencias.render(dialogo, r.message || {}),
	});
};

entre_hr.ausencias.render = function (dialogo, dados) {
	const wrapper = dialogo.fields_dict.grelha.$wrapper;
	const funcionarios = dados.funcionarios || [];
	const modo = dados.modo || "Por Dias";
	dialogo.modo_faltas = modo;
	if (!funcionarios.length) {
		wrapper.html(`<div class="text-muted">${__("Sem funcionários activos.")}</div>`);
		return;
	}
	const esc = frappe.utils.escape_html;
	const th_sticky = 'style="position:sticky;top:0;background:var(--card-bg);z-index:1"';
	const por_dias = modo === "Por Dias";
	const linhas = funcionarios
		.map((f) => {
			// Incremental registration is allowed: existing records only inform,
			// the input stays open to add more (the server enforces the limits).
			const input = por_dias
				? `<input type="text" class="form-control input-faltas" style="width:140px;margin-left:auto" placeholder="${__("ex.: 3, 5, 12")}" data-funcionario="${esc(f.name)}">`
				: `<input type="number" class="form-control input-faltas" style="width:90px;margin-left:auto" min="0" data-funcionario="${esc(f.name)}">`;
			let estado = "";
			if (f.existente) {
				const dias_txt =
					por_dias && (f.existente.dias || []).length
						? ` · ${__("dias")} ${f.existente.dias.join(", ")}`
						: "";
				estado = `<span class="indicator-pill blue">${cint(f.existente.total)} ${__("falta(s)")}</span> <small class="text-muted">${cint(f.existente.registos)} ${__("registo(s)")}${dias_txt}</small>`;
			}
			const texto = `${f.employee_name || ""} ${f.name} ${f.department || ""}`.toLowerCase();
			return `<tr class="linha-funcionario" data-texto="${esc(texto)}">
				<td>${esc(f.employee_name || f.name)}<br><small class="text-muted">${esc(f.name)}${f.department ? " · " + esc(f.department) : ""}</small></td>
				<td>${estado}</td>
				<td style="text-align:right">${input}</td>
			</tr>`;
		})
		.join("");
	wrapper.html(`
		<input type="text" class="form-control procura" placeholder="${__("Procurar funcionário...")}" style="margin-bottom:10px">
		<div style="max-height:45vh;overflow-y:auto;border:1px solid var(--border-color);border-radius:8px">
			<table class="table table-sm" style="margin:0">
				<thead>
					<tr>
						<th ${th_sticky}>${__("Funcionário")}</th>
						<th ${th_sticky}>${__("Já registado no mês")}</th>
						<th ${th_sticky} style="text-align:right">${por_dias ? __("Dias de Falta") : __("Nº de Faltas")}</th>
					</tr>
				</thead>
				<tbody>${linhas}</tbody>
			</table>
		</div>
		<p class="resumo text-muted" style="margin-top:8px"></p>`);

	const actualizar_resumo = () => {
		let com_faltas = 0;
		let total = 0;
		wrapper.find(".input-faltas").each(function () {
			const n = por_dias
				? entre_hr.ausencias.analisar_dias($(this).val()).length
				: cint($(this).val());
			if (n > 0) {
				com_faltas++;
				total += n;
			}
		});
		wrapper
			.find(".resumo")
			.text(
				com_faltas
					? __("{0} funcionário(s) · {1} falta(s) a registar", [com_faltas, total])
					: por_dias
						? __("Introduza os dias de falta (números do dia do mês) apenas nos funcionários que faltaram.")
						: __("Introduza o número de faltas apenas nos funcionários que faltaram.")
			);
	};
	wrapper.find(".input-faltas").on("input", actualizar_resumo);
	actualizar_resumo();

	wrapper.find(".procura").on("input", function () {
		const termo = ($(this).val() || "").toLowerCase();
		wrapper.find(".linha-funcionario").each(function () {
			$(this).toggle(!termo || $(this).data("texto").includes(termo));
		});
	});
};

entre_hr.ausencias.analisar_dias = function (texto) {
	const dias = [];
	String(texto || "")
		.split(/[\s,;.]+/)
		.forEach((parte) => {
			const dia = cint(parte);
			if (dia >= 1 && dia <= 31 && !dias.includes(dia)) dias.push(dia);
		});
	return dias.sort((a, b) => a - b);
};

entre_hr.ausencias.criar = function (dialogo, listview) {
	const por_dias = dialogo.modo_faltas !== "Por Total";
	const faltas = {};
	dialogo.fields_dict.grelha.$wrapper.find(".input-faltas").each(function () {
		if (por_dias) {
			const dias = entre_hr.ausencias.analisar_dias($(this).val());
			if (dias.length) faltas[$(this).attr("data-funcionario")] = dias;
		} else {
			const n = cint($(this).val());
			if (n > 0) faltas[$(this).attr("data-funcionario")] = n;
		}
	});
	if (!Object.keys(faltas).length) {
		frappe.msgprint(__("Introduza as faltas de pelo menos um funcionário."));
		return;
	}
	frappe.call({
		method: "entre_hr.ausencias.registar_massa",
		args: {
			mes: dialogo.get_value("mes"),
			ano: cint(dialogo.get_value("ano")),
			faltas: faltas,
			submeter: cint(dialogo.get_value("submeter")),
		},
		freeze: true,
		freeze_message: __("A criar registos de ausência..."),
		callback(r) {
			const resultado = r.message || {};
			dialogo.hide();
			let msg = __("Criados {0} registo(s) de ausência.", [
				(resultado.criadas || []).length,
			]);
			if ((resultado.ignoradas || []).length) {
				msg += "<br>" + __("Ignorados (já registados): {0}", [resultado.ignoradas.join(", ")]);
			}
			frappe.msgprint(msg);
			listview && listview.refresh();
		},
	});
};

frappe.listview_settings["Ausencia"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Registar em Massa"), () =>
			entre_hr.ausencias.abrir(listview)
		);
	},
};

// --- Form registrations --------------------------------------------------------

frappe.ui.form.on("Outras Deducoes", entre_hr.periodo.eventos());
frappe.ui.form.on("Outras Remuneracoes", entre_hr.periodo.eventos());
frappe.ui.form.on("Emprestimo", entre_hr.periodo.eventos_data());

// Ausencia: the form adapts to the company's entry mode (Settings), and in Por Dias
// mode n_de_faltas mirrors the days table live (the server re-derives on save).
entre_hr.ausencias.contar_dias = function (frm) {
	if (frm.modo_faltas === "Por Total" && !(frm.doc.dias || []).length) return;
	const n = (frm.doc.dias || []).filter((d) => d.data).length;
	if (cint(frm.doc.n_de_faltas) !== n) frm.set_value("n_de_faltas", n);
};

frappe.ui.form.on("Ausencia", {
	refresh(frm) {
		frappe.db
			.get_single_value("Entre HR Settings", "modo_registo_faltas")
			.then((modo) => {
				frm.modo_faltas = modo || "Por Dias";
				const por_dias = frm.modo_faltas === "Por Dias";
				frm.set_df_property("n_de_faltas", "read_only", por_dias ? 1 : 0);
				frm.set_df_property("dias", "reqd", por_dias ? 1 : 0);
			});
	},
	dias_add: entre_hr.ausencias.contar_dias,
	dias_remove: entre_hr.ausencias.contar_dias,
});

frappe.ui.form.on("Dia De Ausencia", {
	data(frm) {
		entre_hr.ausencias.contar_dias(frm);
	},
});
