import { useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  formatTime,
  type FileEntry,
  type DirectoryEntry,
} from "@/lib/api";
import { FileDetailDialog } from "@/components/FileDetailDialog";
import { Button } from "@/components/ui/button";
import {
  Folder,
  FileText,
  Layers,
  Clock,
  Upload,
  Loader2,
  ArrowLeft,
} from "lucide-react";

function FileIcon({ canBePrinted }: { canBePrinted: boolean }) {
  if (canBePrinted) return <Layers className="h-4 w-4 text-primary" />;
  return <FileText className="h-4 w-4 text-muted-foreground" />;
}

export default function Files() {
  const [currentPath, setCurrentPath] = useState(".");
  const [selectedFile, setSelectedFile] = useState<FileEntry | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["files", currentPath],
    queryFn: () => api.listFiles(currentPath),
  });

  const handleDirectoryClick = (dirname: string) => {
    if (dirname === "..") {
      setCurrentPath((prev) => {
        const parts = prev.split("/").filter(Boolean);
        parts.pop();
        return parts.length === 0 ? "." : parts.join("/");
      });
    } else {
      setCurrentPath((prev) => (prev === "." ? dirname : `${prev}/${dirname}`));
    }
  };

  const handleFileClick = (file: FileEntry) => {
    setSelectedFile(file);
    setDialogOpen(true);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await api.uploadFile(file);
    queryClient.invalidateQueries({ queryKey: ["files", currentPath] });
    e.target.value = "";
  };

  return (
    <div className="container py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">File Manager</h1>
          <p className="text-sm text-muted-foreground">
            {currentPath === "." ? "/" : `/${currentPath}`}
          </p>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleUpload}
          />
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Upload</span>
          </Button>
        </div>
      </div>

      <div className="rounded-lg border bg-card">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <span className="ml-2 text-sm text-muted-foreground">
              Loading files...
            </span>
          </div>
        ) : (
          <div className="divide-y">
            {/* Back button */}
            {currentPath !== "." && (
              <button
                onClick={() => handleDirectoryClick("..")}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
              >
                <ArrowLeft className="h-3.5 w-3.5 text-muted-foreground" />
                <Folder className="h-4 w-4 text-primary" />
                <span className="font-medium">..</span>
              </button>
            )}

            {/* Directories */}
            {data?.directories.map((dir: DirectoryEntry) => (
              <button
                key={dir.dirname}
                onClick={() => handleDirectoryClick(dir.dirname)}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
              >
                <Folder className="h-4 w-4 text-primary" />
                <span className="font-medium">{dir.dirname}</span>
              </button>
            ))}

            {/* Files */}
            {data?.files.map((file: FileEntry) => (
              <button
                key={file.filename}
                onClick={() => handleFileClick(file)}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
              >
                <FileIcon canBePrinted={file.can_be_printed} />
                <span className="min-w-0 flex-1 truncate font-mono text-sm">
                  {file.filename}
                </span>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  {file.print_time_secs && (
                    <span className="hidden items-center gap-1 sm:flex">
                      <Clock className="h-3 w-3" />
                      {formatTime(file.print_time_secs)}
                    </span>
                  )}
                  {file.can_be_printed && (
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase text-primary">
                      print
                    </span>
                  )}
                </div>
              </button>
            ))}

            {/* Empty state */}
            {data &&
              data.directories.length === 0 &&
              data.files.length === 0 && (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  No files found in this directory.
                </div>
              )}
          </div>
        )}
      </div>

      <FileDetailDialog
        file={selectedFile}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
