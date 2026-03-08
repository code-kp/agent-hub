import React from "react";

import { MarkdownContent } from "./MarkdownContent";

export function AnimatedMessageBody({
  text,
  streaming,
}) {
  return (
    <div
      className={[
        "message-body-shell",
        streaming ? "streaming" : "",
      ].filter(Boolean).join(" ")}
      data-streaming={streaming ? "true" : "false"}
    >
      {streaming ? (
        <div className="message-body message-body-live">
          {text}
        </div>
      ) : (
        <MarkdownContent text={text} />
      )}
      {streaming ? <span className="message-streaming-caret" aria-hidden="true" /> : null}
    </div>
  );
}
