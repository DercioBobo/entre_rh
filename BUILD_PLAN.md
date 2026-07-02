# Entre HR — Build Plan

A guided, phase-by-phase playbook to build **Entre HR** (Frappe app `entre_hr`): a
generic-company HR + payroll app built on Frappe / ERPNext / HRMS, for a normal company
in Mozambique (Metical currency, Mozambican labour rules).

## How to use this

- Each phase is **one prompt you run + an acceptance check**.
- Run phases **in order** — the dependency chain is real (you can't assemble a salary
  slip before base salary exists).
- **Do not advance** to phase N+1 until phase N's acceptance check passes.
- Paste each phase's prompt block into your AI/dev session working in the `entre_hr`
  bench.
- The **spec** under each prompt gives the exact rules, formulas, and fields — build to
  the spec, not to intuition.

## Foundational principles (apply throughout)

- **Employee-native.** We work directly on the HRMS `Employee` doctype. There is no
  separate "person" doctype mirroring Employee — every feature links to and keys on
  `Employee`. This avoids an entire class of two-record desync bugs.
- **Naming series.** Master/entity records use `XXX-.##`; transactional records use
  `XXX-.YY.-.##` (YY = 2-digit year).
- **Doctype names in ASCII** (e.g. `Ausencia`, `Justificacao De Faltas`); user-facing
  **labels and prose keep accents** (Ausência, Justificação).
- **Config lives in one singleton** (`Entre HR Settings`) so nothing is hard-coded.
- **Money documents are Employee-primary**: each links `funcionario` (Link Employee)
  plus a read-only `funcionario_nome` (fetch from `funcionario.employee_name`).
- **Approvals** use Frappe's **built-in Workflow** (configured by the operator, not shipped
  as a fixture); its approved state maps to submit (see Phase 9).

## Scope of this build (v1)

**Payroll + Férias MVP** = Phases 0–9, including the statutory components **INSS**,
**IRPS**, and **13º Salário** (Phase 7 — formulas supplied later). Out of scope for v1:
disciplinary process, custom dashboards, and any bespoke premium UI (build those in v2).

**Approval workflow is not shipped by this app.** The submittable documents are built to
be workflow-ready (submittable, with their effect on `on_submit`), but the approval flow
itself is configured directly in Frappe's **built-in Workflow** UI by the operator — we
do not ship a Workflow/Workflow State fixture.

---

## Phase 0 — Scaffold

> Create a new Frappe app named `entre_hr` (title "Entre HR"). In `hooks.py`:
> `app_title = "Entre HR"`, `required_apps = ["frappe", "erpnext", "hrms"]`,
> `after_install = "entre_hr.install.after_install"`,
> `after_migrate = "entre_hr.install.after_migrate"`, and `app_include_css` /
> `app_include_js` placeholders. Create:
> - a Roles fixture: `Aprovador RH`, `RH Manager` (System Manager is reused alongside);
> - a README documenting the naming-series convention (entities `XXX-.##`,
    >   transactional `XXX-.YY.-.##`) and the Employee-native principle;
> - a single doctype `Entre HR Settings` (see spec).
    > No business doctypes yet.

**Spec — `Entre HR Settings` (Single doctype) fields:**
- `salario_minimo_padrao` (Currency) — legal minimum-wage floor; blank/0 = no floor.
- `estrutura_salarial_padrao` (Link → Salary Structure) — the structure new assignments
  use.
- `payroll_payable_account` (Link → Account) — set on every Salary Structure Assignment.
- `leave_type_ferias` (Link → Leave Type, default "Ferias").
- `dias_maximos_ferias` (Int, default 60) — férias cap.
- `metodo_calculo_faltas` (Select: "Proporcional ao Salário" | "Valor Fixo por Falta").
- `valor_fixo_por_falta` (Currency, shown when method = fixed).
- `divisor_dias` (Select: "Dias do Mês" | "Dias Úteis", default "Dias do Mês").
- `componente_faltas` (Link → Salary Component, default "Faltas").
- `componente_proporcional` (Link → Salary Component, default "Proporcional").
- `componente_retroativo` (Link → Salary Component, default "Retroativo").
- `componente_emprestimo` (Link → Salary Component, default "Emprestimo").
- `componente_inss` (Link → Salary Component, default "INSS") — social-security deduction.
- `componente_irps` (Link → Salary Component, default "IRPS") — income-tax deduction.
- `componente_13o_salario` (Link → Salary Component, default "13o Salario") — Christmas /
  year-end bonus earning.
