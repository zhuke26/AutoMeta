import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PdfEvidenceViewer } from "./PdfEvidenceViewer";


const pages = [
  { render: vi.fn(() => ({ promise: Promise.resolve() })), getViewport: vi.fn(() => ({ width: 612, height: 792 })), getTextContent: vi.fn(async () => ({ items: [{ str: "Background" }] })) },
  { render: vi.fn(() => ({ promise: Promise.resolve() })), getViewport: vi.fn(() => ({ width: 612, height: 792 })), getTextContent: vi.fn(async () => ({ items: [{ str: "Primary outcome improved" }] })) },
];

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: vi.fn(() => ({
    destroy: vi.fn(),
    promise: Promise.resolve({ numPages: 2, getPage: (page: number) => Promise.resolve(pages[page - 1]) }),
  })),
}));
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({ default: "/worker.js" }));


beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D);
});


describe("PdfEvidenceViewer", () => {
  it("opens the located page and converts a bottom-left bbox into a highlight", async () => {
    const { container } = render(<PdfEvidenceViewer
      locator={{
        file_id: "file-1", source_id: "source-1", page_number: 2,
        element_type: "body", parser_name: "docling", parser_version: "2.0",
        extraction_type: "direct", derivation: "", quotation: "Primary outcome improved",
        bbox: { left: 61.2, bottom: 79.2, right: 306, top: 158.4, page_width: 612, page_height: 792 },
      }}
      reviewId="review-1"
      onClose={() => undefined}
    />);
    expect(await screen.findByText("Page 2 of 2")).toBeInTheDocument();
    const highlight = container.querySelector(".pdf-highlight") as HTMLElement;
    expect(highlight.style.left).toBe("10%");
    expect(highlight.style.top).toBe("80%");
    expect(highlight.style.width).toBe("40%");
    expect(highlight.style.height).toBe("10%");
  });

  it("searches pages and degrades when exact page is unavailable", async () => {
    const { rerender } = render(<PdfEvidenceViewer
      locator={{ element_type: "unknown", parser_name: "unknown", parser_version: "", extraction_type: "direct", derivation: "", quotation: "Primary outcome improved" }}
      reviewId="review-1"
      onClose={() => undefined}
    />);
    expect(screen.getByText("Exact page location unavailable")).toBeInTheDocument();
    rerender(<PdfEvidenceViewer
      locator={{ file_id: "file-1", page_number: 1, element_type: "body", parser_name: "pypdfium2", parser_version: "1", extraction_type: "direct", derivation: "", quotation: "Primary outcome improved" }}
      reviewId="review-1"
      onClose={() => undefined}
    />);
    await screen.findByText("Page 1 of 2");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search PDF" }), "Primary outcome");
    await userEvent.click(screen.getByRole("button", { name: "Find" }));
    await waitFor(() => expect(screen.getByText("Page 2 of 2")).toBeInTheDocument());
  });
});
