export type PrinterStatus = "idle" | "printing" | "paused" | "offline";

export interface PrintStatusResponse {
  state: string;
  selected_file: string;
  progress: number;
  current_layer?: number;
  layer_count?: number;
  print_time_secs?: number;
  time_left_secs?: number;
}

export interface FileEntry {
  filename: string;
  path: string;
  can_be_printed: boolean;
  print_time_secs?: number;
}

export interface DirectoryEntry {
  dirname: string;
}

export interface FileListResponse {
  files: FileEntry[];
  directories: DirectoryEntry[];
}

export interface FileDetailsResponse {
  filename: string;
  path: string;
  bed_size_mm: number[];
  height_mm: number;
  layer_count: number;
  layer_height_mm: number;
  resolution: number[];
  print_time_secs: number;
}

function getCsrfToken(): string | null {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta?.getAttribute("content") ?? null;
}

async function apiFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  const csrf = getCsrfToken();
  if (csrf) {
    headers["X-CSRFToken"] = csrf;
  }

  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  async printStatus(): Promise<PrintStatusResponse> {
    return apiFetch<PrintStatusResponse>("/api/print_status");
  },

  async listFiles(path: string = "."): Promise<FileListResponse> {
    return apiFetch<FileListResponse>(
      `/api/list_files?path=${encodeURIComponent(path)}`,
    );
  },

  async fileDetails(filename: string): Promise<FileDetailsResponse> {
    return apiFetch<FileDetailsResponse>(
      `/api/file_details?filename=${encodeURIComponent(filename)}`,
    );
  },

  filePreviewUrl(filename: string): string {
    return `/api/file_preview?filename=${encodeURIComponent(filename)}`;
  },

  async uploadFile(file: File, path: string = "."): Promise<void> {
    const formData = new FormData();
    formData.append("file", file);
    const csrf = getCsrfToken();
    const headers: Record<string, string> = {};
    if (csrf) headers["X-CSRFToken"] = csrf;
    const q = new URLSearchParams({ path });
    const res = await fetch(`/api/upload_file?${q.toString()}`, {
      method: "POST",
      headers,
      body: formData,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  },

  async deleteFile(filename: string): Promise<void> {
    await apiFetch(
      `/api/delete_file?filename=${encodeURIComponent(filename)}`,
      {
        method: "POST",
      },
    );
  },

  async createDirectory(parentPath: string, name: string): Promise<void> {
    const params = new URLSearchParams({
      path: parentPath,
      name,
    });
    await apiFetch(`/api/create_directory?${params.toString()}`, {
      method: "POST",
    });
  },

  async printerCommand(
    command: "start_print" | "pause_print" | "resume_print" | "cancel_print",
    filename?: string,
  ): Promise<void> {
    const params = filename ? `?filename=${encodeURIComponent(filename)}` : "";
    await apiFetch(`/api/printer/command/${command}${params}`, {
      method: "POST",
    });
  },
};

export function mapPrinterState(state: string): PrinterStatus {
  switch (state) {
    case "PRINTING":
    case "STARTING_PRINT":
      return "printing";
    case "PAUSED":
      return "paused";
    case "CLOSED":
      return "offline";
    default:
      return "idle";
  }
}

export function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
