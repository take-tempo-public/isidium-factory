"""The store server (03b §2; 03 §1.2, §1.3): one writer of every governed path, per tenant — the governed copy (a
clone of the tenant repo), the journal (SQLite, write-ahead, hash-chained), the id counter, the grant check, the
signer seam, and the verbs. Runs as one process (`python -m isidium.store.server`); the Containerfile wraps it."""
