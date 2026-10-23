import { useEffect, useRef } from "react";
import type { HealthResponse } from "../types";
import { Composer } from "./Composer";
import { Icon, type IconName } from "./Icon";
import { BrandMark } from "./BrandMark";
import { HeroArtwork } from "./HeroArtwork";
import { HomePromptTools } from "./HomePromptTools";

const PROMPTS: {
  icon: IconName;
  label: string;
  description: string;
  prompt: string;
  color: string;
}[] = [
  {
    icon: "database",
    label: "探索数据结构",
    description: "了解有哪些表，以及它们的用途",
    prompt: "请列出数据库中的表，并根据表名和注释简要介绍它们的用途。",
    color: "green",
  },
  {
    icon: "chart",
    label: "发现业务趋势",
    description: "从时间维度，找到变化的线索",
    prompt:
      "请先查找适合做时间趋势分析的表和日期字段，向我建议几个可以分析的业务指标。",
    color: "purple",
  },
  {
    icon: "search",
    label: "查看字段详情",
    description: "核对字段、类型与业务含义",
    prompt: "请查找数据库中与用户相关的表，展示它们的字段、类型和注释。",
    color: "blue",
  },
  {
    icon: "layers",
    label: "梳理表间关系",
    description: "理解数据如何关联，探索分析路径",
    prompt:
      "请根据表结构中的主键、外键和字段注释，梳理可以确认的表间关系；不确定的关系请明确标注。",
    color: "amber",
  },
];

export function AnalysisHome({
  health,
  input,
  onInputChange,
  onSend,
  onMetadata,
}: {
  health: HealthResponse | null;
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onMetadata: () => void;
}) {
  const examplesRef = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      const examples = examplesRef.current;
      if (examples?.open && !examples.contains(event.target as Node)) {
        examples.open = false;
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      const examples = examplesRef.current;
      if (event.key === "Escape" && examples?.open) {
        examples.open = false;
        examples.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);
  const choosePrompt = (prompt: string) => {
    if (examplesRef.current) examplesRef.current.open = false;
    onInputChange(prompt);
    requestAnimationFrame(() =>
      document
        .querySelector<HTMLTextAreaElement>(".analysis-home textarea")
        ?.focus(),
    );
  };
  return (
    <div className="analysis-home">
      <div className="home-intro">
        <HeroArtwork />
        <span className="home-eyebrow">
          <span />
          DATA AGENT / 你的智能数据助手
        </span>
        <h1>
          让每个问题，<span>都有数据回答。</span>
        </h1>
        <p>
          用自然语言探索数据库，连接问题、SQL 与数据洞察，
          <br className="hero-copy-break" />
          让数据分析像对话一样简单。
        </p>
      </div>
      <div className="home-composer">
        <div className="home-composer__label">
          <BrandMark size={18} />向 Data Agent 提问
          <details className="home-examples" ref={examplesRef}>
            <summary>
              <Icon name="book" size={16} />
              参考示例
              <Icon name="chevron" size={12} className="turn-down" />
            </summary>
            <div className="home-examples__menu">
              {PROMPTS.map((item) => (
                <button
                  type="button"
                  key={item.label}
                  aria-label={`${item.label}：${item.description}`}
                  onClick={() => choosePrompt(item.prompt)}
                >
                  <Icon name={item.icon} size={16} />
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.description}</small>
                  </span>
                  <Icon name="arrow" size={13} />
                </button>
              ))}
            </div>
          </details>
        </div>
        <Composer
          input={input}
          loading={false}
          onInputChange={onInputChange}
          onSend={onSend}
          onCancel={() => {}}
          variant="home"
          toolbarContent={
            <HomePromptTools
              health={health}
              onMetadata={onMetadata}
              onAddTable={(table) =>
                choosePrompt(
                  `请基于表「${table}」分析：${input ? `\n${input}` : ""}`,
                )
              }
              onExample={() => choosePrompt(PROMPTS[0].prompt)}
            />
          }
        />
      </div>
      <div className="home-suggestions">
        <div className="section-caption">
          <span>常用分析方向</span>
          <small>从一个好问题开始</small>
        </div>
        <div className="prompt-grid">
          {PROMPTS.map((item) => (
            <button
              type="button"
              className="prompt-card"
              key={item.label}
              onClick={() => choosePrompt(item.prompt)}
            >
              <span className={`prompt-card__icon tone-${item.color}`}>
                <Icon name={item.icon} size={19} />
              </span>
              <span className="prompt-card__copy">
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </span>
              <Icon name="arrow" size={16} />
            </button>
          ))}
        </div>
      </div>
      <div className="home-source">
        <div className="home-source__mark">
          <Icon name="chart" size={22} />
        </div>
        <div className="home-source__description">
          <strong>分析能力与数据状态</strong>
          <span>连接服务后，自动读取当前状态，让分析有据可依。</span>
        </div>
        <dl className="home-source__stats">
          <div>
            <dt>
              <Icon name="database" size={14} />
              元数据缓存
            </dt>
            <dd>
              {health?.with_db ? (
                <>
                  {health.cache_table_count ?? 0}
                  <small>张表</small>
                </>
              ) : (
                "待检测"
              )}
            </dd>
          </div>
          <div>
            <dt>
              <Icon name="shield" size={14} />
              数据连接
            </dt>
            <dd
              className={
                health?.with_db
                  ? "status-value status-value--ok"
                  : "status-value"
              }
            >
              <span className="status-dot" />
              {health?.with_db ? "已启用" : health ? "未启用" : "未连接"}
            </dd>
          </div>
          <div>
            <dt>
              <Icon name="chart" size={14} />
              分析能力
            </dt>
            <dd>
              {health ? (
                <>
                  {health.tools.length}
                  <small>项工具</small>
                </>
              ) : (
                "待检测"
              )}
            </dd>
          </div>
        </dl>
        <button type="button" onClick={onMetadata}>
          <span className="sr-only">管理元数据</span>
          <Icon name="arrow" size={14} />
        </button>
      </div>
      <div className="home-footnote">
        <Icon name="shield" size={13} />
        结构探索 → SQL 查询 → 数据洞察，分析过程始终可见。
      </div>
    </div>
  );
}
