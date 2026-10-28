"""The remote-totp signing service (the service half of `isidium.store.server.signer.RemoteTotpContract`).

It signs `chain.sig_bytes(tenant, value)` with its own Ed25519 key, and only after the owner's Aegis code for that
request: a code from the owner's phone, which no session on the workstation can produce. It runs only on the owner's
own host, never where the store or a session runs, and so it is its own distribution rather than a
module of `isidium-store`, whose image must not carry it.

Its only imports from `isidium-store` are `core.chain` (`sig_bytes`, `format_sig`, `fingerprint`) and the `Refusal`
type the contract names for a declined request; `http.HttpsService` implements `RemoteTotpContract` structurally, so
the contract itself is not imported. Nothing in `isidium-store` imports this package.

Nothing is imported here (C-13): each submodule is imported by the code that uses it.
"""
