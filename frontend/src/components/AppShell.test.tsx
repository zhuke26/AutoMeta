import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppShell } from "./AppShell";


describe("AppShell", () => {
  it("renders the product navigation and manuscript Logo A", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <p>Workspace content</p>
        </AppShell>
      </MemoryRouter>,
    );

    expect(screen.getByRole("img", { name: "AutoMeta" })).toBeInTheDocument();
    expect(screen.getByText("Evidence synthesis workspace")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New review" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Library" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "System status" })).toHaveAttribute(
      "href",
      "/system",
    );
  });

  it("shows all agents, checkpoints, and semantic stage states", () => {
    const { container } = render(
      <MemoryRouter>
        <AppShell
          activeStage="screening"
          stageStates={{ search: "approved", screening: "running", extraction: "stale" }}
        >
          <p>Workspace content</p>
        </AppShell>
      </MemoryRouter>,
    );

    for (const name of [
      "Search Agent",
      "Screening Agent",
      "Extraction Agent",
      "Meta-analysis Agent",
    ]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Retrieved records: Review & edit")).toBeInTheDocument();
    expect(screen.getByLabelText("Selected studies: Reviewer select")).toBeInTheDocument();
    expect(screen.getByLabelText("Source-linked values: Human review")).toBeInTheDocument();
    expect(container.querySelector('[data-stage="search"]')).toHaveAttribute(
      "data-state",
      "approved",
    );
    expect(container.querySelector('[data-stage="screening"]')).toHaveAttribute(
      "data-state",
      "running",
    );
    expect(container.querySelector('[data-stage="extraction"]')).toHaveAttribute(
      "data-state",
      "stale",
    );
  });
});
