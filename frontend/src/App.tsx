import { useEffect, useRef, useState } from "react";
import { fetchHealth } from "./api/chat";
import { ChatMessage } from "./components/ChatMessage";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { Header } from "./components/Header";
import { useChat } from "./hooks/useChat";
import type { HealthResponse } from "./types";

function uid() {
  return crypto.randomUUID();
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [conversationId] = useState(() => uid());
  const bottomRef = useRef<HTMLDivElement>(null);

  const { messages, input, setInput, loading, send, cancel } = useChat(conversationId);

  useEffect(() => {
    fetchHealth()
      .then((data) => {
        setHealth(data);
        setHealthError(null);
      })
      .catch(() => {
        setHealthError("unreachable");
      });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant")?.id;

  return (
    <div className="layout">
      <Header health={health} healthError={healthError} />

      <main className="chat">
        {messages.length === 0 && (
          <EmptyState onSend={(p) => void send(p)} disabled={loading || !!healthError} />
        )}
        {messages.map((m) => (
          <ChatMessage
            key={m.id}
            message={m}
            isStreaming={loading && m.id === lastAssistantId}
          />
        ))}
        <div ref={bottomRef} />
      </main>

      <Composer
        input={input}
        loading={loading}
        onInputChange={setInput}
        onSend={() => void send()}
        onCancel={cancel}
      />
    </div>
  );
}
