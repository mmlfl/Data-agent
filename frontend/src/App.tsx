import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHealth, syncCache } from "./api/chat";
import { ConversationPane } from "./components/ConversationPane";
import { Header } from "./components/Header";
import { ResultPane } from "./components/results/ResultPane";
import { useChat } from "./hooks/useChat";
import { useTheme } from "./hooks/useTheme";
import type { HealthResponse, ResultArtifact } from "./types";

function uid() {
  return crypto.randomUUID();
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [conversationId] = useState(() => uid());
  const syncMsgTimer = useRef<number | null>(null);

  const { theme, toggleTheme } = useTheme();
  const {
    messages,
    toolCalls,
    results,
    resultOrder,
    activeResultId,
    phase,
    input,
    setInput,
    loading,
    send,
    cancel,
    setActiveResult,
  } = useChat(conversationId);

  const refreshHealth = useCallback(async () => {
    const data = await fetchHealth();
    setHealth(data);
    setHealthError(null);
    return data;
  }, []);

  useEffect(() => {
    refreshHealth().catch(() => {
      setHealthError("unreachable");
    });
  }, [refreshHealth]);

  useEffect(() => {
    return () => {
      if (syncMsgTimer.current != null) window.clearTimeout(syncMsgTimer.current);
    };
  }, []);

  const showSyncMessage = (msg: string) => {
    setSyncMessage(msg);
    if (syncMsgTimer.current != null) window.clearTimeout(syncMsgTimer.current);
    syncMsgTimer.current = window.setTimeout(() => setSyncMessage(null), 4000);
  };

  const handleSyncCache = async () => {
    setSyncing(true);
    try {
      const result = await syncCache();
      showSyncMessage(result.message || `已同步 ${result.table_count} 张表`);
      await refreshHealth();
    } catch (e) {
      showSyncMessage(e instanceof Error ? e.message : "同步失败");
    } finally {
      setSyncing(false);
    }
  };

  const artifacts = resultOrder
    .map((id) => results[id])
    .filter((artifact): artifact is ResultArtifact => Boolean(artifact));

  return (
    <div className="app-shell">
      <Header
        health={health}
        healthError={healthError}
        theme={theme}
        onToggleTheme={toggleTheme}
        syncing={syncing}
        syncMessage={syncMessage}
        onSyncCache={() => void handleSyncCache()}
      />

      <main className="workbench">
        <ConversationPane
          messages={messages}
          toolCalls={toolCalls}
          input={input}
          loading={loading}
          disabled={Boolean(healthError)}
          onInputChange={setInput}
          onSend={(prompt) => void send(prompt)}
          onCancel={cancel}
          onOpenResult={setActiveResult}
        />
        <ResultPane
          artifacts={artifacts}
          activeResultId={activeResultId}
          phase={phase}
          onSelectResult={setActiveResult}
        />
      </main>
    </div>
  );
}
