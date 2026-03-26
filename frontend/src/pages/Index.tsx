import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PrintProgress } from "@/components/PrintProgress";
import { PrintControls } from "@/components/PrintControls";
import { StatusIndicator } from "@/components/StatusIndicator";
import { api, mapPrinterState, type PrinterStatus } from "@/lib/api";
import { WifiOff, CheckCircle2, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function Index() {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["printStatus"],
    queryFn: () => api.printStatus(),
    refetchInterval: 5000,
  });

  const status: PrinterStatus = data ? mapPrinterState(data.state) : "offline";

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["printStatus"] });

  const handlePause = async () => {
    await api.printerCommand("pause_print");
    refresh();
  };

  const handleResume = async () => {
    await api.printerCommand("resume_print");
    refresh();
  };

  const handleCancel = async () => {
    await api.printerCommand("cancel_print");
    refresh();
  };

  const printerName =
    document
      .querySelector('meta[name="printer-display-name"]')
      ?.getAttribute("content") || undefined;

  if (isLoading) {
    return (
      <div className="container py-6">
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card px-6 py-16">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="mt-4 text-sm text-muted-foreground">
            Connecting to printer...
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container py-6">
        <div className="flex flex-col items-center justify-center rounded-lg border border-destructive/20 bg-destructive/5 px-6 py-16">
          <WifiOff className="h-8 w-8 text-destructive" />
          <h2 className="mt-4 text-lg font-semibold">Connection Error</h2>
          <p className="mt-1 text-center text-sm text-muted-foreground">
            Could not reach the printer. Check that the backend is running.
          </p>
        </div>
      </div>
    );
  }

  const job = data
    ? {
        fileName: data.selected_file || "",
        currentLayer: data.current_layer ?? 0,
        totalLayers: data.layer_count ?? 0,
        progress: data.progress,
        elapsedTime: data.print_time_secs
          ? data.print_time_secs - (data.time_left_secs ?? 0)
          : 0,
        remainingTime: data.time_left_secs ?? 0,
        status,
      }
    : null;

  return (
    <div className="container py-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Printer Dashboard
          </h1>
          {printerName && (
            <p className="text-sm text-muted-foreground">{printerName}</p>
          )}
        </div>
        <StatusIndicator status={status} />
      </div>

      {/* Printing / Paused */}
      {(status === "printing" || status === "paused") && job && (
        <div className="space-y-6">
          <div className="rounded-lg border bg-card p-6">
            <PrintProgress job={job} />
          </div>
          <PrintControls
            status={status}
            onPause={handlePause}
            onResume={handleResume}
            onCancel={handleCancel}
          />
        </div>
      )}

      {/* Idle */}
      {status === "idle" && (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card px-6 py-16">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-success/10">
            <CheckCircle2 className="h-8 w-8 text-success" />
          </div>
          <h2 className="mt-4 text-lg font-semibold">Ready to Print</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Select a file from the File Manager to start printing.
          </p>
          <Button asChild className="mt-4">
            <Link to="/files">Open File Manager</Link>
          </Button>
        </div>
      )}

      {/* Offline */}
      {status === "offline" && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-destructive/20 bg-destructive/5 px-6 py-16">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
            <WifiOff className="h-8 w-8 text-destructive" />
          </div>
          <h2 className="mt-4 text-lg font-semibold">Printer Offline</h2>
          <p className="mt-1 text-center text-sm text-muted-foreground">
            Unable to connect. Check USB connection and power.
          </p>
        </div>
      )}
    </div>
  );
}
