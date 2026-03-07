import React from "react";

export function LoadingScreen() {
  return (
    <main className="app-shell loading-state">
      <section className="loading-card card-shell">
        <span className="section-kicker">Initializing</span>
        <h1>Preparing the agent workspace</h1>
        <p>Loading available agents, namespaces, and the current conversation shell.</p>
      </section>
    </main>
  );
}
