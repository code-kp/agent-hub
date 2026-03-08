import unittest

from core.contracts.memory import (
    DEFAULT_MEMORY_CONFIG,
    MemoryConfig,
    ensure_memory_config,
)


class MemoryContractsTest(unittest.TestCase):
    def test_ensure_memory_config_returns_default_when_missing(self) -> None:
        self.assertIs(ensure_memory_config(None), DEFAULT_MEMORY_CONFIG)

    def test_memory_config_rejects_non_positive_limits(self) -> None:
        with self.assertRaises(ValueError):
            MemoryConfig(preserve_recent_turns=0)

    def test_ensure_memory_config_requires_memory_config_instance(self) -> None:
        with self.assertRaises(TypeError):
            ensure_memory_config("invalid")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
