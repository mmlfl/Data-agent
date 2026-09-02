const TOOL_LABELS: Record<string, string> = {
  list_tables: "列出数据表",
  describe_table: "查看表结构",
  run_sql: "执行查询",
};

export function getToolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name;
}

export function formatToolList(tools: string[]): string {
  return tools.map(getToolLabel).join("、");
}
