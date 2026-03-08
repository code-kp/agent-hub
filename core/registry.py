"""
Tests:
- tests/core/test_registry.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type, TypeVar


T = TypeVar("T")


class Register:
    """Global typed registry for runtime lookups."""

    _items: Dict[Type[Any], Dict[str, Any]] = {}

    @classmethod
    def register(
        cls, item_type: Type[T], name: str, item: T, overwrite: bool = True
    ) -> T:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Registry name must be non-empty.")

        bucket = cls._items.setdefault(item_type, {})
        if not overwrite and normalized_name in bucket:
            raise KeyError(
                "Registry entry already exists for type={type_name} name={name}".format(
                    type_name=item_type.__name__,
                    name=normalized_name,
                )
            )
        bucket[normalized_name] = item
        return item

    @classmethod
    def get(cls, item_type: Type[T], name: str) -> T:
        normalized_name = name.strip()
        bucket = cls._items.get(item_type, {})
        if normalized_name not in bucket:
            raise KeyError(
                "Registry entry not found for type={type_name} name={name}".format(
                    type_name=item_type.__name__,
                    name=normalized_name,
                )
            )
        return bucket[normalized_name]

    @classmethod
    def maybe_get(cls, item_type: Type[T], name: str) -> Optional[T]:
        bucket = cls._items.get(item_type, {})
        return bucket.get(name.strip())

    @classmethod
    def items(cls, item_type: Type[T]) -> Dict[str, T]:
        bucket = cls._items.get(item_type, {})
        return dict(bucket)

    @classmethod
    def values(cls, item_type: Type[T]) -> List[T]:
        return list(cls._items.get(item_type, {}).values())

    @classmethod
    def clear(cls, item_type: Optional[Type[Any]] = None) -> None:
        if item_type is None:
            cls._items.clear()
            return
        cls._items.pop(item_type, None)
