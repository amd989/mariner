import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Play, Layers, Clock, Ruler, Trash2 } from "lucide-react";
import { api, formatTime, type FileEntry } from "@/lib/api";

interface FileDetailDialogProps {
  file: FileEntry | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function FileDetailDialog({
  file,
  open,
  onOpenChange,
}: FileDetailDialogProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: details } = useQuery({
    queryKey: ["fileDetails", file?.path],
    queryFn: () => api.fileDetails(file!.path),
    enabled: !!file?.can_be_printed && open,
  });

  if (!file) return null;

  const handlePrint = async () => {
    await api.printerCommand("start_print", file.path);
    onOpenChange(false);
    navigate("/");
  };

  const handleDelete = async () => {
    await api.deleteFile(file.path);
    onOpenChange(false);
    queryClient.invalidateQueries({ queryKey: ["files"] });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="break-all font-mono text-base">
            {file.filename}
          </DialogTitle>
          <DialogDescription>
            {file.can_be_printed ? "Printable file details" : "File details"}
          </DialogDescription>
        </DialogHeader>

        {file.can_be_printed && (
          <>
            {/* Layer preview */}
            <div className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-md border bg-muted">
              <img
                src={api.filePreviewUrl(file.path)}
                alt="Layer preview"
                className="h-full w-full object-contain"
                onError={(e) => {
                  const el = e.target as HTMLImageElement;
                  el.style.display = "none";
                }}
              />
            </div>

            {/* Metadata */}
            {details && (
              <div className="grid grid-cols-3 gap-3">
                <MetaItem
                  icon={Layers}
                  label="Layers"
                  value={`${details.layer_count}`}
                />
                <MetaItem
                  icon={Clock}
                  label="Est. Time"
                  value={formatTime(details.print_time_secs)}
                />
                <MetaItem
                  icon={Ruler}
                  label="Height"
                  value={`${details.height_mm || (details.layer_height_mm * details.layer_count).toFixed(1)}mm`}
                />
              </div>
            )}
          </>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="ghost"
            className="gap-2 text-muted-foreground"
            onClick={handleDelete}
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
          {file.can_be_printed && (
            <Button className="gap-2" onClick={handlePrint}>
              <Play className="h-4 w-4" />
              Start Print
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MetaItem({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border bg-card p-2 text-center">
      <Icon className="mx-auto h-4 w-4 text-muted-foreground" />
      <p className="mt-1 text-[10px] text-muted-foreground">{label}</p>
      <p className="font-mono text-sm font-medium">{value}</p>
    </div>
  );
}
