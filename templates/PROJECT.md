# Project: {{PROJECT_NAME}}

This file holds everything specific to this one Webflow project. The rule files (`CLAUDE.md`, `README.md`, `SKILL.md`, `docs/`, `views/`) stay identical to the starter so they can be refreshed with `scripts/pull-standard.sh`. Put project notes here, never in those files.

Status: {{SETUP_STATUS}}

## Webflow
- Client: {{CLIENT_NAME}}
- Workspace: {{WEBFLOW_WORKSPACE}}
- Site name: {{WEBFLOW_SITE_NAME}}
- Site id: {{WEBFLOW_SITE_ID}}
- Staging URL: {{WEBFLOW_STAGING_URL}}
- Region: {{WEBFLOW_REGION}}
- MCP server name: `webflow-{{PROJECT_SLUG}}` (in `.mcp.json`, signed in to this site only)
- Local folder: {{LOCAL_FOLDER}}

## Brand
- Design system / brand guide: {{BRAND_LINK}}

## Connection test (from `docs/webflow-project-connection.md` step 8)
- [ ] Server sees only this site
- [ ] Data read works (list pages)
- [ ] Designer read works (current page, breakpoints)
- [ ] Reversible Designer write works (rename an element, then restore it)

## Secrets (names only, never values)
- Site API token, if scripts need one: Supabase Vault `webflow_{{PROJECT_SLUG_UNDERSCORE}}_token`
- CI exports, if any: GitHub Actions secret `WEBFLOW_API_TOKEN` on the repo that runs them

## Notes
