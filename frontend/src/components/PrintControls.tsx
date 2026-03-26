import { Button } from "@/components/ui/button";
import { Pause, Play, X } from "lucide-react";
import type { PrinterStatus } from "@/lib/api";

interface PrintControlsProps {
  status: PrinterStatus;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
}

export function PrintControls({
  status,
  onPause,
  onResume,
  onCancel,
}: PrintControlsProps) {
  return (
    <div className="flex items-center justify-center gap-3">
      {status === "printing" ? (
        <Button
          onClick={onPause}
          variant="secondary"
          size="lg"
          className="gap-2"
        >
          <Pause className="h-4 w-4" />
          Pause
        </Button>
      ) : status === "paused" ? (
        <Button onClick={onResume} size="lg" className="gap-2">
          <Play className="h-4 w-4" />
          Resume
        </Button>
      ) : null}

      {(status === "printing" || status === "paused") && (
        <Button
          onClick={onCancel}
          variant="destructive"
          size="lg"
          className="gap-2"
        >
          <X className="h-4 w-4" />
          Cancel
        </Button>
      )}
    </div>
  );
}