- Statutory parameters are **placeholders for now** (rates/brackets supplied later): keep
  their config in Settings too — e.g. `inss_taxa_trabalhador` (Percent),
  `irps_tabela` (child table of brackets), `activo_inss` / `activo_irps` /
  `activo_13o_salario` (Check) — but leave the concrete values/formulas `TBD`.
- Gates: `ferias_activo` (Check), `folha_activo` (Check).

**✅ Check:** `bench --site <site> install-app entre_hr` succeeds; `Entre HR Settings`
opens with all fields; the two roles exist.

---

## Phase 1 — Employee foundation

> Add custom fields to the HRMS `Employee` doctype (via `custom_fields` fixture) and
> establish the link-filter convention.

**Spec — custom fields on Employee:**
- `custom_salario_base_manual` (Currency) — per-employee base-salary override; blank =
  inherit the default/minimum.
- `custom_data_antiguidade_ferias` (Date) — anchor date for férias accrual; defaults to
  `date_of_joining`.
- `custom_ultima_acumulacao_ferias` (Date, read-only) — idempotency marker for the
  accrual scheduler.

**Spec — link filters:** every Link → Employee field we create in later phases carries
`link_filters` excluding terminated staff: `[["Employee","status","!=","Left"]]`.

**✅ Check:** the custom fields render on the Employee form.

---

## Phase 2 — Base salary via Salary Structure Assignment (SSA)

> Base pay lives in the HRMS **Salary Structure Assignment.base**. Build a resolver and
> an idempotent apply function, plus a form button to set an employee's salary.

**Spec — resolution (`resolver_salario_base(employee)`):**
1. If `Employee.custom_salario_base_manual` is set, use it.
2. Otherwise fall back to the current SSA base if any, else the minimum.
3. Floor the result at Settings `salario_minimo_padrao` when it is > 0
   (`base = max(base, minimo)`). If the floor is 0/blank, apply no floor.

**Spec — apply (`aplicar_salario_base(employee, silent=False)`):**
- Requires Settings `estrutura_salarial_padrao`.
- Creates or updates a **submitted** SSA for the employee with the resolved base and
  `payroll_payable_account` from Settings.
- **Idempotent:** no-op if the latest SSA base already matches. A changed base creates a
  new dated SSA that supersedes the old one.
- **`from_date`:** for the employee's **first** assignment, `from_date = date_of_joining`
  (clamped so it never precedes joining). Subsequent raises use `today()`.

**Spec — "Definir Salário" button** (Employee form, RH Manager / System Manager only):
prompts for a value (or "use minimum"), then calls apply. **Pay-cut guard:** compute the
prospective vs current resolved base *before* mutating; if the new value is lower and not
yet confirmed, return `{requires_confirm, atual, novo}` and write nothing, so the UI can
ask for confirmation and re-call with `confirmar_reducao=1`. Enforce this server-side.

**✅ Check:** setting a salary creates exactly one submitted SSA and is idempotent on
re-run; entering a lower value triggers the confirm before it writes.

---

## Phase 3 — Férias (annual-leave) accrual engine

> Own annual-leave accrual directly via **Leave Ledger Entries** (do not rely on the
> HRMS earned-leave automation, and do not trust `new_leaves_allocated` as the balance).

**Spec — policy:**
- Two tiers of service: **under 1 year = 1 day/month**; **≥ 1 year = 2.5 days/month**
  (30/year).
- Cap = Settings `dias_maximos_ferias` (default 60). Excess **expires on the admission
  anniversary**.
- Gated by Settings `ferias_activo`. Leave Type = Settings `leave_type_ferias`.

**Spec — mechanism (the important part):**
- Bookable balance = **SUM of Leave Ledger Entries**, so write an explicit Leave Ledger
  Entry for every accrual (+) and every expiry (−).
- Maintain a **single rolling Leave Allocation** per employee with
  `to_date = 2099-12-31` (a far horizon so HRMS auto-expiry never fires — this engine
  owns the cap), `is_carry_forward = 0`. Mirror the display fields on the allocation.

**Spec — cadence:**
- A **daily scheduler** accrues per-employee on their admission **day-of-month**, and
  trims excess at the anniversary.
- Anchor = `Employee.custom_data_antiguidade_ferias` (defaults to `date_of_joining`).
- Idempotency via `Employee.custom_ultima_acumulacao_ferias` (never double-accrue a
  month).

**Spec — one-time backfill:** a button on `Entre HR Settings` that seeds existing
employees' starting balance from tenure (theoretical accrued − already used, capped),
**create-only** (skips employees who already have an allocation; safe to re-run).
Enqueue it and report the result via realtime.

