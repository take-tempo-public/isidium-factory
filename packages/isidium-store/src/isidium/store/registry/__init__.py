"""The schema registry (03b §4, 04 §4): versioned, content-addressed schema documents `name@version` under
`schemas/`, the nine-member constraint vocabulary and its form validator (`registry@1` is the fixed point), the
loader, and the validators that read schema documents — `config.toml` (04) and the card profile (03 §3, §1.11).

Layering: core (canon · chain · grammar · derive) ← registry (this package) ← server / client.
"""
