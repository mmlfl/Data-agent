type Segment = { type: "text" | "sql"; value: string };

const SQL_LINE =
  /^(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|WITH|SHOW|DESC|DESCRIBE|EXPLAIN)\b/i;

function isSqlBlock(text: string): boolean {
  const lines = text.trim().split("\n");
  return lines.some((line) => SQL_LINE.test(line.trim()));
}

function splitByFences(content: string): Segment[] {
  const segments: Segment[] = [];
  const fenceRegex = /```(?:sql)?\s*\n?([\s\S]*?)```/gi;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = fenceRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: content.slice(lastIndex, match.index) });
    }
    segments.push({ type: "sql", value: match[1].trim() });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    segments.push({ type: "text", value: content.slice(lastIndex) });
  }

  return segments.length > 0 ? segments : [{ type: "text", value: content }];
}

function splitSqlLines(text: string): Segment[] {
  const lines = text.split("\n");
  const segments: Segment[] = [];
  let buffer: string[] = [];

  const flush = (type: "text" | "sql") => {
    if (buffer.length === 0) return;
    segments.push({ type, value: buffer.join("\n") });
    buffer = [];
  };

  for (const line of lines) {
    if (SQL_LINE.test(line.trim())) {
      flush("text");
      buffer.push(line);
    } else if (buffer.length > 0 && line.trim() === "") {
      buffer.push(line);
    } else if (buffer.length > 0 && /^\s{2,}|\t/.test(line)) {
      buffer.push(line);
    } else {
      flush("sql");
      buffer.push(line);
    }
  }
  flush(buffer.length > 0 && isSqlBlock(buffer.join("\n")) ? "sql" : "text");

  return segments.length > 0 ? segments : [{ type: "text", value: text }];
}

export function parseMessageContent(content: string): Segment[] {
  const fenced = splitByFences(content);
  const result: Segment[] = [];

  for (const seg of fenced) {
    if (seg.type === "sql") {
      result.push(seg);
    } else if (isSqlBlock(seg.value)) {
      result.push(...splitSqlLines(seg.value));
    } else {
      result.push(seg);
    }
  }

  return result;
}

interface MessageContentProps {
  content: string;
}

export function MessageContent({ content }: MessageContentProps) {
  const segments = parseMessageContent(content);

  return (
    <div className="bubble__content">
      {segments.map((seg, i) =>
        seg.type === "sql" ? (
          <pre key={i} className="bubble__sql">
            {seg.value}
          </pre>
        ) : (
          <span key={i} className="bubble__text">
            {seg.value}
          </span>
        ),
      )}
    </div>
  );
}
