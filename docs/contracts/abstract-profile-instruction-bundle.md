# Historical abstract profile instructions

Profiles1,2,3 retain their original source commit, file hashes, manifest digest and no-tool restrictions. Their identical historical instruction material now lives under package-owned `skills_data/_profiles/abstract-draft-instructions-v1/`, independent of evolving operator skills. This repairs the regression where truthful canonical skill documentation changed the bytes and disabled all existing adapters.

These historical bytes are retained solely for deterministic restricted draft profiles; historical dual-write wording does not authorize writes. The profile's explicit `not_performed` restrictions continue to exclude cluster CLI, Zotero/Obsidian writes and human acceptance. Canonical and top-level packaged operator skills retain the corrected current guidance.

The loader still rejects any changed historical byte. Moving the read location does not silently update a profile hash or reinterpret an old task. New instruction semantics require an explicit new profile/version contract rather than editing this bundle.
