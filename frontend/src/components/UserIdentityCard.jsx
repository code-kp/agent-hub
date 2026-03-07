import React from "react";

export function UserIdentityCard({
  userId,
  onUserIdChange,
}) {
  const [draftUserId, setDraftUserId] = React.useState(userId);
  const [status, setStatus] = React.useState("");
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    setDraftUserId(userId);
    setError("");
  }, [userId]);

  const onSubmit = (event) => {
    event.preventDefault();
    const nextValue = String(draftUserId || "").trim();
    if (!nextValue) {
      setError("User ID is required.");
      setStatus("");
      return;
    }

    onUserIdChange(nextValue);
    setError("");
    setStatus("Saved. Chats and uploaded knowledge now use this user ID.");
  };

  return (
    <section className="settings-card">
      <div className="settings-card-header">
        <div>
          <h3>User identity</h3>
          <p>Chats and uploaded knowledge are scoped to this user ID across all agents.</p>
        </div>
        <span className="settings-chip">{userId}</span>
      </div>

      <form className="identity-form" onSubmit={onSubmit}>
        <label className="knowledge-upload-field">
          <span>User ID</span>
          <input
            type="text"
            value={draftUserId}
            placeholder="browser-user"
            onChange={(event) => {
              setDraftUserId(event.target.value);
              setError("");
              setStatus("");
            }}
          />
          <small>Use the same value for chat and uploads if you want that knowledge available in conversations.</small>
        </label>

        <div className="knowledge-upload-actions">
          <div className="knowledge-upload-status" aria-live="polite">
            {error ? <span className="knowledge-upload-error">{error}</span> : null}
            {!error && status ? <span>{status}</span> : null}
            {!error && !status ? <span>Uploaded markdown is visible only to this user ID, across all agents.</span> : null}
          </div>
          <button type="submit" className="sidebar-action">
            Save user ID
          </button>
        </div>
      </form>
    </section>
  );
}
