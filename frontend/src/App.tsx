import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { fetchHealth } from "./api/chat";
import { AnalysisHome } from "./components/AnalysisHome";
import { ConversationPane } from "./components/ConversationPane";
import { Header } from "./components/Header";
import { Icon } from "./components/Icon";
import { Sidebar } from "./components/Sidebar";
import { ResultPane } from "./components/results/ResultPane";
import { useChat } from "./hooks/useChat";
import { useMetadataSync } from "./hooks/useMetadataSync";
import { useTheme } from "./hooks/useTheme";
import type { HealthResponse, ResultArtifact } from "./types";
const MetadataManager = lazy(() => import("./components/MetadataManager").then(module => ({ default: module.MetadataManager })));

export default function App() {
  const [page, setPage] = useState<"analysis" | "metadata">("analysis");
  const [metadataOpened, setMetadataOpened] = useState(false);
  const [mobileView, setMobileView] = useState<"conversation" | "results">(
    "conversation",
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const healthRequest = useRef<Promise<HealthResponse> | null>(null);
  const contentRef = useRef<HTMLElement>(null);
  const [initialId] = useState(() => crypto.randomUUID());
  const { theme, toggleTheme } = useTheme();
  const chat = useChat(initialId);

  const refreshHealth = useCallback(() => {
    if (healthRequest.current) return healthRequest.current;
    setChecking(true);
    const request = fetchHealth()
      .then((data) => {
        setHealth(data);
        setHealthError(null);
        return data;
      })
      .catch((error: unknown) => {
        setHealthError("暂时无法连接分析服务，请确认服务已启动后重新连接。");
        throw error;
      })
      .finally(() => {
        setChecking(false);
        healthRequest.current = null;
      });
    healthRequest.current = request;
    return request;
  }, []);
  const metadata = useMetadataSync(refreshHealth);

  useEffect(() => {
    void refreshHealth().catch(() => {});
  }, [refreshHealth]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSidebarOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  const navigate = (next: "analysis" | "metadata") => {
    if (next === "metadata") setMetadataOpened(true);
    setPage(next);
    setSidebarOpen(false);
  };
  const openResult = (id: string) => {
    chat.setActiveResult(id);
    setMobileView("results");
  };
  const artifacts = chat.resultOrder
    .map((id) => chat.results[id])
    .filter((artifact): artifact is ResultArtifact => Boolean(artifact));
  const hasMessages = chat.messages.length > 0;

  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [page, chat.conversationId, hasMessages]);

  return (
    <div
      className={`workspace-shell${sidebarCollapsed ? " workspace-shell--compact" : ""}`}
    >
      <Sidebar
        page={page}
        open={sidebarOpen}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        busy={chat.loading}
        health={healthError ? null : health}
        conversations={chat.conversations}
        activeId={chat.conversationId}
        onNavigate={navigate}
        onNew={() => {
          chat.switchConversation();
          setMobileView("conversation");
          navigate("analysis");
        }}
        onOpen={(id) => {
          chat.switchConversation(id);
          setMobileView("conversation");
          navigate("analysis");
        }}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="workspace-main">
        <Header
          page={page}
          health={health}
          healthError={healthError}
          checking={checking}
          menuOpen={sidebarOpen}
          theme={theme}
          onToggleTheme={toggleTheme}
          onRefresh={() => void refreshHealth().catch(() => {})}
          onMenu={() => setSidebarOpen(true)}
        />
        {healthError && (
          <div className="service-banner" role="status">
            <Icon name="alert" size={15} />
            <span>{healthError}</span>
            <button
              type="button"
              onClick={() => void refreshHealth().catch(() => {})}
              disabled={checking}
            >
              {checking ? "连接中…" : "重新连接"}
              <Icon name="refresh" size={13} />
            </button>
          </div>
        )}
        <main
          ref={contentRef}
          className={`workspace-content ${page === "analysis" && hasMessages ? "workspace-content--chat" : ""}`}
        >
          <div className="analysis-page" hidden={page !== "analysis"}>
            {!hasMessages ? (
              <AnalysisHome
                health={healthError ? null : health}
                input={chat.input}
                onInputChange={chat.setInput}
                onSend={() => void chat.send()}
                onMetadata={() => navigate("metadata")}
              />
            ) : (
              <>
                <div className="analysis-title">
                  <div>
                    <span className="page-eyebrow">ANALYSIS WORKSPACE</span>
                    <h1 title={chat.messages[0]?.content}>
                      {chat.messages[0]?.content}
                    </h1>
                  </div>
                  <span
                    className={`analysis-status ${chat.loading ? "analysis-status--running" : ""}`}
                  >
                    <span className="status-dot" />
                    {chat.loading ? "分析进行中" : "本次分析"}
                  </span>
                </div>
                <div
                  className="mobile-view-switch"
                  role="group"
                  aria-label="工作台视图"
                >
                  <button
                    type="button"
                    aria-pressed={mobileView === "conversation"}
                    onClick={() => setMobileView("conversation")}
                  >
                    <Icon name="message" size={15} />
                    分析对话
                  </button>
                  <button
                    type="button"
                    aria-pressed={mobileView === "results"}
                    onClick={() => setMobileView("results")}
                  >
                    <Icon name="chart" size={15} />
                    查询结果
                    {artifacts.length > 0 && <span>{artifacts.length}</span>}
                  </button>
                </div>
                <div className={`analysis-grid analysis-grid--${mobileView}`}>
                  <ConversationPane
                    key={chat.conversationId}
                    messages={chat.messages}
                    toolCalls={chat.toolCalls}
                    input={chat.input}
                    loading={chat.loading}
                    disabled={false}
                    contextTokens={chat.contextTokens}
                    contextWindowTokens={chat.contextWindowTokens}
                    contextNotice={chat.contextNotice}
                    onInputChange={chat.setInput}
                    onSend={(prompt) => void chat.send(prompt)}
                    onCancel={chat.cancel}
                    onOpenResult={openResult}
                  />
                  <ResultPane
                    artifacts={artifacts}
                    activeResultId={chat.activeResultId}
                    phase={chat.phase}
                    onSelectResult={chat.setActiveResult}
                  />
                </div>
              </>
            )}
          </div>
          <div hidden={page !== "metadata"}>
            {metadataOpened && <Suspense fallback={<p>正在加载元数据管理…</p>}><MetadataManager
              active={page === "metadata"}
              health={health}
              healthError={healthError}
              executions={metadata.executions}
              activeTarget={metadata.activeTarget}
              onSync={(target) => void metadata.sync(target)}
            /></Suspense>}
          </div>
        </main>
        <footer className="workspace-footer">
          <span>
            DATA AGENT <span className="footer-version">v0.1.0</span>
            <span className="footer-dot">|</span>用数据连接问题与答案
          </span>
          <span>
            <Icon name="shield" size={13} />
            基于真实查询结果
            <span
              className={`footer-service ${health && !healthError ? "footer-service--online" : ""}`}
            >
              <span className="status-dot" />
              {health && !healthError ? "服务在线" : "服务未连接"}
            </span>
          </span>
        </footer>
      </div>
    </div>
  );
}
