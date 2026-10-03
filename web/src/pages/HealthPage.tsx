import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";

export function HealthPage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => unwrap(await api.GET("/api/health")),
    refetchInterval: 15_000,
  });

  if (health.isPending) return <p role="status">Checking…</p>;
  if (health.isError) {
    return (
      <section aria-labelledby="health-title">
        <h1 id="health-title">Memoir</h1>
        <p role="alert">{health.error.message}</p>
      </section>
    );
  }
  const { status, database, worker, version } = health.data;
  return (
    <section aria-labelledby="health-title">
      <h1 id="health-title">Memoir</h1>
      <dl>
        <dt>Overall</dt>
        <dd>{status}</dd>
        <dt>Database</dt>
        <dd>{database}</dd>
        <dt>Worker</dt>
        <dd>{worker.status}</dd>
        <dt>Version</dt>
        <dd>{version}</dd>
      </dl>
    </section>
  );
}
