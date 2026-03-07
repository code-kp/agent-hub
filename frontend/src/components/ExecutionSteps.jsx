import React, { useEffect, useRef, useState } from "react";

function formatTime(value) {
  if (!value) {
    return "";
  }
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function prettyType(type) {
  return (type || "event")
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function summarizeBody(body) {
  if (!body) {
    return "";
  }

  return body
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 160);
}

export function ExecutionSteps({ events, active }) {
  const [expanded, setExpanded] = useState(false);
  const [isCollapsing, setIsCollapsing] = useState(false);
  const listRef = useRef(null);
  const collapseTimeoutRef = useRef(null);
  const previousActiveRef = useRef(active);
  const latestEvent = events[events.length - 1] || null;
  const liveEvents = events.slice(-4);
  const visibleEvents = expanded ? events : liveEvents;
  const hiddenCount = Math.max(events.length - liveEvents.length, 0);
  const latestSummary = summarizeBody(latestEvent?.body);
  const showPanel = active || expanded || isCollapsing;
  const showCollapsedSummary = !active && !expanded && !isCollapsing;

  const startCollapse = () => {
    window.clearTimeout(collapseTimeoutRef.current);
    setExpanded(false);
    setIsCollapsing(true);
    collapseTimeoutRef.current = window.setTimeout(() => {
      setIsCollapsing(false);
    }, 420);
  };

  useEffect(() => {
    if (latestEvent?.type === "error") {
      window.clearTimeout(collapseTimeoutRef.current);
      setIsCollapsing(false);
      setExpanded(true);
    }
  }, [latestEvent]);

  useEffect(() => {
    if (!showPanel || !listRef.current) {
      return;
    }
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [events, showPanel]);

  useEffect(() => {
    if (active) {
      window.clearTimeout(collapseTimeoutRef.current);
      setIsCollapsing(false);
    } else if (previousActiveRef.current && events.length && !expanded) {
      startCollapse();
    }

    previousActiveRef.current = active;
  }, [active, events.length, expanded]);

  useEffect(() => () => {
    window.clearTimeout(collapseTimeoutRef.current);
  }, []);

  if (!events.length) {
    return null;
  }

  const onToggleExpanded = () => {
    if (expanded) {
      startCollapse();
      return;
    }

    window.clearTimeout(collapseTimeoutRef.current);
    setIsCollapsing(false);
    setExpanded(true);
  };

  return (
    <section
      className={[
        "execution-steps",
        active ? "live" : "",
        expanded ? "expanded" : "",
        isCollapsing ? "collapsing" : "",
        showCollapsedSummary ? "collapsed" : "",
      ].filter(Boolean).join(" ")}
    >
      <div className="execution-panel">
        <header className="execution-header">
          <div className="execution-status">
            <span className={active ? "execution-badge live" : "execution-badge"}>
              {active ? "Executing" : "Execution steps"}
            </span>
            <div className="execution-summary">
              <strong>{active ? prettyType(latestEvent?.type) || "Preparing" : `${events.length} steps captured`}</strong>
              <span>
                {active
                  ? latestSummary || "Waiting for the next progress update."
                  : latestSummary || "Response completed."}
              </span>
            </div>
          </div>
          {!active ? (
            <button
              type="button"
              className="execution-toggle"
              onClick={onToggleExpanded}
              aria-expanded={expanded}
            >
              {expanded ? "Hide" : `Show all ${events.length}`}
            </button>
          ) : (
            <span className="execution-live-pill">Live</span>
          )}
        </header>

        <ol className="execution-list" ref={listRef}>
          {visibleEvents.map((event, index) => {
            const absoluteIndex = expanded ? index : events.length - visibleEvents.length + index;
            const isLatest = absoluteIndex === events.length - 1;
            const isError = event.type === "error";
            const preview = summarizeBody(event.body);

            return (
              <li
                key={event.id}
                className={[
                  "execution-item",
                  isLatest ? "latest" : "",
                  isError ? "error" : "",
                  active && isLatest ? "live" : "",
                ].filter(Boolean).join(" ")}
              >
                <div className="execution-rail" aria-hidden="true">
                  <span className="execution-node" />
                  {absoluteIndex < events.length - 1 ? <span className="execution-line" /> : null}
                </div>
                <div className="execution-step">
                  <div className="execution-step-header">
                    <strong>{prettyType(event.type)}</strong>
                    <time dateTime={event.timestamp ? new Date(event.timestamp).toISOString() : undefined}>
                      {formatTime(event.timestamp)}
                    </time>
                  </div>
                  {preview ? <p className="execution-preview">{preview}</p> : null}
                  {expanded ? <div className="execution-detail">{event.body}</div> : null}
                </div>
              </li>
            );
          })}
        </ol>

        {!active && !expanded && hiddenCount > 0 ? (
          <button
            type="button"
            className="execution-more"
            onClick={() => setExpanded(true)}
          >
            Show {hiddenCount} earlier step{hiddenCount === 1 ? "" : "s"}
          </button>
        ) : null}
      </div>

      {showCollapsedSummary ? (
        <button
          type="button"
          className="execution-collapsed"
          onClick={() => setExpanded(true)}
        >
          <span>Execution steps</span>
          <strong>{events.length}</strong>
          <span>View</span>
        </button>
      ) : null}
    </section>
  );
}
