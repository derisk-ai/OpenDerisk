from typing import Any, List, Optional

from derisk._private.pydantic import BaseModel


class DataNode(BaseModel):
    title: Optional[str]
    key: Optional[str]

    type: Optional[str] = ""
    default_value: Optional[Any] = None
    can_null: Optional[str] = "YES"
    comment: Optional[str] = None
    children: Optional[List] = []


class SqlRunData(BaseModel):
    result_info: Optional[str]
    run_cost: float
    colunms: Optional[List[str]] = []
    values: Optional[List] = []

