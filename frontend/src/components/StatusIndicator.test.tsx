import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusIndicator } from "./StatusIndicator";

describe("StatusIndicator", () => {
  it("shows Ready for idle status", () => {
    render(<StatusIndicator status="idle" />);
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("shows Printing for printing status", () => {
    render(<StatusIndicator status="printing" />);
    expect(screen.getByText("Printing")).toBeInTheDocument();
  });

  it("shows Paused for paused status", () => {
    render(<StatusIndicator status="paused" />);
    expect(screen.getByText("Paused")).toBeInTheDocument();
  });

  it("shows Offline for offline status", () => {
    render(<StatusIndicator status="offline" />);
    expect(screen.getByText("Offline")).toBeInTheDocument();
  });
});
