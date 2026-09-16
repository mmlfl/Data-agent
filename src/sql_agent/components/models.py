"""Typed rich UI components streamed to capable clients.

Tools keep ``result_for_llm`` concise while these models carry the richer,
user-facing representation.  The ``type`` field is a stable discriminator for
frontend renderers.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field


ColumnDataType = Literal["number", "datetime", "boolean", "string", "unknown"]
ChartType = Literal["bar", "line", "area", "pie", "scatter", "none"]
ChartAggregation = Literal["none", "sum", "avg", "min", "max", "count"]


class DataColumn(BaseModel):
    name: str
    data_type: ColumnDataType = "unknown"


class DataFrameComponent(BaseModel):
    type: Literal["dataframe"] = "dataframe"
    title: str = "查询结果"
    columns: list[DataColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    row_count_is_exact: bool = True
    displayed_row_count: int = 0
    truncated: bool = False
    sql: str


class TableInfo(BaseModel):
    table_name: str
    schema_name: Optional[str] = None
    table_comment: Optional[str] = None


class TableListComponent(BaseModel):
    type: Literal["table_list"] = "table_list"
    title: str = "候选数据表"
    keyword: str
    tables: list[TableInfo] = Field(default_factory=list)


class SchemaColumn(BaseModel):
    column_name: str
    data_type: Optional[str] = None
    is_nullable: Optional[str] = None
    data_length: Optional[int] = None
    column_comment: Optional[str] = None


class TableSchemaComponent(BaseModel):
    type: Literal["table_schema"] = "table_schema"
    title: str = "表结构"
    table_name: str
    columns: list[SchemaColumn] = Field(default_factory=list)


class ChartSpec(BaseModel):
    type: ChartType = "none"
    title: Optional[str] = None
    x_field: Optional[str] = None
    y_fields: list[str] = Field(default_factory=list)
    series_field: Optional[str] = None
    aggregation: ChartAggregation = "none"
    reason: Optional[str] = None


class FinalResultComponent(BaseModel):
    type: Literal["final_result"] = "final_result"
    source_tool_call_id: str
    title: str
    summary: str
    insights: list[str] = Field(default_factory=list)
    chart: ChartSpec = Field(default_factory=ChartSpec)
    warnings: list[str] = Field(default_factory=list)


UiComponent = Annotated[
    Union[
        DataFrameComponent,
        TableListComponent,
        TableSchemaComponent,
        FinalResultComponent,
    ],
    Field(discriminator="type"),
]
