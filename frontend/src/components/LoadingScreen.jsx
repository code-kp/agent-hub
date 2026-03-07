import React from "react";

export function LoadingScreen({
  isLoading = true,
  isRetrying = false,
  error = "",
  healthState = "checking",
  healthMessage = "",
  onRetry,
}) {
  const showServiceHint = healthState === "down" || Boolean(error) || isRetrying;
  const subtleMessage = isRetrying
    ? "Retrying connection to the agent service."
    : error
      || healthMessage
    || "Agent service might be down or still starting.";

  return (
    <main className="app-shell loading-state">
      <section className="loading-card card-shell">
        <span className="section-kicker">Initializing</span>
        <h1>Preparing the agent workspace</h1>
        <p>Loading available agents, namespaces, and the current conversation shell.</p>

        {showServiceHint ? (
          <div className="loading-inline-status" aria-live="polite">
            <div className="loading-inline-copy">
              <span className="loading-inline-dot" aria-hidden="true" />
              <span>{subtleMessage}</span>
            </div>
            {onRetry ? (
              <button
                type="button"
                className={isRetrying ? "loading-retry-button retrying" : "loading-retry-button"}
                onClick={onRetry}
                aria-label="Reload agent workspace"
                title={isRetrying ? "Retrying" : "Reload"}
                disabled={isRetrying}
              >
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path
                    d="M13.5 8A5.5 5.5 0 1 1 12 4.2"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.4"
                  />
                  <path
                    d="M12 1.8v2.9H9.1"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.4"
                  />
                </svg>
              </button>
            ) : null}
          </div>
        ) : null}

        {isLoading && !showServiceHint ? (
          <div className="loading-inline-status neutral" aria-live="polite">
            <div className="loading-inline-copy">
              <span className="loading-inline-dot loading" aria-hidden="true" />
              <span>Connecting to the agent service.</span>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}
