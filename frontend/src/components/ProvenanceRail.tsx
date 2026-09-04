const artifacts = ["Query", "Records", "Sources", "Plan", "Code", "Result"] as const;


interface ProvenanceRailProps {
  completed?: ReadonlyArray<(typeof artifacts)[number]>;
}


export function ProvenanceRail({ completed = [] }: ProvenanceRailProps) {
  const completedSet = new Set(completed);
  return (
    <footer className="provenance-rail">
      <span className="provenance-rail__label">Evidence provenance</span>
      <ol>
        {artifacts.map((artifact) => (
          <li data-complete={completedSet.has(artifact)} key={artifact}>
            <span aria-hidden="true" className="provenance-rail__tick" />
            {artifact}
          </li>
        ))}
      </ol>
    </footer>
  );
}
