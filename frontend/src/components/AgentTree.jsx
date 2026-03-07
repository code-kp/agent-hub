import React from "react";

function countAgents(nodes) {
  return nodes.reduce((count, node) => {
    if (node.type === "agent") {
      return count + 1;
    }

    return count + countAgents(node.children || []);
  }, 0);
}

function branchHasSelection(nodes, selectedAgentId) {
  return nodes.some((node) => {
    if (node.type === "agent") {
      return node.id === selectedAgentId;
    }

    return branchHasSelection(node.children || [], selectedAgentId);
  });
}

function AgentTreeNode({
  node,
  selectedAgentId,
  searchText,
  onSelectAgent,
}) {
  if (node.type === "agent") {
    return (
      <li className="tree-node agent-node">
        <button
          type="button"
          className={node.id === selectedAgentId ? "agent-button selected" : "agent-button"}
          onClick={() => onSelectAgent(node.id)}
        >
          <span className="agent-name">{node.name || node.id}</span>
          <span className="agent-id">{node.id}</span>
          {node.description ? <span className="agent-description">{node.description}</span> : null}
        </button>
      </li>
    );
  }

  const children = node.children || [];
  const shouldOpen = Boolean(searchText.trim()) || branchHasSelection(children, selectedAgentId);
  const childCount = countAgents(children);

  return (
    <li className="tree-node namespace-node">
      <details defaultOpen={shouldOpen}>
        <summary>
          <span>{node.name}</span>
          <em>{childCount}</em>
        </summary>
        <ul className="tree-list">
          {children.map((child) => (
            <AgentTreeNode
              key={child.type === "agent" ? child.id : `${node.name}.${child.name}`}
              node={child}
              selectedAgentId={selectedAgentId}
              searchText={searchText}
              onSelectAgent={onSelectAgent}
            />
          ))}
        </ul>
      </details>
    </li>
  );
}

export function AgentTree({
  tree,
  selectedAgentId,
  searchText,
  onSelectAgent,
}) {
  if (!tree.length) {
    return <div className="tree-empty">No namespaces or agents match the current search.</div>;
  }

  return (
    <ul className="tree-list" key={`${selectedAgentId}:${searchText.trim()}`}>
      {tree.map((node) => (
        <AgentTreeNode
          key={node.type === "agent" ? node.id : node.name}
          node={node}
          selectedAgentId={selectedAgentId}
          searchText={searchText}
          onSelectAgent={onSelectAgent}
        />
      ))}
    </ul>
  );
}
