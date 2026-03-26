import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PrintProgress } from "./PrintProgress";
import type { PrintJob } from "./PrintProgress";

const mockJob: PrintJob = {
  fileName: "dragon.ctb",
  currentLayer: 847,
  totalLayers: 2140,
  progress: 39.6,
  elapsedTime: 4820,
  remainingTime: 7340,
  status: "printing",
};

describe("PrintProgress", () => {
  it("renders progress percentage", () => {
    render(<PrintProgress job={mockJob} />);
    expect(screen.getByText("39.6%")).toBeInTheDocument();
  });

  it("renders current layer", () => {
    render(<PrintProgress job={mockJob} />);
    expect(screen.getByText("847")).toBeInTheDocument();
  });

  it("renders total layers", () => {
    render(<PrintProgress job={mockJob} />);
    expect(screen.getByText("2140")).toBeInTheDocument();
  });

  it("renders elapsed time", () => {
    render(<PrintProgress job={mockJob} />);
    expect(screen.getByText("1h 20m")).toBeInTheDocument();
  });

  it("renders remaining time", () => {
    render(<PrintProgress job={mockJob} />);
    expect(screen.getByText("2h 2m")).toBeInTheDocument();
  });

  it("renders file name", () => {
    render(<PrintProgress job={mockJob} />);
    expect(screen.getByText("dragon.ctb")).toBeInTheDocument();
  });
});
