const TOOL_LABELS: Record<string, string> = {
  list_tables: "定位数据表",
  describe_table: "核对字段结构",
  run_sql: "执行只读查询",
  finalize_result: "生成分析结论",
};

export function getToolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name;
}

export function formatToolList(tools: string[]): string {
  return tools.map(getToolLabel).join("、");
}
