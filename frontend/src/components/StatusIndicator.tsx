import { cn } from "@/lib/utils";
import type { PrinterStatus } from "@/lib/api";

const statusConfig: Record<
  PrinterStatus,
  { label: string; dotClass: string; textClass: string }
> = {
  idle: { label: "Ready", dotClass: "bg-success", textClass: "text-success" },
  printing: {
    label: "Printing",
    dotClass: "bg-primary animate-pulse-glow",
    textClass: "text-primary",
  },
  paused: {
    label: "Paused",
    dotClass: "bg-warning",
    textClass: "text-warning",
  },
  offline: {
    label: "Offline",
    dotClass: "bg-destructive",
    textClass: "text-destructive",
  },
};

export function StatusIndicator({ status }: { status: PrinterStatus }) {
  const config = statusConfig[status];

  return (
    <div className="flex items-center gap-2">
      <div className={cn("h-2.5 w-2.5 rounded-full", config.dotClass)} />
      <span className={cn("font-mono text-sm font-medium", config.textClass)}>
        {config.label}
      </span>
    </div>
  );
}
