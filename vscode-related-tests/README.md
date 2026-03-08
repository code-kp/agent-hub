# Related Tests Controller

This VS Code extension adds a second Testing controller named `Related Tests`.

It discovers Python source files that declare a top-level module docstring like:

```python
"""
Tests:
- tests/core/test_guardrails.py
- tests/core/contracts/test_execution.py
"""
```

The controller follows the active Python file in the editor. When the active file declares related tests, the tree shows only that module and the related `tests/...py` files declared in it.

Profiles:
- `Run`
  - executes the related files through `python -m pytest`
- `Debug`
  - launches `pytest` under the Python debugger
- `Coverage`
  - runs the related files through `coverage.py` and publishes file coverage back into VS Code

Coverage note:
- the selected interpreter must have `coverage` installed
- if `coverage.py` is missing, the coverage profile will fail with a startup/error message

The extension ships its own Python metadata helper under `python/related_tests_metadata.py`, so the editor-specific logic stays out of the runtime framework.

Switch editors to change the displayed module. Use `Refresh Related Tests` on the source item if you want to reload the active file after editing its metadata.

Install from this workspace with:

```bash
uv run poe install-related-tests-extension
```
