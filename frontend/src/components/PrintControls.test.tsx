import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PrintControls } from "./PrintControls";

describe("PrintControls", () => {
  it("shows Pause button when printing", () => {
    render(
      <PrintControls
        status="printing"
        onPause={vi.fn()}
        onResume={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Pause")).toBeInTheDocument();
    expect(screen.queryByText("Resume")).not.toBeInTheDocument();
  });

  it("shows Resume button when paused", () => {
    render(
      <PrintControls
        status="paused"
        onPause={vi.fn()}
        onResume={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Resume")).toBeInTheDocument();
    expect(screen.queryByText("Pause")).not.toBeInTheDocument();
  });

  it("shows Cancel button when printing or paused", () => {
    const { rerender } = render(
      <PrintControls
        status="printing"
        onPause={vi.fn()}
        onResume={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Cancel")).toBeInTheDocument();

    rerender(
      <PrintControls
        status="paused"
        onPause={vi.fn()}
        onResume={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("calls onPause when Pause is clicked", () => {
    const onPause = vi.fn();
    render(
      <PrintControls
        status="printing"
        onPause={onPause}
        onResume={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Pause"));
    expect(onPause).toHaveBeenCalledOnce();
  });

  it("calls onResume when Resume is clicked", () => {
    const onResume = vi.fn();
    render(
      <PrintControls
        status="paused"
        onPause={vi.fn()}
        onResume={onResume}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Resume"));
    expect(onResume).toHaveBeenCalledOnce();
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn();
    render(
      <PrintControls
        status="printing"
        onPause={vi.fn()}
        onResume={vi.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
