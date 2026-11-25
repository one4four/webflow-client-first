# Per-project Webflow connection (Claude Code)

The claude.ai Webflow connector signs in to one workspace at a time, and that sign-in is shared by every project. To give one project its own Webflow access (Data and Designer tools) without touching that connector, add a project-scoped copy of Webflow's hosted MCP server in Claude Code, with its own sign-in.

Use this when a new Webflow build or client site needs Claude to read or build in the Designer, or when the claude.ai connector is already in use for another workspace or client.

Setup takes about 10 minutes per project. It contains no secrets: the sign-in is OAuth and is stored locally by Claude Code, never in the repo.

**Fast path:** in a copy of this starter repo, run `scripts/new-project.sh`. It does steps 1 and 2 (writes `.mcp.json` and `PROJECT.md`), then continue at step 3. The manual steps below are the same thing by hand.

## 1. Pick a local project folder

One folder per project on the Mac, for example:

```
~/Desktop/One4Four, LLC/<Client>/<Project> - Claude Folder
```

## 2. Add the server, scoped to that folder

Give the server a unique name, `webflow-<project>` (for example `webflow-opd`), so it never collides with the claude.ai connector or another project.

Either run this from inside the folder (`-s project` writes it to that folder's `.mcp.json` instead of the global Claude Code config):

```bash
claude mcp add --transport http webflow-<project> https://mcp.webflow.com/mcp -s project
```

Or create `.mcp.json` in the folder by hand:

```json
{
  "mcpServers": {
    "webflow-<project>": {
      "type": "http",
      "url": "https://mcp.webflow.com/mcp"
    }
  }
}
```

- Workspaces hosted in the EU use `https://mcp.eu.webflow.com/mcp` instead.
- Use Webflow's hosted server only. Don't use the archived local, token-based server: it can't use Designer tools without a custom Bridge App.
- `.mcp.json` holds no credentials, so it is safe to keep in the folder.

## 3. Start Claude Code in that folder

`cd` into the folder (drag it from Finder into Terminal), then run `claude`. Starting from the home folder won't load the server.

## 4. Approve the server

At "New MCP server found", choose **Use this MCP server**. Decline the Chrome browser-tools prompt unless the project needs it.

## 5. Sign in

Type `/mcp`, pick `webflow-<project>`, and choose **Authenticate**. Webflow's OAuth screen opens in the browser. Tick **only this project's site**. Authorizing also installs the MCP Bridge App on that site.

This sign-in belongs to this folder only. It is separate from the claude.ai connector and from every other project folder.

## 6. Claude Code login

If Claude Code asks how to log in, choose **Claude account with subscription**.

## 7. Designer access

Open the site in the Webflow Designer, press **E** to open the Apps panel, and launch the **MCP Bridge App**. Leave it open while Claude builds. Designer tools fail when it is closed.

## 8. Test

Confirm all four before building:

1. The server sees only this site (ask Claude to list the sites it can reach).
2. A Data read works (list pages).
3. A Designer read works (current page, breakpoints).
4. A reversible Designer write works (rename an element, then restore it).

## Running work

- Designer work runs as a Remote Control session on the Mac in that folder. Keep the Mac awake, the Claude app open, and the Designer tab with the Bridge App open. Terminal is only needed for the one-time sign-in.
- Cloud threads can't reach this connection. Write the Designer spec in the cloud thread and send it to the Mac session.

## Optional: site API token for scripts

Only for server-side scripts, never for Designer work.

1. In Webflow: Site settings > Apps & integrations > API access > generate a site token with the scopes the script needs.
2. Store it in Supabase Vault through the dashboard: Integrations > Vault > Add new secret, named `webflow_<project>_token`.
3. Don't add it through the SQL editor, which keeps query history.
4. Never paste a token in chat, a doc, a commit or `.mcp.json`.

Tokens can't build in the Designer, and can't delete pages or components.

## CI exports (GitHub Actions)

A token in Supabase Vault is only readable from inside Supabase. GitHub Actions can't see it, so a workflow that calls Webflow (for example a DevLink component export) needs its own copy:

1. In the project's GitHub repo: Settings > Secrets and variables > Actions > New repository secret.
2. Name it `WEBFLOW_API_TOKEN` and paste the site token (same scopes as above, plus whatever the export needs).
3. Reference it in the workflow as `${{ secrets.WEBFLOW_API_TOKEN }}`. Never echo it in a step.
4. Record the secret's name (not its value) in `PROJECT.md`.

Learned on the OPD build (2026-11-24): the token was in Supabase Vault, and the DevLink export workflow still needed it added as an Actions secret.

## Known limits

- The API can't delete pages or components, and Home, 404 and Password pages can only be emptied. Do these in the Designer.
- New variables and some component variants need Designer clicks. Claude gives a short click list.
- The element snapshot tool has returned format errors, so check visuals in the Designer.
- Every build still follows this repo: `CLAUDE.md` first, then `README.md` (§19 before any MCP/API build).

## Sources

- Webflow, [Claude Code installation](https://developers.webflow.com/mcp/installing/claude-code) (hosted URL, `-s project` per-folder setup, OAuth flow). Checked 2026-11-24.
- Webflow, [MCP getting started](https://developers.webflow.com/mcp/reference/getting-started) (EU URL, Bridge App installs during OAuth). Checked 2026-11-24.
