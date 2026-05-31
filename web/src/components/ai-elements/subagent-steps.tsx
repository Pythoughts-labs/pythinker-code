"use client";

import { cn } from "@/lib/utils";
import type { SubagentStep } from "@/hooks/types";
import type { ComponentProps } from "react";
import { memo, useState } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Shimmer } from "./shimmer";
import { ChevronRightIcon, XIcon } from "lucide-react";

// ---------------------------------------------------------------------------
// SubagentActivity — top-level wrapper rendered inside Tool's ToolContent area
// ---------------------------------------------------------------------------

export type SubagentActivityProps = ComponentProps<"div"> & {
  steps: SubagentStep[];
  isRunning?: boolean;
  defaultOpen?: boolean;
  /** Built-in subagent type (coder / explore / plan) */
  subagentType?: string;
};

export const SubagentActivity = memo(
  ({
    className,
    steps,
    isRunning = false,
    defaultOpen = false,
    subagentType,
    ...props
  }: SubagentActivityProps) => {
    const agentLabel = subagentType
      ? `${subagentType.charAt(0).toUpperCase() + subagentType.slice(1)} agent`
      : "Agent";
    const [isOpen, setIsOpen] = useState(defaultOpen);

    const toolCallCount = steps.filter((s) => s.kind === "tool-call").length;
    const hasError = steps.some(
      (s) => s.kind === "tool-call" && s.status === "error",
    );

    return (
      <Collapsible
        className={cn("mt-2", className)}
        open={isOpen}
        onOpenChange={setIsOpen}
        {...props}
      >
        <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground group cursor-pointer">
          <span className="flex size-3 items-center justify-center shrink-0">
            {hasError && !isRunning ? (
              <XIcon className="size-3 text-destructive" />
            ) : (
              <span
                className={cn(
                  "size-2 rounded-full",
                  isRunning
                    ? "bg-muted-foreground animate-pulse motion-reduce:animate-none"
                    : "bg-success",
                )}
              />
            )}
          </span>
          <span>
            {isRunning ? (
              <>
                {agentLabel} working
                <Shimmer
                  as="span"
                  duration={1}
                  className="text-muted-foreground ml-0.5"
                >
                  ...
                </Shimmer>
              </>
            ) : hasError ? (
              toolCallCount > 0 ? (
                `${agentLabel} failed · ${toolCallCount} tool call${toolCallCount !== 1 ? "s" : ""}`
              ) : (
                `${agentLabel} failed`
              )
            ) : toolCallCount > 0 ? (
              `${agentLabel} completed · ${toolCallCount} tool call${toolCallCount !== 1 ? "s" : ""}`
            ) : (
              `${agentLabel} completed`
            )}
          </span>
          <ChevronRightIcon
            className={cn(
              "size-3 text-muted-foreground transition-transform duration-200",
              isOpen && "rotate-90",
            )}
          />
        </CollapsibleTrigger>

        <CollapsibleContent
          className={cn(
            "mt-1.5 space-y-0.5 border-l-2 border-border pl-3",
            "data-[state=closed]:fade-out-0 data-[state=open]:slide-in-from-top-1 outline-none data-[state=closed]:animate-out data-[state=open]:animate-in",
          )}
        >
          {steps.map((step, index) => (
            <SubagentStepItem key={`sa-step-${index}`} step={step} />
          ))}
        </CollapsibleContent>
      </Collapsible>
    );
  },
);

SubagentActivity.displayName = "SubagentActivity";

// ---------------------------------------------------------------------------
// SubagentStepItem — renders a single step based on kind
// ---------------------------------------------------------------------------

const SubagentStepItem = ({ step }: { step: SubagentStep }) => {
  switch (step.kind) {
    case "thinking":
      return (
        <div className="text-muted-foreground/60 italic text-xs line-clamp-2">
          {step.text}
        </div>
      );

    case "text":
      return (
        <div className="text-foreground/70 text-xs line-clamp-2">
          {step.text}
        </div>
      );

    case "tool-call":
      return <SubToolCallItem step={step} />;

    default:
      return null;
  }
};

// ---------------------------------------------------------------------------
// SubToolCallItem — expandable sub-tool-call with status + output
// ---------------------------------------------------------------------------

/** Extract a primary parameter value for inline display */
const getPrimaryParam = (input: unknown): string | null => {
  if (!input || typeof input !== "object") return null;
  const keys = ["path", "command", "pattern", "url", "query", "file_path"];
  for (const key of keys) {
    const val = (input as Record<string, unknown>)[key];
    if (typeof val === "string" && val.length > 0) {
      return val.length > 50 ? `${val.slice(0, 50)}…` : val;
    }
  }
  return null;
};

const getSubToolStatusIcon = (status: string) => {
  switch (status) {
    case "success":
      return (
        <span className="flex size-2.5 items-center justify-center shrink-0">
          <span className="size-2 rounded-full bg-success" />
        </span>
      );
    case "error":
      return <XIcon className="size-2.5 text-destructive shrink-0" />;
    default:
      // Running: pulse a grey solid circle; keep the footprint aligned with
      // the finished green dot and failed red X states.
      return (
        <span className="flex size-2.5 items-center justify-center shrink-0">
          <span className="size-2 rounded-full bg-muted-foreground animate-pulse motion-reduce:animate-none" />
        </span>
      );
  }
};

const SubToolCallItem = ({
  step,
}: {
  step: Extract<SubagentStep, { kind: "tool-call" }>;
}) => {
  const [expanded, setExpanded] = useState(false);
  const primaryParam = getPrimaryParam(step.input);
  const hasExpandableContent = Boolean(step.output || step.errorText);

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-1 text-xs",
          hasExpandableContent && "cursor-pointer",
        )}
        onClick={() => hasExpandableContent && setExpanded(!expanded)}
        onKeyDown={(e) => {
          if (hasExpandableContent && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
        role={hasExpandableContent ? "button" : undefined}
        tabIndex={hasExpandableContent ? 0 : undefined}
      >
        {getSubToolStatusIcon(step.status)}
        <span className="text-primary/80 font-medium">{step.toolName}</span>
        {primaryParam && !expanded && (
          <span className="text-muted-foreground truncate">
            ({primaryParam})
          </span>
        )}
        {hasExpandableContent && (
          <ChevronRightIcon
            className={cn(
              "size-2.5 text-muted-foreground/50 transition-transform duration-200",
              expanded && "rotate-90",
            )}
          />
        )}
      </div>
      {expanded && (
        <div className="ml-4 mt-0.5">
          {step.errorText && (
            <pre className="text-xs text-destructive whitespace-pre-wrap max-h-24 overflow-y-auto">
              {step.errorText}
            </pre>
          )}
          {step.output && !step.errorText && (
            <pre className="text-xs text-foreground/60 whitespace-pre-wrap max-h-24 overflow-y-auto">
              {step.output.length > 500
                ? `${step.output.slice(0, 500)}…`
                : step.output}
            </pre>
          )}
        </div>
      )}
    </div>
  );
};
