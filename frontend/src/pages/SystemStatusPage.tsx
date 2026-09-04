import { useSystemStatus } from "../api/system";
import { AppShell } from "../components/AppShell";


const loopbackHosts = new Set(["127.0.0.1", "::1", "localhost"]);


function label(value: string) {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}


export function SystemStatusPage() {
  const status = useSystemStatus();

  return (
    <AppShell>
      <main className="page-stack system-status-page">
        <header className="page-heading">
          <div>
            <p className="eyebrow">Local runtime</p>
            <h1>System status</h1>
            <p>Safe configuration details reported by the local AutoMeta server.</p>
          </div>
        </header>

        {status.isPending ? <section className="panel state-panel">Loading system status…</section> : null}
        {status.isError ? (
          <section className="panel state-panel state-panel--error">
            <h2>Could not load system status</h2>
            <p>{status.error.message}</p>
          </section>
        ) : null}
        {status.isSuccess ? (
          <>
            {!loopbackHosts.has(status.data.host) ? (
              <p className="security-warning" role="alert">
                This server is reachable beyond localhost and has no authentication.
              </p>
            ) : null}
            <section aria-label="Runtime status" className="panel status-grid">
              <div>
                <span>Database</span>
                <strong className={`status-value status-value--${status.data.database}`}>
                  {label(status.data.database)}
                </strong>
              </div>
              <div>
                <span>Model provider</span>
                <strong>{status.data.provider_configured ? "Configured" : "Not configured"}</strong>
              </div>
              <div>
                <span>Server bind</span>
                <strong className="mono-value">{status.data.host}:{status.data.port}</strong>
              </div>
              <div>
                <span>Version</span>
                <strong className="mono-value">{status.data.version}</strong>
              </div>
            </section>

            <section className="panel status-section">
              <h2>Provider</h2>
              <dl className="status-definition-list">
                <div><dt>OpenAI-compatible endpoint</dt><dd>{status.data.provider_base_url || "Not set"}</dd></div>
                <div><dt>Credential state</dt><dd>{status.data.provider_configured ? "Configured in server environment" : "Not configured"}</dd></div>
              </dl>
              <p className="field-help">Credentials are never returned to the browser or stored in the Library.</p>
            </section>

            <section className="panel status-section">
              <h2>Models</h2>
              <table className="status-table">
                <thead><tr><th>Scope</th><th>Resolved model</th></tr></thead>
                <tbody>
                  {Object.entries(status.data.models).map(([scope, model]) => (
                    <tr key={scope}><td>{label(scope)}</td><td className="mono-value">{model || "Not set"}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="panel status-section">
              <h2>Local storage</h2>
              <p className="mono-value path-value">{status.data.data_directory}</p>
            </section>
          </>
        ) : null}
      </main>
    </AppShell>
  );
}
