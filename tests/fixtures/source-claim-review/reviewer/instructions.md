# Source-claim review

For each case in `cases.json`, compare the claim with the provided passage only.
Choose `supported`, `contradicted`, or `unverifiable`. Explain how the passage
supports or contradicts the claim, or identify what evidence is missing. Do not
assume facts beyond the passage.

Return a JSON array with one record per case. Each record must contain `case_id`,
`reviewer_id`, `source_sha256`, `claim_sha256`, `verdict`, `locator`, `quote`,
`start`, `end`, and `explanation`. Use SHA-256 of the exact UTF-8 passage and
claim strings as loaded. The locator is the section label preceding `: ` in the
passage. `quote` is an exact excerpt; `start` and `end` are Unicode character
offsets in the passage, with `end` exclusive.
