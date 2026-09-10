frappe.query_reports["Saldos de Férias"] = {
	filters: [
		{
			fieldname: "data_referencia",
			label: __("Data de Referência"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
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
		{
			fieldname: "leave_type",
			label: __("Tipo de Licença"),
			fieldtype: "Link",
			options: "Leave Type",
			get_query: () => ({ filters: { is_lwp: 0 } }),
		},
		{
			fieldname: "incluir_inactivos",
			label: __("Incluir inactivos"),
			fieldtype: "Check",
		},
	],
};
