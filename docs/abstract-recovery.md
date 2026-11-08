# DOI-bound abstract recovery

Missing-abstract recovery tries Crossref, Unpaywall, OpenAlex and Semantic
Scholar in the existing order. A remote response must explicitly return a
DOI matching the requested DOI before its text or OA link can be reused.
Case, surrounding whitespace and standard DOI URL/prefix forms are normalized.
A missing, malformed or different DOI leaves that provider unresolved and
allows the fallback chain to continue. HTTP success alone is insufficient.

Semantic Scholar requests `externalIds` alongside `abstract,tldr` so this
check can use its returned DOI. A TLDR retains the `s2-tldr` source label;
it is derived text, not the author's abstract. If only Unpaywall has a usable
OA link, that link is retained only when its returned DOI matches.

The result shape and fallback order are unchanged. Stricter identity checks
can leave an abstract unavailable when a provider omits its DOI. Existing
placeholder rejection and explicit local-PDF fallback are unchanged. The
local-PDF path is user-supplied and is not independently DOI-verified by this
recovery helper.

A matching identifier is an observed metadata relationship. It does not
verify source content, a particular manuscript revision, downloaded PDF bytes
or scientific claims. Keep the original response and inspect source identity
when the research task requires stronger evidence. Offline synthetic tests
exercise routing and data preservation, not current live-provider coverage.
