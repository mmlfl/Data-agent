import type { ToolCallRecord } from "../types";

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}

export function ToolDetail({ call }: { call: ToolCallRecord }) {
  const component = call.component;

  if (call.status === "error") {
    return (
      <div className="tool-detail tool-detail--error" role="alert">
        <strong>执行未完成</strong>
        <span>{call.error || call.content || "工具返回了未知错误"}</span>
        {typeof call.arguments?.sql === "string" && (
          <pre>{call.arguments.sql}</pre>
        )}
      </div>
    );
  }

  if (!component) {
    const args = call.arguments ?? {};
    if (typeof args.sql === "string") {
      return (
        <div className="tool-detail">
          <div className="tool-detail__label">准备执行的 SQL</div>
          <pre>{args.sql}</pre>
        </div>
      );
    }
    return (
      <div className="tool-detail">
        <div className="tool-detail__label">
          {call.status === "running" ? "正在处理" : "调用参数"}
        </div>
        <pre>{displayValue(args)}</pre>
      </div>
    );
  }

  if (component.type === "table_list") {
    return (
      <div className="tool-detail">
        <div className="tool-detail__label">
          关键词“{component.keyword}”命中 {component.tables.length} 张表
        </div>
        {component.tables.length === 0 ? (
          <p className="tool-detail__empty">没有找到匹配的数据表。</p>
        ) : (
          <ul className="tool-detail__tables">
            {component.tables.map((table) => (
              <li key={`${table.schema_name ?? ""}.${table.table_name}`}>
                <code>{table.table_name}</code>
                {table.table_comment && <span>{table.table_comment}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  if (component.type === "table_schema") {
    return (
      <div className="tool-detail">
        <div className="tool-detail__label">
          <code>{component.table_name}</code> · {component.columns.length} 个字段
        </div>
        <div className="tool-detail__schema-wrap">
          <table className="tool-detail__schema">
            <thead>
              <tr>
                <th>字段</th>
                <th>类型</th>
                <th>可空</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {component.columns.map((column) => (
                <tr key={column.column_name}>
                  <td><code>{column.column_name}</code></td>
                  <td>{column.data_type || "—"}</td>
                  <td>{column.is_nullable || "—"}</td>
                  <td>{column.column_comment || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (component.type === "dataframe") {
    return (
      <div className="tool-detail tool-detail--result">
        <div>
          <strong>{component.row_count}</strong> 行结果
          <span> · {component.columns.length} 个字段</span>
        </div>
        <span>完整结果已固定到右侧洞察画布。</span>
        <details>
          <summary>查看 SQL</summary>
          <pre>{component.sql}</pre>
        </details>
      </div>
    );
  }

  return (
    <div className="tool-detail tool-detail--result">
      <strong>{component.title}</strong>
      <span>{component.summary}</span>
    </div>
  );
}
