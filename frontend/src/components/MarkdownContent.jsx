import React from "react";

function isBlank(line) {
  return !line.trim();
}

function isHeading(line) {
  return /^#{1,6}\s+/.test(line.trim());
}

function isHorizontalRule(line) {
  return /^\s{0,3}([-*_]\s*){3,}$/.test(line);
}

function isBlockquote(line) {
  return /^\s*>\s?/.test(line);
}

function isOrderedList(line) {
  return /^\s*\d+\.\s+/.test(line);
}

function isUnorderedList(line) {
  return /^\s*[-*+]\s+/.test(line);
}

function isFence(line) {
  return /^```/.test(line.trim());
}

function parseTableRow(line) {
  const trimmed = line.trim();
  const withoutLeading = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const withoutEdges = withoutLeading.endsWith("|")
    ? withoutLeading.slice(0, -1)
    : withoutLeading;

  return withoutEdges.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line) {
  const cells = parseTableRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, "")));
}

function isTableStart(lines, index) {
  if (index + 1 >= lines.length || !lines[index].includes("|")) {
    return false;
  }

  const headerCells = parseTableRow(lines[index]);
  const separatorCells = parseTableRow(lines[index + 1]);
  return (
    headerCells.length > 0
    && headerCells.length === separatorCells.length
    && isTableSeparator(lines[index + 1])
  );
}

function isSafeHref(href) {
  return /^(https?:\/\/|mailto:|\/)/i.test(href);
}

function pushTextNodes(target, text, keyPrefix) {
  const parts = text.split("\n");

  parts.forEach((part, index) => {
    if (part) {
      target.push(part);
    }

    if (index < parts.length - 1) {
      target.push(<br key={`${keyPrefix}-br-${index}`} />);
    }
  });
}

function parseInline(text, keyPrefix = "md") {
  const output = [];
  const tokenPattern = /(\[([^\]]+)\]\(([^)\s]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_)/;
  let remainder = text;
  let tokenIndex = 0;

  while (remainder) {
    const match = remainder.match(tokenPattern);

    if (!match || typeof match.index !== "number") {
      pushTextNodes(output, remainder, `${keyPrefix}-tail-${tokenIndex}`);
      break;
    }

    const start = match.index;
    const [token] = match;

    if (start > 0) {
      pushTextNodes(output, remainder.slice(0, start), `${keyPrefix}-text-${tokenIndex}`);
    }

    if (match[2] && match[3]) {
      const href = match[3];
      if (isSafeHref(href)) {
        output.push(
          <a
            key={`${keyPrefix}-link-${tokenIndex}`}
            href={href}
            target={href.startsWith("/") ? undefined : "_blank"}
            rel={href.startsWith("/") ? undefined : "noreferrer"}
          >
            {parseInline(match[2], `${keyPrefix}-link-label-${tokenIndex}`)}
          </a>,
        );
      } else {
        pushTextNodes(output, token, `${keyPrefix}-unsafe-link-${tokenIndex}`);
      }
    } else if (match[4]) {
      output.push(<code key={`${keyPrefix}-code-${tokenIndex}`}>{match[4]}</code>);
    } else if (match[5] || match[6]) {
      output.push(
        <strong key={`${keyPrefix}-strong-${tokenIndex}`}>
          {parseInline(match[5] || match[6], `${keyPrefix}-strong-inner-${tokenIndex}`)}
        </strong>,
      );
    } else if (match[7] || match[8]) {
      output.push(
        <em key={`${keyPrefix}-em-${tokenIndex}`}>
          {parseInline(match[7] || match[8], `${keyPrefix}-em-inner-${tokenIndex}`)}
        </em>,
      );
    }

    remainder = remainder.slice(start + token.length);
    tokenIndex += 1;
  }

  return output;
}

function parseTableAlignments(separatorCells) {
  return separatorCells.map((cell) => {
    const normalized = cell.replace(/\s+/g, "");

    if (normalized.startsWith(":") && normalized.endsWith(":")) {
      return "center";
    }
    if (normalized.endsWith(":")) {
      return "right";
    }
    if (normalized.startsWith(":")) {
      return "left";
    }
    return undefined;
  });
}

function renderBlocks(text, keyPrefix = "md") {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (isBlank(line)) {
      index += 1;
      continue;
    }

    if (isFence(line)) {
      const language = line.trim().slice(3).trim();
      const codeLines = [];
      index += 1;

      while (index < lines.length && !isFence(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }

      if (index < lines.length && isFence(lines[index])) {
        index += 1;
      }

      blocks.push(
        <pre key={`${keyPrefix}-codeblock-${blocks.length}`}>
          <code data-language={language || undefined}>
            {codeLines.join("\n")}
          </code>
        </pre>,
      );
      continue;
    }

    if (isTableStart(lines, index)) {
      const headerCells = parseTableRow(lines[index]);
      const alignments = parseTableAlignments(parseTableRow(lines[index + 1]));
      const bodyRows = [];
      index += 2;

      while (index < lines.length && lines[index].includes("|") && !isBlank(lines[index])) {
        const rowCells = parseTableRow(lines[index]);
        if (rowCells.length === headerCells.length) {
          bodyRows.push(rowCells);
        }
        index += 1;
      }

      blocks.push(
        <div className="markdown-table-wrap" key={`${keyPrefix}-table-${blocks.length}`}>
          <table>
            <thead>
              <tr>
                {headerCells.map((cell, cellIndex) => (
                  <th
                    key={`${keyPrefix}-table-head-${cellIndex}`}
                    style={alignments[cellIndex] ? { textAlign: alignments[cellIndex] } : undefined}
                  >
                    {parseInline(cell, `${keyPrefix}-table-head-${cellIndex}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((row, rowIndex) => (
                <tr key={`${keyPrefix}-table-row-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td
                      key={`${keyPrefix}-table-cell-${rowIndex}-${cellIndex}`}
                      style={alignments[cellIndex] ? { textAlign: alignments[cellIndex] } : undefined}
                    >
                      {parseInline(cell, `${keyPrefix}-table-cell-${rowIndex}-${cellIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (isHeading(line)) {
      const [, hashes, content] = line.trim().match(/^(#{1,6})\s+(.*)$/) || [];
      const level = hashes.length;
      const HeadingTag = `h${level}`;

      blocks.push(
        <HeadingTag key={`${keyPrefix}-heading-${blocks.length}`}>
          {parseInline(content, `${keyPrefix}-heading-${blocks.length}`)}
        </HeadingTag>,
      );
      index += 1;
      continue;
    }

    if (isHorizontalRule(line)) {
      blocks.push(<hr key={`${keyPrefix}-hr-${blocks.length}`} />);
      index += 1;
      continue;
    }

    if (isBlockquote(line)) {
      const quoteLines = [];

      while (index < lines.length && isBlockquote(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }

      blocks.push(
        <blockquote key={`${keyPrefix}-quote-${blocks.length}`}>
          {renderBlocks(quoteLines.join("\n"), `${keyPrefix}-quote-${blocks.length}`)}
        </blockquote>,
      );
      continue;
    }

    if (isOrderedList(line) || isUnorderedList(line)) {
      const ordered = isOrderedList(line);
      const listItems = [];
      const listPattern = ordered ? /^\s*\d+\.\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/;

      while (index < lines.length) {
        const match = lines[index].match(listPattern);
        if (!match) {
          break;
        }
        listItems.push(match[1]);
        index += 1;
      }

      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag key={`${keyPrefix}-list-${blocks.length}`}>
          {listItems.map((item, itemIndex) => (
            <li key={`${keyPrefix}-list-item-${itemIndex}`}>
              {parseInline(item, `${keyPrefix}-list-item-${itemIndex}`)}
            </li>
          ))}
        </ListTag>,
      );
      continue;
    }

    const paragraphLines = [line];
    index += 1;

    while (index < lines.length) {
      if (
        isBlank(lines[index])
        || isFence(lines[index])
        || isTableStart(lines, index)
        || isHeading(lines[index])
        || isHorizontalRule(lines[index])
        || isBlockquote(lines[index])
        || isOrderedList(lines[index])
        || isUnorderedList(lines[index])
      ) {
        break;
      }

      paragraphLines.push(lines[index]);
      index += 1;
    }

    blocks.push(
      <p key={`${keyPrefix}-paragraph-${blocks.length}`}>
        {parseInline(paragraphLines.join("\n"), `${keyPrefix}-paragraph-${blocks.length}`)}
      </p>,
    );
  }

  return blocks;
}

export function MarkdownContent({ text }) {
  return <div className="message-body">{renderBlocks(text || "")}</div>;
}