**✅ Check:** a manual accrual run produces the correct bookable balance computed as the
SUM of that employee's Leave Ledger Entries (not from `new_leaves_allocated`).

---

## Phase 4 — Absences (Ausência) + Justificação

> Faltas are recorded by a **custom monthly-entry doctype** — there is no shift schedule
> to derive them from.

**Spec — `Ausencia` doctype** (submittable, series `AUS-.YY.-.##`):
- `funcionario` (Link Employee) + `funcionario_nome` (read-only fetch).
- `mes` (Select: Janeiro…Dezembro) + `ano` (Int, JS-defaults current year).
- `n_de_faltas` (Int) — number of unjustified absence days that month.
- `observacoes` (Small Text, optional).
- **No-past-months validation:** the chosen month resolves to the **current year** if it
  is ≥ the current month; it may resolve to **next year only during the December→January
  wrap** (i.e. only when we are currently in December). Any earlier month in the current
  year is **rejected**. (Fires only for new records or when the month changes.)

**Spec — `Justificacao De Faltas` doctype** (submittable, Employee-keyed): records
justified days that offset absences for a month, matched to the employee.

**Spec — `entre_hr.utils.calcular_faltas(employee, start, end)`:** returns
`absence_days − justified_days`, where **both sides are matched on `employee`** (so they
can never desync), summed over the submitted Ausência / Justificação records overlapping
`[start, end]`.

**✅ Check:** an Ausência of 3 days minus a 1-day Justificação yields 2 from
`calcular_faltas` for that employee and period.

---

## Phase 5 — Payroll assembly skeleton

> Hook the Salary Slip to auto-assemble itself, keyed on the slip's `employee`.

**Spec — wire `doc_events` on "Salary Slip"** →
`entre_hr.payroll.salary_slip_hooks.{before_insert, before_validate, before_submit}`.
Gated by Settings `folha_activo`.

**Spec — on each slip (before_validate):**
1. Resolve base from the employee's latest **submitted SSA** and ensure it is on the
   slip.
2. Set the divisor from Settings `divisor_dias`: `custom_dias_de_trabalho` = days in the
   month ("Dias do Mês") or working days ("Dias Úteis").
3. Compute faltas via `calcular_faltas(employee, slip.start_date, slip.end_date)`; set
   `custom_dias_trabalhados = custom_dias_de_trabalho − faltas`.
4. Append the **faltas deduction** using Settings `componente_faltas`:
  - method "Proporcional ao Salário": `amount = base / custom_dias_de_trabalho × faltas`;
  - method "Valor Fixo por Falta": `amount = faltas × valor_fixo_por_falta`.
    If the configured component is missing, skip silently.

**✅ Check:** a fresh slip auto-fills the base and a correct faltas deduction.

---

## Phase 6 — Money doctypes (earnings & deductions add-ons)

> Four Employee-primary doctypes feed the slip. All carry `funcionario` +
> `funcionario_nome`. Wire each into `salary_slip_hooks`.

**Spec — `Outras Deducoes`** (submittable): a `tipo` field that is a **Link → Salary
Component** filtered to `type = Deduction`; `valor_mensal` (Currency); a start month/year
and a number of months, from which the controller derives `data_de_inicio` and
`data_de_fim` (`data_de_fim` = last day of the final month). Active + date-bounded rows
covering the slip period are summed into the slip's deductions, with the component read
**verbatim from `tipo`**. Apply the same no-past-months rule as Ausência.

**Spec — `Outras Remuneracoes`** (submittable): mirror of the above for earnings — a
`tipo_de_subsidios` field that **is** the Salary Component; approved + date-covering rows
add to the slip's earnings, **de-duplicated per component**.

**Spec — `Emprestimo`** (loans, submittable, series `EMP-.####`): active + date-covering;
sum of `valor_mensal` → the Settings `componente_emprestimo` deduction. Fetch the
employee's base from the latest SSA so any percentage-of-salary cap can be enforced.

**Spec — `Reclamacao De Salario`** (salary claim, submittable): a "Mês de Reclamação"
(month + year) reference resolves the **already-processed** Salary Slip for that month
and surfaces its gross and net; the claimed amount is added to the target slip's earnings
as `componente_retroativo`. If no processed slip is found, leave the reference fields
**blank (not 0)** and show a **non-blocking** warning (a claim for a genuinely unpaid
month is still valid).

**Spec — wiring:** add `_add_deducoes`, `_add_remuneracoes`, `_add_emprestimos`, and the
retroativo handler to `salary_slip_hooks`, each matched on the slip's `employee`.

