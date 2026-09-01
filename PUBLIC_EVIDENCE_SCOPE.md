# Public evidence scope

Large and private evidence is intentionally kept out of ordinary Git. The file
`reproducibility/OFF_REPO_ARTIFACT_INTEGRITY.tsv` records its preservation state,
size, SHA-256, and purpose.

Some publication-facing copies of result and configuration files replace
workstation root strings with `<LOCAL_RESEARCH_ROOT>` or `<USER_HOME>`. Frozen
protocol and source trees are never sanitized or rewritten: they remain
byte-identical to their protocol-lock hashes.

Two protocol-locked documentation files retain a generic workstation root used
during registered execution. The strings contain no username, hostname,
credential, or secret. They remain unchanged because rewriting them would break
byte identity with the registered protocol locks.

The exact release ZIP produced beside this directory is intended for GitHub
Releases and archival deposition. Full database and vector backups remain
private unless a separate disclosure decision is made.

## Public path sanitization

Two absolute workstation prefixes in protocol documentation were replaced with `<MHB_RESEARCH_ROOT>/` and `<MHB_V0_3_ROOT>/` in this public copy. The private protocol locked originals remain unchanged. No experimental configuration, case content, executable logic, outcomes, labels, or model records were altered.
