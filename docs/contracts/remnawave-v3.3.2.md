# Remnawave API contract baseline

STEP 5 was implemented against the user-supplied `api-remnawave.json`:

- OpenAPI title: `Remnawave API v3.3.2`
- version: `3.3.2`
- SHA-256: `60d2dabf9c170829f6e807135df84e78e0c8a005820bcb8dd78127cb9d33bc33`
- source size: `1,597,371` bytes

The adapter contract tests cover the subset used by Hazbit: users, status,
enable/disable/update/extend, HWID create/list/delete, and system health.
When the supplied OpenAPI changes, compare its checksum and update the typed
adapter plus contract tests before changing Platform domain code.
