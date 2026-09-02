import { useEffect, useMemo, useState } from "react";
import type { AgentEvent } from "../types";
import { getToolLabel } from "../utils/toolLabels";
import { ToolOutput } from "./ToolOutput";

type StepStatus = "done" | "active" | "pending";

interface PipelineStep {
  name: string;
  label: string;
  status: StepStatus;
  events: AgentEvent[];
}

function buildSteps(events: AgentEvent[]): PipelineStep[] {
  const toolNames: string[] = [];
  for (const ev of events) {
    if (ev.tool_name && !toolNames.includes(ev.tool_name)) {
      toolNames.push(ev.tool_name);
    }
  }
  if (toolNames.length === 0) return [];

  const lastEvent = events[events.length - 1];
  const activeTool =
    lastEvent?.type === "tool_start" ? (lastEvent.tool_name ?? null) : null;

  return toolNames.map((name) => {
    const related = events.filter((e) => e.tool_name === name);
    const hasResult = related.some((e) => e.type === "tool_result");
    let status: StepStatus = "pending";
    if (hasResult) status = "done";
    else if (name === activeTool) status = "active";
    return { name, label: getToolLabel(name), status, events: related };
  });
}

function statusIcon(status: StepStatus) {
  switch (status) {
    case "done":
      return "✓";
    case "active":
      return "●";
    default:
      return "○";
  }
}

interface ToolPipelineProps {
  events: AgentEvent[];
  isStreaming?: boolean;
}

export function ToolPipeline({ events, isStreaming }: ToolPipelineProps) {
  const steps = useMemo(() => buildSteps(events), [events]);
  const [expanded, setExpanded] = useState<string | null>(null);

  const activeStep = steps.find((s) => s.status === "active");

  useEffect(() => {
    if (isStreaming && activeStep) {
      setExpanded(activeStep.name);
    }
  }, [isStreaming, activeStep?.name]);

  if (steps.length === 0) return null;

  const toggle = (name: string) => {
    setExpanded((prev) => (prev === name ? null : name));
  };

  const expandedStep = steps.find((s) => s.name === expanded);

  return (
    <>
      <div className="pipeline" role="list" aria-label="查询步骤">
        {steps.map((step, i) => (
          <div key={step.name} className="pipeline__node" role="listitem">
            {i > 0 && (
              <span className="pipeline__arrow" aria-hidden="true">
                →
              </span>
            )}
            <button
              type="button"
              className={`pipeline__step pipeline__step--${step.status}`}
              onClick={() => toggle(step.name)}
              aria-expanded={expanded === step.name}
              aria-label={step.label}
            >
              <span className="pipeline__icon" aria-hidden="true">
                {statusIcon(step.status)}
              </span>
              {step.label}
            </button>
          </div>
        ))}
      </div>
      {expandedStep && <ToolOutput events={expandedStep.events} />}
    </>
  );
}
