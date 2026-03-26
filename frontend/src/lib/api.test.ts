import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, mapPrinterState, formatTime, formatFileSize } from "./api";

describe("mapPrinterState", () => {
  it("maps PRINTING to printing", () => {
    expect(mapPrinterState("PRINTING")).toBe("printing");
  });

  it("maps STARTING_PRINT to printing", () => {
    expect(mapPrinterState("STARTING_PRINT")).toBe("printing");
  });

  it("maps PAUSED to paused", () => {
    expect(mapPrinterState("PAUSED")).toBe("paused");
  });

  it("maps CLOSED to offline", () => {
    expect(mapPrinterState("CLOSED")).toBe("offline");
  });

  it("maps IDLE to idle", () => {
    expect(mapPrinterState("IDLE")).toBe("idle");
  });

  it("maps unknown states to idle", () => {
    expect(mapPrinterState("UNKNOWN")).toBe("idle");
  });
});

describe("formatTime", () => {
  it("formats seconds to minutes only", () => {
    expect(formatTime(300)).toBe("5m");
  });

  it("formats seconds to hours and minutes", () => {
    expect(formatTime(3720)).toBe("1h 2m");
  });

  it("formats zero seconds", () => {
    expect(formatTime(0)).toBe("0m");
  });

  it("formats large values", () => {
    expect(formatTime(16740)).toBe("4h 39m");
  });
});

describe("formatFileSize", () => {
  it("formats bytes", () => {
    expect(formatFileSize(512)).toBe("512 B");
  });

  it("formats kilobytes", () => {
    expect(formatFileSize(2048)).toBe("2.0 KB");
  });

  it("formats megabytes", () => {
    expect(formatFileSize(48_200_000)).toBe("46.0 MB");
  });
});

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches print status", async () => {
    const mockResponse = {
      state: "IDLE",
      selected_file: "",
      progress: 0,
    };
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response);

    const result = await api.printStatus();
    expect(result).toEqual(mockResponse);
    expect(fetch).toHaveBeenCalledWith("/api/print_status", expect.any(Object));
  });

  it("fetches file list with path", async () => {
    const mockResponse = { files: [], directories: [] };
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response);

    await api.listFiles("subdir");
    expect(fetch).toHaveBeenCalledWith(
      "/api/list_files?path=subdir",
      expect.any(Object),
    );
  });

  it("throws on non-ok response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
    } as Response);

    await expect(api.printStatus()).rejects.toThrow("API error: 500");
  });

  it("sends CSRF token from meta tag", async () => {
    const meta = document.createElement("meta");
    meta.name = "csrf-token";
    meta.content = "test-csrf-token";
    document.head.appendChild(meta);

    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response);

    await api.printStatus();
    expect(fetch).toHaveBeenCalledWith(
      "/api/print_status",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-CSRFToken": "test-csrf-token",
        }),
      }),
    );

    document.head.removeChild(meta);
  });

  it("sends printer commands with POST", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    } as Response);

    await api.printerCommand("pause_print");
    expect(fetch).toHaveBeenCalledWith(
      "/api/printer/command/pause_print",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("sends filename with start_print command", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    } as Response);

    await api.printerCommand("start_print", "test.ctb");
    expect(fetch).toHaveBeenCalledWith(
      "/api/printer/command/start_print?filename=test.ctb",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("generates correct file preview URL", () => {
    expect(api.filePreviewUrl("subdir/test.ctb")).toBe(
      "/api/file_preview?filename=subdir%2Ftest.ctb",
    );
  });
});
