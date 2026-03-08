import React from "react";

function formatCount(value) {
  return new Intl.NumberFormat().format(Number.isFinite(value) ? value : 0);
}

function formatAuthor(author) {
  if (!author) {
    return "Model call";
  }
  return author
    .replace(/[._]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function UsageMetric({ label, value, emphasized = false }) {
  return (
    <div className={emphasized ? "usage-metric usage-metric-emphasized" : "usage-metric"}>
      <span className="usage-metric-label">{label}</span>
      <strong className="usage-metric-value">{formatCount(value)}</strong>
    </div>
  );
}

export function TokenUsagePopover({ usage, streaming = false }) {
  const calls = Array.isArray(usage?.calls) ? usage.calls : [];
  const hasUsage = Boolean(usage && typeof usage === "object");
  const showBreakdown = calls.length > 1;
  const hasSecondaryMetrics = hasUsage && (
    (usage.tool_use_prompt_tokens || 0) > 0
    || (usage.thoughts_tokens || 0) > 0
    || (usage.cached_content_tokens || 0) > 0
  );

  return (
    <details className="token-usage">
      <summary
        className={hasUsage ? "token-usage-trigger" : "token-usage-trigger token-usage-trigger-muted"}
        aria-label="Show token usage"
      >
        <span aria-hidden="true">i</span>
      </summary>
      <div className="token-usage-popover">
        <div className="token-usage-header">
          <strong>Token usage</strong>
          {hasUsage ? <span>{formatCount(usage.call_count || calls.length)} model call(s)</span> : null}
        </div>
        {hasUsage ? (
          <>
            <div className="token-usage-grid">
              <UsageMetric label="Input" value={usage.input_tokens || 0} emphasized />
              <UsageMetric label="Output" value={usage.output_tokens || 0} emphasized />
              <UsageMetric label="Total" value={usage.total_tokens || 0} emphasized />
            </div>
            {hasSecondaryMetrics ? (
              <div className="token-usage-secondary">
                {(usage.tool_use_prompt_tokens || 0) > 0 ? (
                  <UsageMetric label="Tool prompt" value={usage.tool_use_prompt_tokens || 0} />
                ) : null}
                {(usage.thoughts_tokens || 0) > 0 ? (
                  <UsageMetric label="Thoughts" value={usage.thoughts_tokens || 0} />
                ) : null}
                {(usage.cached_content_tokens || 0) > 0 ? (
                  <UsageMetric label="Cached" value={usage.cached_content_tokens || 0} />
                ) : null}
              </div>
            ) : null}
            {showBreakdown ? (
              <div className="token-usage-breakdown">
                <div className="token-usage-breakdown-title">Per call</div>
                <div className="token-usage-call-list">
                  {calls.map((call, index) => (
                    <div className="token-usage-call" key={`${call.author || "call"}-${index}`}>
                      <div className="token-usage-call-head">
                        <strong>{formatAuthor(call.author)}</strong>
                        {call.model_version ? <span>{call.model_version}</span> : null}
                      </div>
                      <div className="token-usage-call-metrics">
                        <span>In {formatCount(call.input_tokens || 0)}</span>
                        <span>Out {formatCount(call.output_tokens || 0)}</span>
                        <span>Total {formatCount(call.total_tokens || 0)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </>
        ) : (
          <div className="token-usage-empty">
            {streaming
              ? "Token usage will appear once the response is complete."
              : "Token usage was not reported for this response."}
          </div>
        )}
      </div>
    </details>
  );
}
