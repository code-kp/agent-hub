import React, { useEffect, useRef, useState } from "react";
import { formatTime, toDateTimeAttr } from "../lib/time";

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

function getEventHeading(event) {
  if (!event) {
    return "Working through the request";
  }
  return event.label || prettyType(event.type) || "Working through the request";
}

function getEventSummary(event) {
  if (!event) {
    return "";
  }
  return summarizeBody(event.detail || event.body || "");
}

export function ExecutionSteps({ events, active }) {
  const [expanded, setExpanded] = useState(false);
  const [isSettling, setIsSettling] = useState(false);
  const [isCollapsing, setIsCollapsing] = useState(false);
  const listRef = useRef(null);
  const collapseStartTimeoutRef = useRef(null);
  const collapseEndTimeoutRef = useRef(null);
  const previousActiveRef = useRef(active);
  const previousEventCountRef = useRef(events.length);
  const latestEvent = events[events.length - 1] || null;
  const recentEvents = events.slice(-4);
  const visibleEvents = expanded ? events : recentEvents;
  const hiddenCount = Math.max(events.length - recentEvents.length, 0);
  const backgroundEvents = events.slice(0, -1);
  const visibleBackgroundEvents = backgroundEvents.slice(-6);
  const hiddenBackgroundCount = Math.max(backgroundEvents.length - visibleBackgroundEvents.length, 0);
  const latestSummary = getEventSummary(latestEvent);
  const showPanel = active || expanded || isSettling || isCollapsing;
  const showFocusedLayout = active || isSettling || isCollapsing;
  const showCollapsedSummary = !active && !expanded && !isSettling && !isCollapsing && events.length > 0;
  const currentHeading = latestEvent
    ? getEventHeading(latestEvent)
    : active
      ? "Starting request"
      : "Execution complete";
  const currentSummary = latestEvent
    ? latestSummary || (active ? "Waiting for the next progress update." : "Response completed.")
    : active
      ? "Connecting to the selected agent and waiting for the first progress update."
      : "Response completed.";

  const clearCollapseTimers = () => {
    window.clearTimeout(collapseStartTimeoutRef.current);
    window.clearTimeout(collapseEndTimeoutRef.current);
  };

  const beginCollapseAnimation = () => {
    setIsSettling(false);
    setIsCollapsing(true);
    collapseEndTimeoutRef.current = window.setTimeout(() => {
      setIsCollapsing(false);
    }, 420);
  };

  const scheduleCollapse = (delay = 0) => {
    clearCollapseTimers();
    setExpanded(false);

    if (delay > 0) {
      setIsSettling(true);
      collapseStartTimeoutRef.current = window.setTimeout(() => {
        beginCollapseAnimation();
      }, delay);
      return;
    }

    setIsSettling(false);
    beginCollapseAnimation();
  };

  useEffect(() => {
    if (latestEvent?.state === "error" || latestEvent?.type === "error") {
      clearCollapseTimers();
      setIsSettling(false);
      setIsCollapsing(false);
      setExpanded(true);
    }
  }, [latestEvent]);

  useEffect(() => {
    if (!showPanel || !listRef.current) {
      previousEventCountRef.current = events.length;
      return;
    }

    const behavior = active && previousEventCountRef.current > 0 ? "smooth" : "auto";
    listRef.current.scrollTo({
      top: listRef.current.scrollHeight,
      behavior,
    });
    previousEventCountRef.current = events.length;
  }, [active, events.length, showPanel]);

  useEffect(() => {
    if (active) {
      clearCollapseTimers();
      setIsSettling(false);
      setIsCollapsing(false);
    } else if (previousActiveRef.current && !expanded) {
      scheduleCollapse(events.length ? 760 : 0);
    }

    previousActiveRef.current = active;
  }, [active, events.length, expanded]);

  useEffect(() => () => {
    clearCollapseTimers();
  }, []);

  if (!events.length && !active) {
    return null;
  }

  const onToggleExpanded = () => {
    if (expanded) {
      scheduleCollapse(0);
      return;
    }

    clearCollapseTimers();
    setIsSettling(false);
    setIsCollapsing(false);
    setExpanded(true);
  };

  return (
    <section
      className={[
        "execution-steps",
        active ? "live" : "",
        expanded ? "expanded" : "",
        isSettling ? "settling" : "",
        isCollapsing ? "collapsing" : "",
        showCollapsedSummary ? "collapsed" : "",
      ].filter(Boolean).join(" ")}
    >
      <div className={showFocusedLayout ? "execution-panel live" : "execution-panel"}>
        <header className="execution-header">
          <div className="execution-status">
            <span className={active ? "execution-badge live" : "execution-badge"}>
              {showFocusedLayout
                ? active
                  ? "Running in background"
                  : "Execution complete"
                : "Execution steps"}
            </span>
            {!showFocusedLayout ? (
              <div className="execution-summary">
                <strong>{events.length} steps captured</strong>
                <span>{latestSummary || "Response completed."}</span>
              </div>
            ) : null}
          </div>
          {!showFocusedLayout ? (
            <button
              type="button"
              className="execution-toggle"
              onClick={onToggleExpanded}
              aria-expanded={expanded}
            >
              {expanded ? "Hide" : `Show all ${events.length}`}
            </button>
          ) : (
            <span className={active ? "execution-live-pill" : "execution-live-pill done"}>
              {active ? "Live" : "Done"}
            </span>
          )}
        </header>

        {showFocusedLayout ? (
          <>
            <section className={active ? "execution-current live" : "execution-current"}>
              <div
                key={latestEvent?.id || (active ? "pending" : "complete")}
                className="execution-current-body"
              >
                <div className="execution-current-topline">
                  <span className="execution-current-kicker">
                    <span className="execution-current-indicator" aria-hidden="true" />
                    {active ? "Current activity" : "Latest activity"}
                  </span>
                  <time dateTime={toDateTimeAttr(latestEvent?.timestamp)}>
                    {formatTime(latestEvent?.timestamp, { withSeconds: true })}
                  </time>
                </div>
                <strong>{currentHeading}</strong>
                <p>{currentSummary}</p>
              </div>
            </section>

            {visibleBackgroundEvents.length ? (
              <div className="execution-history">
                <div className="execution-history-header">
                  <span>Recent updates</span>
                  {hiddenBackgroundCount > 0 ? (
                    <span>{hiddenBackgroundCount} earlier</span>
                  ) : null}
                </div>

                <ol className="execution-list live" ref={listRef}>
                  {visibleBackgroundEvents.map((event, index) => {
                    const absoluteIndex = backgroundEvents.length - visibleBackgroundEvents.length + index;
                    const isLatest = absoluteIndex === backgroundEvents.length - 1;
                    const isError = event.state === "error" || event.type === "error";
                    const preview = getEventSummary(event);

                    return (
                      <li
                        key={event.id}
                        className={[
                          "execution-item",
                          isLatest ? "latest" : "",
                          isError ? "error" : "",
                        ].filter(Boolean).join(" ")}
                      >
                        <div className="execution-rail" aria-hidden="true">
                          <span className="execution-node" />
                          {absoluteIndex < backgroundEvents.length - 1 ? <span className="execution-line" /> : null}
                        </div>
                        <div className="execution-step">
                          <div className="execution-step-header">
                            <strong>{getEventHeading(event)}</strong>
                            <time dateTime={toDateTimeAttr(event.timestamp)}>
                              {formatTime(event.timestamp, { withSeconds: true })}
                            </time>
                          </div>
                          {preview ? <p className="execution-preview">{preview}</p> : null}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </div>
            ) : null}
          </>
        ) : (
          <ol
            className="execution-list"
            ref={listRef}
          >
            {visibleEvents.map((event, index) => {
              const absoluteIndex = expanded ? index : events.length - visibleEvents.length + index;
              const isLatest = absoluteIndex === events.length - 1;
              const isError = event.state === "error" || event.type === "error";
              const preview = getEventSummary(event);

              return (
                <li
                  key={event.id}
                  className={[
                    "execution-item",
                    isLatest ? "latest" : "",
                    isError ? "error" : "",
                  ].filter(Boolean).join(" ")}
                >
                  <div className="execution-rail" aria-hidden="true">
                    <span className="execution-node" />
                    {absoluteIndex < events.length - 1 ? <span className="execution-line" /> : null}
                  </div>
                  <div className="execution-step">
                    <div className="execution-step-header">
                      <strong>{getEventHeading(event)}</strong>
                      <time dateTime={toDateTimeAttr(event.timestamp)}>
                        {formatTime(event.timestamp, { withSeconds: true })}
                      </time>
                    </div>
                    {preview ? <p className="execution-preview">{preview}</p> : null}
                    {expanded ? <div className="execution-detail">{event.body}</div> : null}
                  </div>
                </li>
              );
            })}
          </ol>
        )}

        {!showActiveLayout && !expanded && hiddenCount > 0 ? (
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
