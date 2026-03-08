import unittest

from core.contracts.execution import (
    DEFAULT_EXECUTION_CONFIG,
    ExecutionConfig,
    ensure_execution_config,
)


class ExecutionContractsTest(unittest.TestCase):
    def test_ensure_execution_config_returns_default_when_missing(self) -> None:
        self.assertIs(ensure_execution_config(None), DEFAULT_EXECUTION_CONFIG)

    def test_execution_config_rejects_non_positive_limits(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionConfig(max_tool_calls=0)

    def test_ensure_execution_config_requires_execution_config_instance(self) -> None:
        with self.assertRaises(TypeError):
            ensure_execution_config("invalid")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
