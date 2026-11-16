# Pull requests for grft-dev/graftcode

Graftcode's core is closed-source (their CONTRIBUTING.md says so). They welcome PRs for
documentation, examples and integrations. Two outside PRs have been merged before. Both PRs
below go to https://github.com/grft-dev/graftcode and touch documentation only.

---

## PR 1: List this project in examples/README.md

`examples/README.md` currently lists two projects, both by the CEO. Add a third line:

```markdown
- **[graftcode-python-ts-demo](https://github.com/Cappybara12/graftcode-python-ts-demo)** — A Python content pipeline called from React and Node through a Graft and from Claude/Cursor through the Gateway's MCP endpoint (15+ tools, no MCP server code), with optional Superlinked SIE semantic search and a reproducible 1.4 → 1.5 Stable benchmark
```

Title: `docs(examples): add graftcode-python-ts-demo`

Body:
> Adds a community project to the examples list: a Python receiver (`ArticlePipelineService`)
> used from a React dashboard and a Node client through the generated Graft, and from Claude and
> Cursor through the Gateway's built-in `/mcp` endpoint. It includes a reproducible benchmark of
> Gateway 1.4.10 against 1.5.0 (`bench/`) that you're welcome to reuse.

---

## PR 2: Add CHANGELOG.md

Most gateway releases have no notes. v1.5.0 (Stable) says only "Graftcode Gateway v1.5.0", so
anyone landing on GitHub cannot see what Stable changed. `CHANGELOG.md` in this folder collects
every published note into Keep a Changelog format, with the Stable features from the
announcement, and marks versions with no published notes.

Title: `docs: add CHANGELOG.md for Graftcode Gateway releases`

Body:
> The gateway release pages carry little or no text (9 of 21 have none, including v1.5.0
> Stable), so this collects what has been published (release notes and the Stable
> announcement) into one Keep a Changelog file, with links to each release. Versions without
> published notes are marked so the team can fill them in. Happy to adjust the format, or to
> move it to graftcode-gateway if that's a better home.

## Commands

```bash
gh repo fork grft-dev/graftcode --clone && cd graftcode
git checkout -b docs/examples-and-changelog
cp /Users/akshay/graft/docs/contributions/graftcode/CHANGELOG.md CHANGELOG.md
# edit examples/README.md: add the line from PR 1
git add CHANGELOG.md examples/README.md
git commit -m "docs: add CHANGELOG.md and a community example"
git push -u origin docs/examples-and-changelog
gh pr create --repo grft-dev/graftcode --title "docs: add CHANGELOG.md and a community example" --body-file PR_BODY.md
```

Two small PRs are easier to merge than one; split them if Rafał prefers.
