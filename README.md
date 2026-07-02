# Entre HR (`entre_hr`)

HR + payroll app for a company in Mozambique (Metical, Mozambican labour rules), built on
**Frappe / ERPNext / HRMS**.

## Install

```bash
bench get-app entre_hr <this repo url>
bench --site <site> install-app entre_hr
```

Requires `frappe`, `erpnext`, and `hrms` on the bench.

## Conventions

### Employee-native principle

There is **no separate "person" doctype** mirroring Employee. Every feature links to and
keys on the HRMS `Employee` doctype directly. Money documents are Employee-primary: each
carries `funcionario` (Link → Employee) plus a read-only `funcionario_nome` fetched from
`funcionario.employee_name`. This avoids two-record desync bugs by construction.

### Naming series

| Kind                          | Series          | Example       |
|-------------------------------|-----------------|---------------|
| Master / entity records       | `XXX-.##`       | `EMP-01`      |
| Transactional records         | `XXX-.YY.-.##`  | `AUS-26-.01`  |

`YY` is the 2-digit year.

### Doctype naming

Doctype names are **ASCII** (e.g. `Ausencia`, `Justificacao De Faltas`); user-facing
labels and prose keep the accents (Ausência, Justificação).

### Link filters

Every Link → Employee field this app creates carries `link_filters` excluding terminated
staff: `[["Employee","status","!=","Left"]]` (constant `EMPLOYEE_LINK_FILTERS` in
`entre_hr/utils.py`).

### Configuration

All configuration lives in the single doctype **`Entre HR Settings`** — nothing is
hard-coded (salary structure, payable account, salary components, leave type, statutory
flags, etc.).

### Approvals

Submittable documents apply their effect in `on_submit`. The approval flow itself is
configured by the operator in Frappe's **built-in Workflow** (approved state → docstatus
1); this app ships no Workflow fixture.

## Roles

- `Aprovador RH` — approves HR money documents.
- `RH Manager` — manages HR configuration and salaries (used alongside System Manager).

## Build plan

See [BUILD_PLAN.md](BUILD_PLAN.md) for the phase-by-phase playbook.
