"""Base model definitions compatible with standard dataclass serialization."""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict
import json


def Field(
    default: Any = ...,
    *,
    default_factory: Any = None,
    description: str = "",
    ge: Any = None,
    le: Any = None,
    gt: Any = None,
    lt: Any = None,
    **kwargs: Any,
) -> Any:
    """Field helper for dataclass model definitions."""
    meta = {"description": description, "ge": ge, "le": le, "gt": gt, "lt": lt, **kwargs}
    if default_factory is not None:
        return field(default_factory=default_factory, metadata=meta)
    elif default is not ...:
        return field(default=default, metadata=meta)
    return field(metadata=meta)


class BaseModel:
    """Base class for all models providing dict(), model_dump(), and json() methods."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        dataclass(cls)

    def dict(self) -> Dict[str, Any]:
        return asdict(self)

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)

    def json(self) -> str:
        return json.dumps(self.model_dump(), default=str)
