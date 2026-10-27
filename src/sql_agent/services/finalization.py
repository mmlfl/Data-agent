"""Result selection/sampling contract, separate from the Agent iteration loop."""
import uuid
from sql_agent.core.tool import ToolCall


def systematic_sample(rows, max_rows):
    if max_rows <= 0 or not rows:
        return []
    if len(rows) <= max_rows:
        return rows
    if max_rows == 1:
        return [rows[0]]
    return [rows[index] for index in sorted({round(index * (len(rows)-1) / (max_rows-1)) for index in range(max_rows)})]


def finalization_call(config, source_id, dataframe, question, draft, *, tool_limit=False, time_limit=False):
    return ToolCall(id='finalize_' + uuid.uuid4().hex[:12], name=config.finalizer_tool_name,
        arguments={'question': question, 'source_tool_call_id': source_id, 'sql': dataframe.sql,
                   'columns': [column.model_dump(mode='json') for column in dataframe.columns],
                   'rows': systematic_sample(dataframe.rows, config.max_finalize_rows),
                   'row_count': dataframe.row_count, 'row_count_is_exact': dataframe.row_count_is_exact,
                   'truncated': dataframe.truncated, 'sample_strategy': 'systematic', 'draft': draft,
                   'partial': tool_limit or time_limit, 'partial_reason': 'time_budget' if time_limit else 'tool_limit'})
