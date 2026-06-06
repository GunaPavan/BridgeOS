"""Shared schema primitives."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Paginated response envelope."""

    items: list[T]
    total: int = Field(description="Total items matching the query")
    skip: int = Field(description="Offset applied to the query")
    limit: int = Field(description="Page size")
