import { useMemo, useState } from "react";


export interface SearchRecord {
  pmid: string;
  title: string;
  abstract?: string | null;
  authors?: string | null;
  year?: string | null;
  journal?: string | null;
  publication_type?: string | null;
}


export function RecordsTable({ papers }: { papers: SearchRecord[] }) {
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState("year-desc");
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const filtered = useMemo(() => {
    const needle = filter.trim().toLocaleLowerCase();
    const items = needle
      ? papers.filter((paper) => [paper.title, paper.pmid, paper.authors, paper.journal]
        .some((value) => String(value ?? "").toLocaleLowerCase().includes(needle)))
      : [...papers];
    items.sort((left, right) => {
      if (sort === "title") {
        return left.title.localeCompare(right.title);
      }
      const order = String(right.year ?? "").localeCompare(String(left.year ?? ""));
      return sort === "year-asc" ? -order : order;
    });
    return items;
  }, [filter, papers, sort]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  return (
    <div className="records-table-wrap">
      <div className="records-toolbar">
        <label className="sr-only" htmlFor="records-filter">Filter records</label>
        <input
          aria-label="Filter records"
          className="text-input"
          id="records-filter"
          onChange={(event) => { setFilter(event.target.value); setPage(1); }}
          placeholder="Filter title, PMID, author, or journal"
          type="search"
          value={filter}
        />
        <label>
          <span className="sr-only">Sort records</span>
          <select
            aria-label="Sort records"
            className="text-input"
            onChange={(event) => setSort(event.target.value)}
            value={sort}
          >
            <option value="year-desc">Newest year</option>
            <option value="year-asc">Oldest year</option>
            <option value="title">Title</option>
          </select>
        </label>
        <span>{filtered.length} records</span>
      </div>
      <div className="table-scroll">
        <table className="records-table">
          <thead>
            <tr><th>PMID</th><th>Title</th><th>Year</th><th>Journal</th><th>Authors</th><th>Type</th></tr>
          </thead>
          <tbody>
            {visible.map((paper) => (
              <tr key={paper.pmid}>
                <td><a href={`https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`} rel="noreferrer" target="_blank">{paper.pmid}</a></td>
                <td><strong>{paper.title}</strong>{paper.abstract ? <small>{paper.abstract}</small> : null}</td>
                <td>{paper.year || "—"}</td>
                <td>{paper.journal || "—"}</td>
                <td>{paper.authors || "—"}</td>
                <td>{paper.publication_type || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageCount > 1 ? (
        <div className="table-pagination">
          <button className="button" disabled={safePage === 1} onClick={() => setPage(safePage - 1)} type="button">Previous</button>
          <span>Page {safePage} of {pageCount}</span>
          <button className="button" disabled={safePage === pageCount} onClick={() => setPage(safePage + 1)} type="button">Next</button>
        </div>
      ) : null}
    </div>
  );
}
