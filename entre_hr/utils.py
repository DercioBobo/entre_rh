"""Shared helpers and conventions for Entre HR."""

# Link-filter convention: every Link -> Employee field created by this app carries
# this filter so terminated staff never appear in pickers (see BUILD_PLAN Phase 1).
EMPLOYEE_LINK_FILTERS = '[["Employee","status","!=","Left"]]'
