# Issue Tracker — chad-polio-ingest

Issues for this repo live in **GitHub Issues** at `akhil-egov/chad-polio-ingest`.

## Usage

- Create: `gh issue create --repo akhil-egov/chad-polio-ingest`
- List: `gh issue list --repo akhil-egov/chad-polio-ingest`
- View: `gh issue view <number> --repo akhil-egov/chad-polio-ingest`
- Close: `gh issue close <number> --repo akhil-egov/chad-polio-ingest`

## Cross-repo issues

This repo and `akhil-egov/chad-polio-dashboard` are coupled via `CONTRACT.md`.
- Bugs that originate here (extraction logic, wrong ES query, missing field in output) → file here.
- Bugs that surface in the dashboard but trace back to this extractor → file here with label `contract` if the schema is broken.
- When an issue spans both repos, file on the repo where the fix lives and cross-reference the other.

## Labels

Workflow labels (triage state): `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`
