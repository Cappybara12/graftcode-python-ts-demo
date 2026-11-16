# Submitting to awesome-mcp-servers

Target: [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
(~98k stars, the largest MCP list). Its rules: a public GitHub repo you install and run
yourself, one line per server, alphabetical order within a category, follow the existing format.

Every entry in the list carries a **Glama score badge**, so get the repo indexed on Glama first.

## 1. Get indexed on Glama (do this first)

1. Sign in at https://glama.ai/mcp/servers with GitHub.
2. Use **Add server** and give it `https://github.com/Cappybara12/graftcode-python-ts-demo`.
3. Glama reads the README, license and tools. The repo already has an MIT license and an
   "Use it from Claude or Cursor (MCP)" section. Wait until the server page exists:
   `https://glama.ai/mcp/servers/Cappybara12/graftcode-python-ts-demo`.

## 2. The line to add

Category: **🎯 Marketing** ("Tools for creating and editing marketing content…"). Insert it in
alphabetical order by repo owner/name (between the `C…` entries).

```markdown
- [Cappybara12/graftcode-python-ts-demo](https://github.com/Cappybara12/graftcode-python-ts-demo) [![Cappybara12/graftcode-python-ts-demo MCP server](https://glama.ai/mcp/servers/Cappybara12/graftcode-python-ts-demo/badges/score.svg)](https://glama.ai/mcp/servers/Cappybara12/graftcode-python-ts-demo) 🐍 🏠 🍎 🐧 - Editorial content pipeline as MCP tools: pick on-brand topics from a trend queue, write and style-check SEO drafts, find related published posts, and stage GitHub PRs. A plain Python class served by Graftcode Gateway, with optional Superlinked SIE semantic search.
```

Legend used: 🐍 Python codebase, 🏠 local service, 🍎 macOS, 🐧 Linux (the gateway also ships for
Linux; add 🪟 only after testing on Windows).

## 3. Open the pull request

```bash
gh repo fork punkpeye/awesome-mcp-servers --clone && cd awesome-mcp-servers
git checkout -b add-graftcode-content-pipeline
# edit README.md: add the line above in the Marketing section, alphabetical order
git commit -am "Add Cappybara12/graftcode-python-ts-demo"
git push -u origin add-graftcode-content-pipeline
gh pr create --title "Add Cappybara12/graftcode-python-ts-demo" --body "Adds an editorial content pipeline MCP server (Python, local) to Marketing. Public repo, MIT, Glama-indexed."
```

## Other lists and directories worth the same entry

| Where | How |
|---|---|
| [appcypher/awesome-mcp-servers](https://github.com/appcypher/awesome-mcp-servers) (~5.8k ★) | PR, same line without the Glama badge |
| [wong2/awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) (~4.4k ★) | Submits through its website form (see the repo README) |
| [mcp.so](https://mcp.so) | "Submit" on the site |
| [Smithery](https://smithery.ai) | Needs a `smithery.yaml`; optional |
| [Graftcode examples](https://github.com/grft-dev/graftcode/blob/main/examples/README.md) | See `graftcode/examples-pr.md` |
