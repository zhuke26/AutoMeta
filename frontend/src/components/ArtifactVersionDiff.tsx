import type { ArtifactDiffView, ArtifactVersionView } from "../api/types";


function value(value: unknown) {
  return value === undefined ? "—" : JSON.stringify(value);
}


export function ArtifactVersionDiff({
  versions,
  fromVersion,
  toVersion,
  onFromVersion,
  onToVersion,
  diff,
}: {
  versions: ArtifactVersionView[];
  fromVersion: number;
  toVersion: number;
  onFromVersion: (version: number) => void;
  onToVersion: (version: number) => void;
  diff?: ArtifactDiffView;
}) {
  return (
    <section className="panel provenance-diff">
      <header className="section-heading"><h2>Version diff</h2></header>
      <div className="diff-controls">
        <label>From version<select aria-label="From version" value={fromVersion} onChange={(event) => onFromVersion(Number(event.target.value))}>{versions.map((item) => <option key={item.version_id} value={item.version}>{item.version}</option>)}</select></label>
        <label>To version<select aria-label="To version" value={toVersion} onChange={(event) => onToVersion(Number(event.target.value))}>{versions.map((item) => <option key={item.version_id} value={item.version}>{item.version}</option>)}</select></label>
      </div>
      {diff?.changes.length ? (
        <table className="diff-table"><thead><tr><th>Change</th><th>Path</th><th>Before</th><th>After</th></tr></thead><tbody>{diff.changes.map((change) => <tr key={`${change.op}:${change.path}`}><td>{change.op}</td><td><code>{change.path}</code></td><td>{value(change.before)}</td><td>{value(change.after)}</td></tr>)}</tbody></table>
      ) : <p className="state-inline">Select two different versions to compare.</p>}
    </section>
  );
}
