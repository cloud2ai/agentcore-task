# Ray Review Python — agentcore-task

**Base commit:** 27c6318  
**Scope:** Hand-written Python under `agentcore_task/` and `tests/` (excl. migrations).

---

## Findings (by severity)

### Fixed in this pass

1. **tests/test_unit_services.py:19** — Line length > 79.  
   Import `from ... import task_config as task_config_svc` exceeded 79 chars.  
   **Fix:** Wrapped in parentheses and broke after `task_config_svc`.

2. **agentcore_task/adapters/django/services/task_config.py** — Logging with variables used `%s` style.  
   Ray: use f-strings for logging with variables.  
   **Fix:** Replaced `logger.warning("...%s...%s", key, e)` and `logger.debug("...%s...%s", key, e)` with f-strings.

3. **agentcore_task/adapters/django/services/timeout.py** — Stdlib import order.  
   Ray: imports grouped stdlib / third-party / local, alphabetized.  
   **Fix:** Reordered to `from datetime`, `import logging`, `from typing`.

4. **agentcore_task/adapters/django/cleanup.py** — Same stdlib import order.  
   **Fix:** Reordered to `from datetime`, `import logging`, `from typing`.

### No further issues found

- **Line length:** No other hand-written file has lines > 79 (migrations excluded).
- **Docstrings:** Public modules, classes, and functions have triple-quoted docstrings.
- **Comments:** In English and placed above code (e.g. task_tracker, task_stats, cleanup).
- **NOTE(Ray):** Used correctly in `conf.py` for lazy imports.
- **Logging:** task_tracker, lock, timeout, cleanup use f-strings; task_config now aligned.

---

## Open questions / assumptions

- `get_queryset` and other viewset overrides in `views/task.py` have no docstrings; treated as overrides where the parent contract is sufficient.
- `conf.py` mid-file imports are documented as NOTE(Ray) exception; no change.

---

## Summary

- **Addressed:** 1 line-length violation, 1 logging-format requirement, 2 import-order adjustments.
- **Residual risk:** None identified for the reviewed scope.
- **Testing:** Existing unit tests remain sufficient; no new tests added for style-only changes.
