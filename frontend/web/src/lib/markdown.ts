// ==========================================================================
// Markdown to HTML — minimal, no dependencies
// Ported verbatim from legacy src/markdown.js
// ==========================================================================

function tableRowCells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

// Convert pipe tables (header row + |---| separator + body rows) into HTML.
// Each table becomes a single line so the paragraph pass leaves it alone.
function renderTables(text: string): string {
  const lines = text.split("\n");
  const isRow = (l: string | undefined) => !!l && /^\s*\|.+\|\s*$/.test(l);
  const isSeparator = (l: string | undefined) =>
    !!l && /^\s*\|(\s*:?-{3,}:?\s*\|)+\s*$/.test(l);

  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    if (isRow(lines[i]) && isSeparator(lines[i + 1])) {
      const headers = tableRowCells(lines[i]);
      i += 2;
      const rows: string[][] = [];
      while (isRow(lines[i]) && !isSeparator(lines[i])) {
        rows.push(tableRowCells(lines[i]));
        i += 1;
      }
      const thead = `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>`;
      const tbody = rows.length
        ? `<tbody>${rows
            .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
            .join("")}</tbody>`
        : "";
      out.push(`<div class="table-wrap"><table>${thead}${tbody}</table></div>`);
    } else {
      out.push(lines[i]);
      i += 1;
    }
  }
  return out.join("\n");
}

export function markdownToHtml(md: string): string {
  let html = md
    // Headers
    .replace(/^##### (.+)$/gm, "<h5>$1</h5>")
    .replace(/^#### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    // Horizontal rules
    .replace(/^---$/gm, "<hr>")
    .replace(/^\*\*\*$/gm, "<hr>")
    // Bold and italic
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Inline source citations [filename.pdf] → colored span
    .replace(/(\[[^\]]+?\.\w{2,4}\])/g, '<span class="source-cite">$1</span>')
    // Blockquotes
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    // Unordered lists
    .replace(/^[\-\*] (.+)$/gm, "<li>$1</li>")
    // Ordered lists
    .replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

  // Pipe tables → <table>
  html = renderTables(html);

  // Paragraphs: wrap lines that aren't already wrapped in tags
  html = html
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return "";
      if (/^<(h[1-5]|ul|ol|li|hr|blockquote|p|div|table)/.test(trimmed)) return trimmed;
      return `<p>${trimmed}</p>`;
    })
    .join("\n");

  // Clean up empty paragraphs
  html = html.replace(/<p><\/p>/g, "");

  return html;
}
