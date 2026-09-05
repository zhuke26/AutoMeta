export interface FigureFile {
  file_id: string;
  filename: string;
  mime_type: string;
}


function figureUrl(reviewId: string, fileId: string) {
  return `/api/v1/reviews/${encodeURIComponent(reviewId)}/figures/${encodeURIComponent(fileId)}/content`;
}


function formatLabel(mimeType: string) {
  if (mimeType === "image/svg+xml") return "SVG";
  if (mimeType === "image/png") return "PNG";
  if (mimeType === "application/pdf") return "PDF";
  return "File";
}


export function ForestPlotPanel({
  figures,
  outcomeName,
  reviewId,
}: {
  figures: FigureFile[];
  outcomeName: string;
  reviewId: string;
}) {
  const preview = figures.find((figure) => figure.mime_type === "image/svg+xml");
  return (
    <section aria-label={`${outcomeName} forest plot files`} className="forest-plot-panel">
      <header className="forest-plot-panel__header">
        <div><p className="eyebrow">Generated figure</p><h3>Forest plot</h3></div>
        {figures.length ? <nav aria-label="Forest plot downloads" className="forest-plot-downloads">
          {figures.map((figure) => <a
            className="button"
            download={figure.filename}
            href={figureUrl(reviewId, figure.file_id)}
            key={figure.file_id}
          >Download {formatLabel(figure.mime_type)}</a>)}
        </nav> : null}
      </header>
      {preview
        ? <img
            alt={`${outcomeName} forest plot`}
            className="forest-plot-preview"
            loading="lazy"
            src={figureUrl(reviewId, preview.file_id)}
          />
        : <p className="empty-state">Forest plot unavailable for this result.</p>}
    </section>
  );
}
