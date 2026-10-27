const TOOL_LABELS: Record<string, string> = {
  search_schema: "召回相关表结构",
  search_sql_memory: "查找已确认的 SQL",
  find_join_path: "查找表间连接路径",
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
