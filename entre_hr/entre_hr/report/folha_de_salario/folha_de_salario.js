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

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.is_total ? `<b>${value}</b>` : value;
	},
};
