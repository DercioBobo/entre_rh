const FOLHA_MESES = [
	"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
	"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

frappe.query_reports["Folha de Salario"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_default("company"),
		},
		{
			fieldname: "mes",
			label: __("Mês"),
			fieldtype: "Select",
			options: FOLHA_MESES.join("\n"),
			reqd: 1,
			default: FOLHA_MESES[new Date().getMonth()],
		},
		{
			fieldname: "ano",
			label: __("Ano"),
			fieldtype: "Int",
			reqd: 1,
			default: new Date().getFullYear(),
		},
	],

	onload(report) {
		// The print dialog's settings reach only Frappe's outer wrapper (which adds the
		// letter head), not this report's template. Record whether a letter head was
		// chosen so folha_de_salario.html can skip its own company header in that case.
		["print_report", "pdf_report"].forEach((metodo) => {
			const original = report[metodo];
			if (typeof original !== "function") return;
			report[metodo] = function (print_settings) {
				report.folha_com_timbrado = !!(print_settings && print_settings.letter_head);
				return original.apply(this, arguments);
			};
		});
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.is_total ? `<b>${value}</b>` : value;
	},
};
