import { useEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import type { SourceLocator } from "../api/types";

export function PdfEvidenceViewer({
  locator,
  reviewId,
  onClose,
}: {
  locator: SourceLocator;
  reviewId: string;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(locator.page_number ?? 1);
  const [scale, setScale] = useState(1);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!locator.file_id) return;
    let active = true;
    let task: PDFDocumentLoadingTask | undefined;
    void import("pdfjs-dist").then((pdfjs) => {
      pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
      task = pdfjs.getDocument(
        `/api/v1/reviews/${reviewId}/files/${locator.file_id}/content`,
      );
      return task.promise;
    }).then((pdf) => {
      if (active) setDocument(pdf);
    }).catch(() => {
      if (active) setError("Could not open the local PDF.");
    });
    return () => { active = false; void task?.destroy(); };
  }, [locator.file_id, reviewId]);

  useEffect(() => {
    if (!document || !canvasRef.current) return;
    let active = true;
    void document.getPage(pageNumber).then(async (page) => {
      if (!active || !canvasRef.current) return;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const context = canvas.getContext("2d");
      if (context) await page.render({ canvasContext: context, viewport }).promise;
    }).catch(() => { if (active) setError("Could not render this PDF page."); });
    return () => { active = false; };
  }, [document, pageNumber, scale]);

  const highlight = useMemo(() => {
    const box = locator.bbox;
    if (!box || locator.page_number !== pageNumber) return undefined;
    return {
      left: `${(box.left / box.page_width) * 100}%`,
      top: `${((box.page_height - box.top) / box.page_height) * 100}%`,
      width: `${((box.right - box.left) / box.page_width) * 100}%`,
      height: `${((box.top - box.bottom) / box.page_height) * 100}%`,
    };
  }, [locator.bbox, locator.page_number, pageNumber]);

  const find = async () => {
    if (!document || !search.trim()) return;
    const needle = search.trim().toLocaleLowerCase();
    for (let index = 1; index <= document.numPages; index += 1) {
      const page = await document.getPage(index);
      const content = await page.getTextContent();
      const text = content.items.map((item) => "str" in item ? item.str : "").join(" ");
      if (text.toLocaleLowerCase().includes(needle)) {
        setPageNumber(index);
        return;
      }
    }
    setError("Text not found in this PDF.");
  };

  return (
    <div className="dialog-backdrop pdf-dialog" role="presentation">
      <section aria-label="PDF evidence" aria-modal="true" className="pdf-viewer" role="dialog">
        <header><div><p className="eyebrow">Source evidence</p><h2>{locator.quotation || "Evidence location"}</h2></div><button className="button" onClick={onClose} type="button">Close</button></header>
        {!locator.page_number ? <p className="security-warning">Exact page location unavailable</p> : null}
        {locator.file_id ? <div className="pdf-toolbar"><button className="button" disabled={pageNumber <= 1} onClick={() => setPageNumber((page) => page - 1)} type="button">Previous page</button><span>Page {pageNumber} of {document?.numPages ?? "…"}</span><button className="button" disabled={!document || pageNumber >= document.numPages} onClick={() => setPageNumber((page) => page + 1)} type="button">Next page</button><button className="button" onClick={() => setScale((value) => Math.max(.5, value - .25))} type="button">Zoom out</button><button className="button" onClick={() => setScale((value) => Math.min(3, value + .25))} type="button">Zoom in</button><input aria-label="Search PDF" onChange={(event) => setSearch(event.target.value)} placeholder="Search this PDF" type="search" value={search} /><button className="button" onClick={() => void find()} type="button">Find</button></div> : null}
        <div className="pdf-reader-body">
          {locator.file_id ? <div className="pdf-canvas-wrap"><canvas ref={canvasRef} />{highlight ? <span className="pdf-highlight" style={highlight} /> : null}</div> : null}
          <aside><blockquote>{locator.quotation || "Verbatim quotation unavailable"}</blockquote><dl><div><dt>Page</dt><dd>{locator.page_number ?? "Unavailable"}</dd></div><div><dt>Element</dt><dd>{locator.element_type}</dd></div><div><dt>Parser</dt><dd>{locator.parser_name} {locator.parser_version}</dd></div><div><dt>Extraction</dt><dd>{locator.extraction_type}</dd></div>{locator.derivation ? <div><dt>Derivation</dt><dd>{locator.derivation}</dd></div> : null}</dl>{error ? <p className="form-error" role="alert">{error}</p> : null}</aside>
        </div>
      </section>
    </div>
  );
}
