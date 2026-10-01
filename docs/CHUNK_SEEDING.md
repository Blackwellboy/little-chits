# Procedural chunk seed identity

Little Chits does not currently stream procedural chunks, but future chunk expansion must use a stable identity
before it is enabled.

The canonical tuple is:

```
(world_seed, chunk_x, chunk_y, generator_version)
```

It is implemented by `server/chits/sim/terrain.py::chunk_seed`. The function serializes a domain tag, the chunk-seed
scheme version, and the four integer fields as canonical JSON, hashes the bytes with SHA-256, and uses the first
64 bits as the deterministic RNG seed.

This intentionally rejects ambiguous forms such as:

```
world_seed + chunk_x + chunk_y + generator_version
```

or delimiter-free string concatenation. Swapped coordinates, negative coordinates, generator-version changes and
world-seed changes produce distinct identities. `CHUNK_SEED_SCHEME` is versioned separately so the derivation
itself can change without pretending old and new chunk identities are the same.

When chunk streaming is implemented, snapshots/manifests must record both the terrain generator version and
`CHUNK_SEED_SCHEME`.
