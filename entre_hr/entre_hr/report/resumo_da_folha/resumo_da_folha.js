frappe.query_reports["Resumo da Folha"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("De"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Até"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "funcionario",
			label: __("Funcionário"),
			fieldtype: "Link",
			options: "Employee",
		},
	],
};
