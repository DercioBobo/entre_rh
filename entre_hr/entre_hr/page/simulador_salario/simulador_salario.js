// Simulador de Salário — desk page.
// Statutory parameters come from entre_hr.simulador.parametros (Entre HR Settings),
// so the simulator always matches payroll: INSS on taxable earnings, IRPS on the
// post-INSS base, per-dependents brackets. Works for employees (data pulled from
// Employee/SSA) and non-employees (typed manually).

frappe.pages["simulador-salario"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Simulador de Salário"),
		single_column: true,
	});
	frappe.call("entre_hr.simulador.parametros").then((r) => {
		new entre_hr_simulador.Simulador(page, r.message || {});
	});
};

frappe.provide("entre_hr_simulador");

entre_hr_simulador.COLUNAS = [
	{ id: "dependentes", label: __("Dep.") },
	{ id: "base", label: __("Salário Base") },
	{ id: "bonus", label: __("Bónus") },
	{ id: "bruto", label: __("Bruto") },
	{ id: "inss", label: __("INSS Func.") },
	{ id: "irps", label: __("IRPS") },
	{ id: "descontos", label: __("Total Desc.") },
	{ id: "liquido", label: __("Líquido") },
	{ id: "inss_emp", label: __("INSS Emp.") },
];

entre_hr_simulador.Simulador = class {
	constructor(page, params) {
		this.page = page;
		this.params = params;
		this.bonus = [];
		this.folha = [];
		this.colunas = this.carregar_colunas();
		this.montar();
	}

	// ---------------------------------------------------------------- cálculo
	fmt(n) {
		return (n || 0).toLocaleString("pt-MZ", {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
		});
	}

	calc_irps(base, dependentes) {
		const grupo = Math.min(Math.max(cint(dependentes), 0), cint(this.params.max_dependentes) || 4);
		let escalao = null;
		(this.params.irps_tabela || []).forEach((r) => {
			if (cint(r.dependentes) !== grupo || base < flt(r.limite_inferior)) return;
			if (!escalao || flt(r.limite_inferior) > flt(escalao.limite_inferior)) escalao = r;
		});
		if (!escalao) return { valor: 0, banda: __("isento") };
		return {
			valor: flt(escalao.parcela_fixa) + ((base - flt(escalao.limite_inferior)) * flt(escalao.taxa)) / 100,
			banda: `${flt(escalao.taxa)}%`,
		};
	}

	// Same semantics as payroll: INSS on the taxable total; IRPS on the post-INSS
	// base. Bónus marked "tributável" join the taxable base; the rest only add to
	// gross/net.
	calcular(base, dependentes, bonus) {
		base = flt(base);
		const trib_bonus = (bonus || []).filter((b) => b.tributavel).reduce((s, b) => s + flt(b.valor), 0);
		const isento = (bonus || []).filter((b) => !b.tributavel).reduce((s, b) => s + flt(b.valor), 0);
		const tributavel = base + trib_bonus;
		const inss = (tributavel * flt(this.params.taxa_inss)) / 100;
		const irps = this.calc_irps(tributavel - inss, dependentes);
		return {
			base: base,
			bonus_total: trib_bonus + isento,
			bruto: tributavel + isento,
			inss: inss,
			irps: irps.valor,
			banda: irps.banda,
			descontos: inss + irps.valor,
			liquido: tributavel + isento - inss - irps.valor,
			inss_emp: (tributavel * flt(this.params.taxa_inss_empregador)) / 100,
		};
	}

	inverter(liquido, dependentes) {
		const liq = (b) => this.calcular(b, dependentes, []).liquido;
		let lo = liquido;
		let hi = Math.max(liquido * 2, 1000);
		while (liq(hi) < liquido) hi *= 2;
		for (let i = 0; i < 80; i++) {
			const mid = (lo + hi) / 2;
			if (liq(mid) < liquido) lo = mid;
			else hi = mid;
		}
		return (lo + hi) / 2;
	}

	// ---------------------------------------------------------------- layout
	montar() {
		this.injectar_css();
		this.page.main.html(`
			<div class="sim-page">
				<div class="sim-tabs">
					<button class="sim-tab active" data-tab="individual">${__("Simulador Individual")}</button>
					<button class="sim-tab" data-tab="folha">${__("Folha de Simulação")}</button>
				</div>
				<div class="sim-sec active" data-sec="individual">
					<div class="sim-subtabs">
						<button class="sim-stab active" data-sub="directo">${__("Bruto → Líquido")}</button>
						<button class="sim-stab" data-sub="inverso">${__("Líquido → Bruto")}</button>
					</div>
					<div class="sim-sec active" data-sec="directo">
						<div class="sim-card">
							<p class="sim-title">${__("Dados")}</p>
							<div class="sim-grid3">
								<div class="sim-field sim-func-ind"></div>
								<div class="sim-field"><label>${__("Salário base (MZN)")}</label>
									<input type="number" class="sim-input" data-campo="base" value="25000" min="0" step="500"></div>
								<div class="sim-field"><label>${__("Dependentes")}</label>
									<select class="sim-input" data-campo="dependentes">${this.opcoes_dependentes()}</select></div>
							</div>
						</div>
						<div class="sim-card">
							<p class="sim-title">${__("Bónus / Subsídios")}</p>
							<div class="sim-bonus-list"></div>
							<button class="btn btn-xs btn-default sim-add-bonus">+ ${__("Adicionar bónus")}</button>
						</div>
						<div class="sim-metrics">
							<div class="sim-metric"><span>${__("Bruto")}</span><b data-m="bruto">–</b></div>
							<div class="sim-metric m-inss"><span>${__("INSS")} (${flt(this.params.taxa_inss)}%)</span><b data-m="inss">–</b></div>
							<div class="sim-metric m-irps"><span>${__("IRPS")}</span><b data-m="irps">–</b></div>
							<div class="sim-metric m-liq"><span>${__("Líquido")}</span><b data-m="liquido">–</b></div>
						</div>
						<div class="sim-bar"><div data-b="liq" style="background:#0a8a65"></div><div data-b="inss" style="background:#c05621"></div><div data-b="irps" style="background:#c0392b"></div><div data-b="bonus" style="background:#1a6faf"></div></div>
						<div class="sim-card">
							<p class="sim-title">${__("Demonstração detalhada")}</p>
							<table class="sim-breakdown"><tbody></tbody></table>
						</div>
					</div>
					<div class="sim-sec" data-sec="inverso">
						<div class="sim-card">
							<p class="sim-title">${__("Definir líquido pretendido")}</p>
							<div class="sim-grid3">
								<div class="sim-field"><label>${__("Líquido desejado (MZN)")}</label>
									<input type="number" class="sim-input" data-campo="inv-liquido" value="20000" min="0" step="500"></div>
								<div class="sim-field"><label>${__("Dependentes")}</label>
									<select class="sim-input" data-campo="inv-dependentes">${this.opcoes_dependentes()}</select></div>
							</div>
						</div>
						<div class="sim-card">
							<div class="sim-hero">${__("Salário base necessário")}: <b data-m="inv-bruto">–</b> MZN</div>
							<table class="sim-breakdown"><tbody class="inv-breakdown"></tbody></table>
						</div>
					</div>
				</div>
				<div class="sim-sec" data-sec="folha">
					<div class="sim-toolbar">
						<button class="btn btn-sm btn-primary sim-add-func">${__("Adicionar pessoa")}</button>
						<button class="btn btn-sm btn-default sim-carregar">${__("Carregar Funcionários Activos")}</button>
						<span class="sim-spacer"></span>
						<button class="btn btn-sm btn-default sim-colunas">${__("Colunas")}</button>
						<button class="btn btn-sm btn-default sim-csv">${__("Exportar CSV")}</button>
						<button class="btn btn-sm btn-default sim-print">${__("Imprimir")}</button>
						<button class="btn btn-sm btn-danger sim-limpar">${__("Limpar")}</button>
					</div>
					<div class="sim-folha-wrap"><table class="sim-folha"><thead></thead><tbody></tbody></table></div>
					<div class="sim-empty text-muted">${__("Ninguém na folha. Adicione uma pessoa (funcionário ou não) ou carregue os funcionários activos.")}</div>
					<div class="sim-metrics sim-totais" style="display:none"></div>
				</div>
			</div>`);

		// tabs
		this.page.main.find(".sim-tab").on("click", (e) => {
			const tab = $(e.currentTarget).data("tab");
			this.page.main.find(".sim-tab").removeClass("active");
			$(e.currentTarget).addClass("active");
			this.page.main.find("> .sim-page > .sim-sec, .sim-page > .sim-sec").removeClass("active");
			this.page.main.find(`.sim-page > .sim-sec[data-sec='${tab}']`).addClass("active");
		});
		this.page.main.find(".sim-stab").on("click", (e) => {
			const sub = $(e.currentTarget).data("sub");
			this.page.main.find(".sim-stab").removeClass("active");
			$(e.currentTarget).addClass("active");
			this.page.main.find("[data-sec='individual'] > .sim-sec").removeClass("active");
			this.page.main.find(`[data-sec='individual'] > .sim-sec[data-sec='${sub}']`).addClass("active");
		});

		// individual: employee picker (optional — non-employees just type values)
		this.func_individual = frappe.ui.form.make_control({
			parent: this.page.main.find(".sim-func-ind"),
			df: {
				fieldtype: "Link",
				options: "Employee",
				label: __("Funcionário (opcional)"),
				get_query: () => ({ filters: { status: "Active" } }),
				onchange: () => {
					const valor = this.func_individual.get_value();
					if (!valor) return;
					frappe.call("entre_hr.simulador.dados_funcionario", { funcionario: valor }).then((r) => {
						const d = r.message;
						this.page.main.find("[data-campo='base']").val(d.base);
						this.page.main.find("[data-campo='dependentes']").val(String(d.dependentes));
						this.calcular_individual();
					});
				},
			},
			render_input: true,
		});

		this.page.main.find("[data-campo='base'],[data-campo='dependentes']").on("input change", () => this.calcular_individual());
		this.page.main.find("[data-campo='inv-liquido'],[data-campo='inv-dependentes']").on("input change", () => this.calcular_inverso());
		this.page.main.find(".sim-add-bonus").on("click", () => {
			this.bonus.push({ id: Date.now(), label: "", valor: 0, tributavel: 0 });
			this.render_bonus();
		});
		this.page.main.find(".sim-add-func").on("click", () => this.dialogo_pessoa());
		this.page.main.find(".sim-carregar").on("click", () => this.carregar_funcionarios());
		this.page.main.find(".sim-colunas").on("click", () => this.dialogo_colunas());
		this.page.main.find(".sim-csv").on("click", () => this.exportar_csv());
		this.page.main.find(".sim-print").on("click", () => this.imprimir());
		this.page.main.find(".sim-limpar").on("click", () => {
			if (!this.folha.length) return;
			frappe.confirm(__("Limpar toda a folha de simulação?"), () => {
				this.folha = [];
				this.render_folha();
			});
		});

		this.render_bonus();
		this.calcular_individual();
		this.calcular_inverso();
		this.render_folha();
	}

	opcoes_dependentes() {
		return [0, 1, 2, 3, 4]
			.map((n) => `<option value="${n}">${n === 4 ? __("4 ou mais") : n} ${n === 1 ? __("dependente") : __("dependentes")}</option>`)
			.join("");
	}

	// ---------------------------------------------------------------- individual
	render_bonus() {
		const lista = this.page.main.find(".sim-bonus-list");
		lista.html(
			this.bonus
				.map(
					(b) => `
			<div class="sim-bonus-row" data-id="${b.id}">
				<input type="text" class="sim-input" placeholder="${__("Descrição")}" value="${frappe.utils.escape_html(b.label)}" data-b="label">
				<input type="number" class="sim-input" placeholder="MZN" value="${b.valor}" min="0" step="100" data-b="valor">
				<label class="sim-check"><input type="checkbox" data-b="tributavel" ${b.tributavel ? "checked" : ""}> ${__("Tributável")}</label>
				<button class="btn btn-xs btn-default" data-b="remover">✕</button>
			</div>`
				)
				.join("")
		);
		lista.find("[data-b='label'],[data-b='valor']").on("input", (e) => {
			const row = $(e.currentTarget).closest(".sim-bonus-row");
			const b = this.bonus.find((x) => x.id === cint(row.attr("data-id")));
			b[$(e.currentTarget).attr("data-b")] = $(e.currentTarget).attr("data-b") === "valor" ? flt(e.currentTarget.value) : e.currentTarget.value;
			this.calcular_individual();
		});
		lista.find("[data-b='tributavel']").on("change", (e) => {
			const row = $(e.currentTarget).closest(".sim-bonus-row");
			this.bonus.find((x) => x.id === cint(row.attr("data-id"))).tributavel = e.currentTarget.checked ? 1 : 0;
			this.calcular_individual();
		});
		lista.find("[data-b='remover']").on("click", (e) => {
			const id = cint($(e.currentTarget).closest(".sim-bonus-row").attr("data-id"));
			this.bonus = this.bonus.filter((x) => x.id !== id);
			this.render_bonus();
			this.calcular_individual();
		});
	}

	calcular_individual() {
		const base = flt(this.page.main.find("[data-campo='base']").val());
		const dependentes = this.page.main.find("[data-campo='dependentes']").val();
		const r = this.calcular(base, dependentes, this.bonus);
		["bruto", "inss", "irps", "liquido"].forEach((m) =>
			this.page.main.find(`[data-m='${m}']`).text(this.fmt(r[m]))
		);
		const total = r.bruto || 1;
		this.page.main.find("[data-b='liq']").css("width", `${Math.max(0, ((r.liquido - r.bonus_total) / total) * 100)}%`);
		this.page.main.find("[data-b='inss']").css("width", `${(r.inss / total) * 100}%`);
		this.page.main.find("[data-b='irps']").css("width", `${(r.irps / total) * 100}%`);
		this.page.main.find("[data-b='bonus']").css("width", `${(r.bonus_total / total) * 100}%`);

		let linhas = `
			<tr><td>${__("Salário base")}</td><td>${this.fmt(base)} MZN</td></tr>
			<tr class="v-orange"><td>(−) ${__("INSS")} <span class="sim-badge">${flt(this.params.taxa_inss)}%</span></td><td>− ${this.fmt(r.inss)} MZN</td></tr>
			<tr class="v-red"><td>(−) ${__("IRPS")} <span class="sim-badge">${r.banda}</span></td><td>− ${this.fmt(r.irps)} MZN</td></tr>`;
		this.bonus.forEach((b) => {
			if (flt(b.valor) > 0)
				linhas += `<tr class="v-blue"><td>(+) ${frappe.utils.escape_html(b.label || __("Bónus"))} <span class="sim-badge">${b.tributavel ? __("tributável") : __("sem desconto")}</span></td><td>+ ${this.fmt(flt(b.valor))} MZN</td></tr>`;
		});
		linhas += `<tr class="sim-total"><td>${__("Salário líquido total")}</td><td>${this.fmt(r.liquido)} MZN</td></tr>`;
		this.page.main.find("[data-sec='directo'] .sim-breakdown tbody").html(linhas);
	}

	calcular_inverso() {
		const desejado = flt(this.page.main.find("[data-campo='inv-liquido']").val());
		const dependentes = this.page.main.find("[data-campo='inv-dependentes']").val();
		if (desejado <= 0) return;
		const base = this.inverter(desejado, dependentes);
		const r = this.calcular(base, dependentes, []);
		this.page.main.find("[data-m='inv-bruto']").text(this.fmt(base));
		this.page.main.find(".inv-breakdown").html(`
			<tr><td>${__("Salário base necessário")}</td><td>${this.fmt(base)} MZN</td></tr>
			<tr class="v-orange"><td>(−) ${__("INSS")} <span class="sim-badge">${flt(this.params.taxa_inss)}%</span></td><td>− ${this.fmt(r.inss)} MZN</td></tr>
			<tr class="v-red"><td>(−) ${__("IRPS")} <span class="sim-badge">${r.banda}</span></td><td>− ${this.fmt(r.irps)} MZN</td></tr>
			<tr><td>${__("Custo empresa (INSS ${0}%)", [flt(this.params.taxa_inss_empregador)])}</td><td>${this.fmt(base + r.inss_emp)} MZN</td></tr>
			<tr class="sim-total"><td>= ${__("Salário líquido")}</td><td>${this.fmt(r.liquido)} MZN</td></tr>`);
	}

	// ---------------------------------------------------------------- folha
	carregar_colunas() {
		try {
			const guardado = JSON.parse(localStorage.getItem("entre_hr_sim_colunas"));
			if (Array.isArray(guardado) && guardado.length) return guardado;
		} catch (e) {
			/* primeiro uso */
		}
		return entre_hr_simulador.COLUNAS.map((c) => c.id);
	}

	dialogo_colunas() {
		const dialogo = new frappe.ui.Dialog({
			title: __("Colunas visíveis"),
			fields: entre_hr_simulador.COLUNAS.map((c) => ({
				fieldname: c.id,
				fieldtype: "Check",
				label: c.label,
				default: this.colunas.includes(c.id) ? 1 : 0,
			})),
			primary_action_label: __("Aplicar"),
			primary_action: (valores) => {
				this.colunas = entre_hr_simulador.COLUNAS.filter((c) => cint(valores[c.id])).map((c) => c.id);
				localStorage.setItem("entre_hr_sim_colunas", JSON.stringify(this.colunas));
				dialogo.hide();
				this.render_folha();
			},
		});
		dialogo.show();
	}

	colunas_visiveis() {
		return entre_hr_simulador.COLUNAS.filter((c) => this.colunas.includes(c.id));
	}

	valores_linha(pessoa) {
		const r = this.calcular(pessoa.base, pessoa.dependentes, pessoa.bonus);
		return {
			dependentes: cint(pessoa.dependentes) >= 4 ? "4+" : String(cint(pessoa.dependentes)),
			base: this.fmt(r.base),
			bonus: r.bonus_total > 0 ? `+ ${this.fmt(r.bonus_total)}` : "—",
			bruto: this.fmt(r.bruto),
			inss: `− ${this.fmt(r.inss)}`,
			irps: `− ${this.fmt(r.irps)}`,
			descontos: `− ${this.fmt(r.descontos)}`,
			liquido: this.fmt(r.liquido),
			inss_emp: `+ ${this.fmt(r.inss_emp)}`,
			_r: r,
		};
	}

	totais() {
		const t = { base: 0, bonus: 0, bruto: 0, inss: 0, irps: 0, descontos: 0, liquido: 0, inss_emp: 0 };
		this.folha.forEach((p) => {
			const r = this.calcular(p.base, p.dependentes, p.bonus);
			t.base += r.base;
			t.bonus += r.bonus_total;
			t.bruto += r.bruto;
			t.inss += r.inss;
			t.irps += r.irps;
			t.descontos += r.descontos;
			t.liquido += r.liquido;
			t.inss_emp += r.inss_emp;
		});
		return t;
	}

	render_folha() {
		const visiveis = this.colunas_visiveis();
		const thead = this.page.main.find(".sim-folha thead");
		const tbody = this.page.main.find(".sim-folha tbody");
		const vazio = this.page.main.find(".sim-empty");
		const totais_el = this.page.main.find(".sim-totais");
		const classe = { inss: "v-orange", irps: "v-red", descontos: "v-red", liquido: "v-teal", bonus: "v-blue", inss_emp: "v-purple" };

		thead.html(
			`<tr><th>#</th><th>${__("Nome")}</th>${visiveis.map((c) => `<th>${c.label}</th>`).join("")}<th></th></tr>`
		);
		if (!this.folha.length) {
			tbody.html("");
			vazio.show();
			totais_el.hide();
			return;
		}
		vazio.hide();

		tbody.html(
			this.folha
				.map((p, i) => {
					const v = this.valores_linha(p);
					return `<tr data-id="${p.id}">
						<td class="text-muted">${i + 1}</td>
						<td><b>${frappe.utils.escape_html(p.nome)}</b>${p.funcionario ? ` <span class="sim-badge">${frappe.utils.escape_html(p.funcionario)}</span>` : ""}</td>
						${visiveis.map((c) => `<td class="sim-mono ${classe[c.id] || ""}">${v[c.id]}</td>`).join("")}
						<td class="sim-acoes"><button class="btn btn-xs btn-default" data-acao="editar">${__("Editar")}</button>
						<button class="btn btn-xs btn-default" data-acao="remover">✕</button></td>
					</tr>`;
				})
				.join("")
		);
		const t = this.totais();
		tbody.append(
			`<tr class="sim-total-row"><td colspan="2">${__("TOTAIS")} (${this.folha.length})</td>
			${visiveis.map((c) => `<td class="sim-mono ${classe[c.id] || ""}">${c.id === "dependentes" ? "" : this.fmt(t[c.id] !== undefined ? t[c.id] : 0)}</td>`).join("")}<td></td></tr>`
		);
		tbody.find("[data-acao='editar']").on("click", (e) => {
			this.dialogo_pessoa(cint($(e.currentTarget).closest("tr").attr("data-id")));
		});
		tbody.find("[data-acao='remover']").on("click", (e) => {
			const id = cint($(e.currentTarget).closest("tr").attr("data-id"));
			this.folha = this.folha.filter((p) => p.id !== id);
			this.render_folha();
		});

		totais_el
			.show()
			.css("display", "grid")
			.html(`
				<div class="sim-metric"><span>${__("Pessoas")}</span><b>${this.folha.length}</b></div>
				<div class="sim-metric"><span>${__("Massa salarial")}</span><b>${this.fmt(t.bruto)}</b></div>
				<div class="sim-metric m-inss"><span>${__("INSS func.")}</span><b>${this.fmt(t.inss)}</b></div>
				<div class="sim-metric m-irps"><span>${__("IRPS")}</span><b>${this.fmt(t.irps)}</b></div>
				<div class="sim-metric m-liq"><span>${__("Líquido total")}</span><b>${this.fmt(t.liquido)}</b></div>
				<div class="sim-metric"><span>${__("INSS empresa")}</span><b>${this.fmt(t.inss_emp)}</b></div>`);
	}

	dialogo_pessoa(id = null) {
		const existente = id ? this.folha.find((p) => p.id === id) : null;
		let bonus = existente ? existente.bonus.map((b) => ({ ...b })) : [];
		const dialogo = new frappe.ui.Dialog({
			title: existente ? __("Editar pessoa") : __("Adicionar pessoa"),
			fields: [
				{
					fieldname: "funcionario",
					fieldtype: "Link",
					options: "Employee",
					label: __("Funcionário (vazio = pessoa externa)"),
					default: existente ? existente.funcionario : null,
					get_query: () => ({ filters: { status: "Active" } }),
					onchange: () => {
						const valor = dialogo.get_value("funcionario");
						if (!valor) return;
						frappe.call("entre_hr.simulador.dados_funcionario", { funcionario: valor }).then((r) => {
							dialogo.set_value("nome", r.message.nome);
							dialogo.set_value("dependentes", String(r.message.dependentes));
							dialogo.set_value("base", r.message.base);
						});
					},
				},
				{ fieldname: "nome", fieldtype: "Data", label: __("Nome"), reqd: 1, default: existente ? existente.nome : "" },
				{ fieldname: "col_1", fieldtype: "Column Break" },
				{
					fieldname: "dependentes",
					fieldtype: "Select",
					label: __("Dependentes"),
					options: "0\n1\n2\n3\n4",
					default: existente ? String(existente.dependentes) : "0",
				},
				{ fieldname: "base", fieldtype: "Currency", label: __("Salário base (MZN)"), default: existente ? existente.base : 0 },
				{ fieldname: "sec_1", fieldtype: "Section Break", label: __("Bónus / Subsídios") },
				{ fieldname: "bonus_html", fieldtype: "HTML" },
			],
			primary_action_label: existente ? __("Guardar") : __("Adicionar"),
			primary_action: (valores) => {
				const pessoa = {
					id: existente ? existente.id : Date.now(),
					funcionario: valores.funcionario || null,
					nome: valores.nome,
					dependentes: cint(valores.dependentes),
					base: flt(valores.base),
					bonus: bonus.filter((b) => flt(b.valor) > 0),
				};
				if (existente) Object.assign(existente, pessoa);
				else this.folha.push(pessoa);
				dialogo.hide();
				this.render_folha();
			},
		});

		const render_bonus_dialogo = () => {
			const wrapper = dialogo.fields_dict.bonus_html.$wrapper;
			wrapper.html(
				bonus
					.map(
						(b, i) => `
				<div class="sim-bonus-row" data-i="${i}">
					<input type="text" class="sim-input" placeholder="${__("Descrição")}" value="${frappe.utils.escape_html(b.label)}" data-b="label">
					<input type="number" class="sim-input" placeholder="MZN" value="${b.valor}" min="0" data-b="valor">
					<label class="sim-check"><input type="checkbox" data-b="tributavel" ${b.tributavel ? "checked" : ""}> ${__("Tributável")}</label>
					<button class="btn btn-xs btn-default" data-b="remover">✕</button>
				</div>`
					)
					.join("") +
					`<button class="btn btn-xs btn-default sim-add-b">+ ${__("Adicionar bónus")}</button>`
			);
			wrapper.find("[data-b='label'],[data-b='valor']").on("input", (e) => {
				const b = bonus[cint($(e.currentTarget).closest(".sim-bonus-row").attr("data-i"))];
				b[$(e.currentTarget).attr("data-b")] = $(e.currentTarget).attr("data-b") === "valor" ? flt(e.currentTarget.value) : e.currentTarget.value;
			});
			wrapper.find("[data-b='tributavel']").on("change", (e) => {
				bonus[cint($(e.currentTarget).closest(".sim-bonus-row").attr("data-i"))].tributavel = e.currentTarget.checked ? 1 : 0;
			});
			wrapper.find("[data-b='remover']").on("click", (e) => {
				bonus.splice(cint($(e.currentTarget).closest(".sim-bonus-row").attr("data-i")), 1);
				render_bonus_dialogo();
			});
			wrapper.find(".sim-add-b").on("click", () => {
				bonus.push({ label: "", valor: 0, tributavel: 0 });
				render_bonus_dialogo();
			});
		};
		render_bonus_dialogo();
		dialogo.show();
	}

	carregar_funcionarios() {
		frappe.call({
			method: "entre_hr.simulador.funcionarios_activos",
			freeze: true,
			freeze_message: __("A carregar funcionários..."),
			callback: (r) => {
				const existentes = new Set(this.folha.map((p) => p.funcionario).filter(Boolean));
				let adicionados = 0;
				(r.message || []).forEach((f, i) => {
					if (existentes.has(f.funcionario)) return;
					this.folha.push({
						id: Date.now() + i,
						funcionario: f.funcionario,
						nome: f.nome,
						dependentes: cint(f.dependentes),
						base: flt(f.base),
						bonus: [],
					});
					adicionados++;
				});
				this.render_folha();
				frappe.show_alert({ message: __("{0} funcionário(s) adicionados.", [adicionados]), indicator: "green" });
			},
		});
	}

	// ---------------------------------------------------------------- exportar
	exportar_csv() {
		if (!this.folha.length) return frappe.msgprint(__("Ninguém na folha."));
		const visiveis = this.colunas_visiveis();
		const limpar = (v) => String(v).replace(/[−+\s]/g, (m) => (m === "−" ? "-" : "")).replace(/\./g, "").replace(",", ".");
		let csv = `${__("Nome")},${visiveis.map((c) => c.label).join(",")}\n`;
		this.folha.forEach((p) => {
			const v = this.valores_linha(p);
			csv += `"${p.nome}",${visiveis.map((c) => (c.id === "dependentes" ? v[c.id] : limpar(v[c.id]))).join(",")}\n`;
		});
		const t = this.totais();
		csv += `"TOTAL (${this.folha.length})",${visiveis.map((c) => (c.id === "dependentes" ? "" : (t[c.id] || 0).toFixed(2))).join(",")}\n`;
		const a = document.createElement("a");
		a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" }));
		a.download = `simulacao_salarios_${frappe.datetime.get_today()}.csv`;
		a.click();
	}

	imprimir() {
		if (!this.folha.length) return frappe.msgprint(__("Ninguém na folha."));
		const visiveis = this.colunas_visiveis();
		const t = this.totais();
		const empresa = frappe.defaults.get_default("company") || "";
		const linhas = this.folha
			.map((p, i) => {
				const v = this.valores_linha(p);
				return `<tr><td>${i + 1}</td><td>${frappe.utils.escape_html(p.nome)}</td>${visiveis.map((c) => `<td class="num">${v[c.id]}</td>`).join("")}</tr>`;
			})
			.join("");
		const janela = window.open("", "_blank");
		janela.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${__("Simulação de Salários")}</title>
			<style>
				body{font-family:Arial,sans-serif;font-size:12px;color:#111;padding:24px}
				h2{margin:0 0 2px}p{margin:0 0 16px;color:#666}
				table{width:100%;border-collapse:collapse}
				th,td{border:1px solid #ccc;padding:6px 8px;text-align:left}
				th{background:#f2f2f2;font-size:11px;text-transform:uppercase}
				.num{text-align:right;font-family:monospace}
				tfoot td{font-weight:bold;background:#f9f9f9}
			</style></head><body>
			<h2>${__("Simulação de Salários")}${empresa ? " — " + frappe.utils.escape_html(empresa) : ""}</h2>
			<p>${__("Gerado em")} ${frappe.datetime.now_datetime()} · ${__("Apenas para efeitos de simulação")}</p>
			<table><thead><tr><th>#</th><th>${__("Nome")}</th>${visiveis.map((c) => `<th>${c.label}</th>`).join("")}</tr></thead>
			<tbody>${linhas}</tbody>
			<tfoot><tr><td colspan="2">${__("TOTAIS")} (${this.folha.length})</td>${visiveis.map((c) => `<td class="num">${c.id === "dependentes" ? "" : this.fmt(t[c.id] || 0)}</td>`).join("")}</tr></tfoot>
			</table></body></html>`);
		janela.document.close();
		janela.onload = () => janela.print();
	}

	// ---------------------------------------------------------------- estilo
	injectar_css() {
		if ($("#sim-salario-css").length) return;
		$("head").append(`<style id="sim-salario-css">
			.sim-page{max-width:1100px;margin:0 auto;padding-bottom:40px}
			.sim-tabs{display:flex;gap:6px;margin-bottom:14px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:5px}
			.sim-tab{flex:1;height:36px;border:none;border-radius:8px;background:transparent;color:var(--text-muted);font-size:13px;font-weight:500;cursor:pointer}
			.sim-tab.active{background:rgba(10,138,101,.12);color:#0a8a65}
			.sim-subtabs{display:flex;gap:5px;margin-bottom:12px}
			.sim-stab{height:30px;padding:0 14px;border:none;border-radius:8px;background:transparent;color:var(--text-muted);font-size:12px;cursor:pointer}
			.sim-stab.active{background:rgba(10,138,101,.12);color:#0a8a65}
			.sim-sec{display:none}.sim-sec.active{display:block}
			.sim-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:12px;padding:16px;margin-bottom:12px}
			.sim-title{font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
			.sim-grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
			@media(max-width:640px){.sim-grid3{grid-template-columns:1fr}}
			.sim-field label{font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px}
			.sim-input{height:32px;width:100%;border-radius:8px;border:1px solid var(--border-color);background:var(--control-bg);color:var(--text-color);padding:0 10px;font-size:13px;outline:none}
			.sim-input:focus{border-color:#0a8a65}
			.sim-bonus-row{display:grid;grid-template-columns:1fr 130px auto 32px;gap:8px;align-items:center;margin-bottom:8px}
			.sim-check{font-size:12px;color:var(--text-muted);white-space:nowrap;margin:0;display:flex;align-items:center;gap:4px}
			.sim-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}
			.sim-totais{grid-template-columns:repeat(6,1fr);margin-top:12px}
			@media(max-width:700px){.sim-metrics,.sim-totais{grid-template-columns:repeat(2,1fr)}}
			.sim-metric{background:var(--card-bg);border:1px solid var(--border-color);border-radius:12px;padding:12px 14px}
			.sim-metric span{font-size:11px;font-weight:500;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;display:block;margin-bottom:4px}
			.sim-metric b{font-family:monospace;font-size:16px;color:var(--text-color)}
			.sim-metric.m-liq b,.sim-metric.m-liq span{color:#0a8a65}
			.sim-metric.m-inss b,.sim-metric.m-inss span{color:#c05621}
			.sim-metric.m-irps b,.sim-metric.m-irps span{color:#c0392b}
			.sim-bar{height:8px;border-radius:99px;overflow:hidden;display:flex;background:var(--border-color);margin-bottom:12px}
			.sim-bar div{height:100%;transition:width .3s}
			.sim-breakdown{width:100%;border-collapse:collapse}
			.sim-breakdown td{padding:8px 0;font-size:13px;border-bottom:1px solid var(--border-color)}
			.sim-breakdown td:last-child{text-align:right;font-family:monospace}
			.sim-breakdown tr:last-child td{border-bottom:none}
			.sim-breakdown .sim-total td{font-size:15px;font-weight:600;border-top:2px solid var(--border-color)}
			.sim-breakdown .sim-total td:last-child{color:#0a8a65}
			.sim-badge{font-size:10px;font-weight:600;padding:2px 6px;border-radius:5px;background:var(--border-color);color:var(--text-muted);margin-left:4px}
			.sim-hero{font-size:14px;color:var(--text-muted);margin-bottom:10px}
			.sim-hero b{font-family:monospace;font-size:24px;color:#6d45b0;margin:0 4px}
			.sim-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
			.sim-spacer{flex:1}
			.sim-folha-wrap{overflow-x:auto;border:1px solid var(--border-color);border-radius:12px}
			.sim-folha{width:100%;border-collapse:collapse;font-size:13px;min-width:800px}
			.sim-folha th{padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);border-bottom:1px solid var(--border-color);text-align:left;white-space:nowrap;background:var(--control-bg)}
			.sim-folha td{padding:8px 12px;border-bottom:1px solid var(--border-color)}
			.sim-folha tr:last-child td{border-bottom:none}
			.sim-mono{font-family:monospace;font-size:12px;white-space:nowrap}
			.sim-folha .v-red{color:#c0392b}.sim-folha .v-orange{color:#c05621}
			.sim-folha .v-teal{color:#0a8a65;font-weight:600}.sim-folha .v-blue{color:#1a6faf}.sim-folha .v-purple{color:#6d45b0}
			.sim-breakdown .v-red td:last-child{color:#c0392b}.sim-breakdown .v-orange td:last-child{color:#c05621}.sim-breakdown .v-blue td:last-child{color:#1a6faf}
			.sim-total-row td{font-weight:600;background:var(--control-bg)}
			.sim-acoes{white-space:nowrap}
			.sim-empty{text-align:center;padding:40px 0}
		</style>`);
	}
};
