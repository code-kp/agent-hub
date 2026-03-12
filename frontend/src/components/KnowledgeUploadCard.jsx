import React from "react";

import { uploadSkillFile } from "../api/client";

function formatFileList(files) {
  if (!files.length) {
    return "No markdown files selected";
  }
  if (files.length === 1) {
    return files[0].name;
  }
  return `${files.length} markdown files selected`;
}

export function KnowledgeUploadCard({ userId }) {
  const fileInputRef = React.useRef(null);
  const [files, setFiles] = React.useState([]);
  const [skillType, setSkillType] = React.useState("knowledge");
  const [namespace, setNamespace] = React.useState("");
  const [isUploading, setIsUploading] = React.useState(false);
  const [statusText, setStatusText] = React.useState("");
  const [results, setResults] = React.useState([]);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    setFiles([]);
    setResults([]);
    setStatusText("");
    setError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [userId]);

  const onFilesChange = (event) => {
    const nextFiles = Array.from(event.target.files || []).filter((file) =>
      file.name.toLowerCase().endsWith(".md"),
    );
    setFiles(nextFiles);
    setError("");
    setResults([]);
    setStatusText("");
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    if (!files.length || isUploading) {
      return;
    }

    setIsUploading(true);
    setError("");
    setResults([]);

    const uploaded = [];
    let failures = 0;

    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        setStatusText(`Uploading ${index + 1} of ${files.length}: ${file.name}`);

        try {
          const payload = await uploadSkillFile({
            file,
            skillClass: skillType,
            namespace,
            userId,
          });
          uploaded.push({
            fileName: file.name,
            ok: true,
            skill: payload.skill,
          });
        } catch (uploadError) {
          failures += 1;
          uploaded.push({
            fileName: file.name,
            ok: false,
            message: uploadError.message || "Upload failed.",
          });
        }
      }
    } finally {
      setResults(uploaded);
      setStatusText(
        failures
          ? `Uploaded ${uploaded.length - failures} of ${uploaded.length} file(s).`
          : `Uploaded ${uploaded.length} file(s) to the user-scoped skill library.`,
      );
      setIsUploading(false);
      if (failures) {
        setError("One or more files could not be uploaded. Review the per-file results below.");
      } else if (uploaded.length) {
        setFiles([]);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      }
    }
  };

  return (
    <section className="settings-card knowledge-upload-card">
      <div className="settings-card-header">
        <div>
          <h3>Skill uploads</h3>
          <p>Upload markdown skills once and make them available to all agents for this user ID.</p>
        </div>
        <span className="settings-chip">{userId}</span>
      </div>

      <form className="knowledge-upload-form" onSubmit={onSubmit}>
        <div className="knowledge-upload-grid">
          <label className="knowledge-upload-field knowledge-upload-file">
            <span>Markdown files</span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,text/markdown"
              multiple
              disabled={isUploading}
              onChange={onFilesChange}
            />
            <strong>{formatFileList(files)}</strong>
            <small>Upload one or more markdown files to add user-scoped skills.</small>
          </label>

          <label className="knowledge-upload-field">
            <span>Skill type</span>
            <select
              value={skillType}
              disabled={isUploading}
              onChange={(event) => setSkillType(event.target.value)}
            >
              <option value="knowledge">Knowledge</option>
              <option value="behavior">Behavior</option>
            </select>
            <small>Choose whether this should be categorized as knowledge or behavior. Backend enforcement for uploaded behavior skills is not wired yet.</small>
          </label>

          <label className="knowledge-upload-field">
            <span>Namespace</span>
            <input
              type="text"
              placeholder="billing or docs/release-notes"
              value={namespace}
              disabled={isUploading}
              onChange={(event) => setNamespace(event.target.value)}
            />
            <small>Optional. Helps group uploaded skills under a stable path.</small>
          </label>
        </div>

        <div className="knowledge-upload-actions">
          <div className="knowledge-upload-status" aria-live="polite">
            {error ? <span className="knowledge-upload-error">{error}</span> : null}
            {!error && statusText ? <span>{statusText}</span> : null}
            {!error && !statusText ? <span>Uploaded skills are shared across all agents for user <strong>{userId}</strong>.</span> : null}
          </div>
          <button type="submit" className="sidebar-action knowledge-upload-submit" disabled={!files.length || isUploading}>
            {isUploading ? "Uploading..." : "Upload skills"}
          </button>
        </div>
      </form>

      {results.length ? (
        <div className="knowledge-upload-results">
          {results.map((result) => (
            <article
              key={`${result.fileName}-${result.ok ? result.skill?.id : result.message}`}
              className={result.ok ? "knowledge-upload-result success" : "knowledge-upload-result error"}
            >
              <div className="knowledge-upload-result-header">
                <strong>{result.fileName}</strong>
                <span>{result.ok ? "Uploaded" : "Failed"}</span>
              </div>
              {result.ok ? (
                <div className="knowledge-upload-result-body">
                  <p>{result.skill.title}</p>
                  <code>{result.skill.id}</code>
                  <small>{result.skill.source}</small>
                </div>
              ) : (
                <p>{result.message}</p>
              )}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
