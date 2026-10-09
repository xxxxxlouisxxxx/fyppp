# Instrument pairing and result-driven brands — user decision 2026-10-08

The requesting user explicitly approved query-001 ↔ prompt-001, query-002 ↔
prompt-002, and the same-index rule for the remaining existing instruments.
[comparisons registry](../config/registries/comparisons.csv) now records all 68
explicit rows with reviewer, approval date, reason, version and effective scope.
This resolves the instrument pairing decision, not extraction quality or paid runs.

Runtime does not infer new mappings from suffixes. New instruments need new explicit
approved rows. Existing locale/window eligibility checks remain mandatory: approval
of instruments does not authorize cross-language/window comparisons. The offline
registry importer validates the mappings and retains full approval rows in its
`meta.registry_csv` artifact. No production warehouse or historical release was
modified. Activation date applies to the mapping definition/new build, not a claim
that older source observations are disallowed or previously released results changed.

## Brand scope clarification

**No fixed brand is required to begin research.** Keywords/prompts define the
research instruments; observed SERP/answer/product evidence supplies brand-name
proposals. A chosen owned brand is optional, not the analysis starting point.

- Inspect all available result evidence, not only hits in a preselected dictionary.
- Explicit product `brand` fields can produce traceable candidate-name proposals
  without a fixed dictionary using `discover_explicit_brands()`.
- Merchant/seller/domain/title words are not automatically brand identities.
- Arbitrary names in free-text answers/titles still require manual annotation or
  a validated entity extractor. This increment does not claim general NER discovery.
- Retain occurrence/item/result/observation lineage and original spelling. Similar
  names/model names are not silently merged; candidate identity is provisional.
- Candidate evidence may be inspected/reviewed, but formal brand KPI and ownership
  attribution still require validated identities/aliases/domains. Do not invent an
  owned brand, fabricate domain ownership or treat dictionary absence as no brands.

Current v2 formal Gold remains approved-registry-based; a result-driven discovery
review stage must precede those metrics. The new pure discovery helper is fixture
tested but not automatically run against production or connected to the dashboard.
This clarification does not claim that discovery/review/publication is already
complete end-to-end. Existing placeholder brand CSV rows were not promoted.