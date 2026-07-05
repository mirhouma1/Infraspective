---
name: Compression/Beam-Column loader gate
description: Durable invariant — shared-pipeline section loaders must exclude sections they can't compute
---

# Section loaders must gate on required properties, not trust the glob

The Compression and Beam-Column pages load sections by globbing the whole `data/`
directory, which mixes in tension-pipeline files that use a different header
convention (no shared alias). Rows from those files resolve their radii-of-gyration
to nothing, so building the section throws — and because they can sort to the top,
one becomes the default and the page errors on first paint.

**Invariant:** a shared-pipeline loader must keep only sections whose required
inputs (area + both radii of gyration) actually resolve, and drop the rest.

**Why:** this regressed twice — the guard was removed during a data-source swap and
had to be restored. A "simpler" loader that trusts every globbed file reintroduces
the first-load crash.

**How to apply:** after any change to these loaders, confirm the default section
still builds and that incompatible-convention families no longer appear.
