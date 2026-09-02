import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MessageContentProps {
  content: string;
}

export function MessageContent({ content }: MessageContentProps) {
  return (
    <div className="message-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer" />
          ),
          pre: ({ node: _node, ...props }) => (
            <pre {...props} className="message-markdown__pre" />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