**✅ Check:** an approved `Outras Deducoes` row appears on the next slip's deductions
under the right component.

---

## Phase 7 — Statutory contributions (INSS, IRPS, 13º Salário)

> Mozambican statutory payroll: social security (**INSS**), income tax (**IRPS**), and the
> year-end **13º Salário** bonus. **Formulas/rates/brackets are supplied later** — build
> the plumbing now with the actual math behind a single, replaceable calculation point.

**Spec — components:** use Settings `componente_inss`, `componente_irps`, and
`componente_13o_salario`. INSS and IRPS are **deductions**; 13º Salário is an **earning**.
Auto-create each as the right component type on first use if missing.

**Spec — wiring:** add `_add_inss`, `_add_irps`, and `_add_13o_salario` to
`salary_slip_hooks` (before_validate, keyed on the slip's `employee`), each gated by its
Settings flag (`activo_inss` / `activo_irps` / `activo_13o_salario`).

**Spec — ordering (matters for tax base):** the usual Mozambican order is INSS first
(reduces taxable income), then IRPS on the post-INSS base. Compute IRPS **after** INSS is
appended so the tax base already reflects it. Keep every formula in one pure helper per
tax (`entre_hr.payroll.statutory.calcular_inss(...)`, `calcular_irps(...)`,
`calcular_13o(...)`) so swapping in the real rates/brackets later touches **one function**,
not the hook wiring.

**Spec — placeholders until formulas land:** ship the helpers returning `0` (or reading a
flat rate from Settings) so the pipeline is exercisable end-to-end, and mark them
`# TODO: real INSS/IRPS/13º formula` — do not invent statutory numbers.

**✅ Check:** with the flags on, a slip shows INSS and IRPS deduction lines (and a 13º
Salário earning when applicable) under the configured components, with IRPS computed on
the post-INSS base; with the flags off, none appear.

---

## Phase 8 — Partial-month proration (join / leave)

> An employee who joins or leaves mid-month is paid only for the worked portion of the
> base (subsídios stay full). **We use ERPNext's built-in payment-days proration** — no
> custom proration deduction.

**Spec — mechanism:**
- Rely on ERPNext's default **payment-days** behavior to prorate the base for mid-month
  join/leave: the base salary component keeps its default `Depends on Payment Days`, and
  the slip's `payment_days` / `total_working_days` drive the fraction. **Do not** add a
  custom `_add_proporcional_admissao_demissao` deduction — that would double-prorate.
- `componente_proporcional` is therefore **not** used for join/leave proration; keep it in
  Settings only if another feature needs it, otherwise it can be dropped.
- Subsídios / earnings that must stay full for a mid-month employee should have their own
  component's `Depends on Payment Days` **off**, so only the base is affected.

**✅ Check:** a mid-month joiner's slip prorates the base via payment days (base only,
subsídios full); a full-month employee's slip is unaffected.

---

## Phase 9 — Approval (built-in Workflow)

> Submittable documents are approved through Frappe's **built-in Workflow**, configured in
> the UI by the operator. This app does **not** ship a Workflow fixture.

**Spec — app side:** ensure `Ausencia`, `Justificacao De Faltas`, `Outras Deducoes`,
`Outras Remuneracoes`, `Emprestimo`, and `Reclamacao De Salario` are **submittable**, and
that each document's effect runs in its `on_submit` handler. The intended contract is that
the workflow's approved state maps to **docstatus 1 (submit)**, which fires `on_submit`.
No custom Workflow/Workflow State fixtures, no bespoke workflow-detection JS — the standard
`workflow_state` field and Frappe's built-in workflow engine handle the UI.

**Spec — operator side (documented, not coded):** in Workflow, create a flow per doctype
(suggested states `Rascunho` → `Pendente De Aprovação` → `Aprovado`, plus `Rejeitado` /
`Cancelado`) with the `Aprovado` state set to **docstatus 1**, restricted to the
`Aprovador RH` / `RH Manager` roles.

**✅ Check:** a submittable money document, once submitted (via the built-in workflow's
approved state or directly), fires its `on_submit` effect so it shows on the slip.

---

## Deploy (after each phase)

`bench --site <site> migrate` + `bench build --app entre_hr` + `bench restart`. Any
auto-created Salary Component (e.g. "Proporcional") is created on first use.

## v2 candidates (out of scope now)

- Disciplinary process (misconduct report → disciplinary case → auto-deduction).
- Rehire / seniority-reset rules (decide the Mozambican-labour treatment first).
- Custom RH dashboard and a premium form UI/design system.
