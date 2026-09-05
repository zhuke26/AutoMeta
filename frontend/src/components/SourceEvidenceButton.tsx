import type { SourceLocator } from "../api/types";


export function SourceEvidenceButton({
  citation,
  source,
  onOpen,
}: {
  citation: string;
  source?: SourceLocator;
  onOpen: (source: SourceLocator) => void;
}) {
  if (!citation) return null;
  const locator = source ?? {
    element_type: "unknown" as const,
    parser_name: "unknown",
    parser_version: "",
    extraction_type: "direct" as const,
    derivation: "",
    quotation: citation,
  };
  return <button className="button button--quiet evidence-button" onClick={() => onOpen(locator)} type="button">View source</button>;
}
