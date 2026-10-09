# Presence Atlas: completed-release dashboard

## 2026-10-08 engineering increment

The runtime now has five tabs: Overview, Need × Market Map, Brand Competition,
Evidence & Citation Explorer and Opportunity Queue. Need mappings are explicitly
unavailable until approved snapshots exist; legacy competition is exploratory.
Optional original-field evidence is read from `presentation.release_evidence`
in the same selected-release transaction, never live raw/Silver. Separate SQLite
review history is read-only and release-filtered; action entry uses the controlled
external writer. See [workflow runbook](v1_workflow_runbook.md) for the new contract,
tested scope and remaining V1.0 gates. The legacy definitions below remain applicable
to existing v1 metric rows, but their four-tab/table-only description is historical.

## Start (Windows PowerShell, Python 3.12)

From the project root (the folder containing the Streamlit launcher):

```powershell
Set-Location d:/FYP/FYP/FYP/FYP/FYP/FYP
py -3.12 -m venv .venv-dashboard
& ./.venv-dashboard/Scripts/python.exe -m pip install -e . pytest pytest-cov
$env:GEO_DASHBOARD_DB = 'd:/FYP/FYP/FYP/FYP/FYP/FYP/data/warehouse/phase_d_presentation.duckdb'
& ./.venv-dashboard/Scripts/python.exe -m streamlit run streamlit_app.py --server.address 127.0.0.1
```

Open http://localhost:8501. The sidebar also accepts an existing warehouse path.
Without the environment variable, the default is the project's main warehouse.
There is no automatic fallback to an unrelated database, creation, migration,
publication or collection. A missing file/schema/release gives a friendly state.
Do not expose the local application to an untrusted network: it permits local
warehouse selection and exposes snapshot lineage identifiers.

Tests (only temporary fixture databases are written):

```powershell
& ./.venv-dashboard/Scripts/python.exe -m pytest tests/unit/test_dashboard.py --no-cov
```

## Release and query safety

- The service opens DuckDB with `read_only=True`; it does not use storage writers,
  initialization, migrations, release publication or provider clients.
- Only presentation release metadata, `information_schema.columns` and the
  three fixed `presentation.release_*` snapshot tables are queried. No raw,
  Bronze, Silver, Gold or analytical presentation views are queried.
- Default selection verifies the `current` slot points to a completed release.
  Historical selection must explicitly name a completed release. No implicit
  “latest release” fallback; incomplete/draft releases are never shown.
- Metadata and all three frames are loaded in one transaction and materialized.
  One release ID is frozen across every tab and filter until the next rerun.
  A subsequent rerun deliberately refreshes the current pointer. No global cache.
- Release IDs are SQL parameters. Identifiers are fixed code-owned allowlists;
  filters operate on materialized frames and cannot become SQL.
- Missing core schema fails closed. Missing additive locale/context fields become
  null (legacy release), never inferred from registries or current settings.
- A warehouse held by an incompatible writer may be unreadable. Stop the writer
  or use an independently prepared copy; the dashboard does not alter locking.

## Tabs and definitions

**Overview:** grouped SERP/LLM presence bars, numerator and denominator counts,
distinct observation counts and source/collection statuses. SERP presence is
`numerator > 0` for available `serp_organic_sov` v1 rows. LLM presence is
`metric_value > 0` for available `llm_brand_mention` v1 rows. Each rate uses
distinct observation-brand rows, not expanded comparisons. Unavailable rows
are reported separately, never converted to zeros. Source statuses count each
observation once across selected brands. Empty denominator means unknown rate.

**Markets:** locale × brand heatmap, scoped to channel, provider, engine/type/device
or platform/model, and collection window; accompanying sample-count table. Labels
preserve language codes and provider location identifiers, with explicit unknowns.
There is no provider-code-to-country inference. The UI warns that topic and
instrument/sample mix preclude interpreting this as a controlled regional effect.

**Evidence:** original snapshot fields and selected metric drilldown, including
versions, availability, observation/query/prompt IDs, timestamps and hashes where
recorded. No raw text, URL, answer snippet or citation provenance is invented.

**Opportunities:** three investigation patterns: SERP present/LLM absent, LLM
present/SERP absent, neither present. Both-present count provides context. Only
available `comparison_brand_presence` **2.0.0**, `matched_context`, nonnull locale,
window and observation IDs qualify; both channel statuses must be available.
v1 comparisons are excluded regardless of release-level metadata version.
Repeated identical source/context pairs are deduplicated. Pair counts can still
reuse an observation across different source pairs or mappings, so distinct SERP
and LLM counts are shown separately. Channel rates never use pair-expanded rows.
Matching locale/window is not proof of controlled source pairing or semantic
equivalence; approved mapping quality requires independent review.

## Filters and limitations

Brand, language, provider location identifier and window apply independently to
each channel and comparisons. Engine affects SERP only; platform affects LLM only;
both affect comparisons. All values initially selected means unrestricted; empty
selection excludes matching rows. Unknown is a selectable null, not a sentinel
string that could collide with actual provider codes. Legacy unknown window or
source metadata is retained unless explicitly excluded by a filter.

The existing LLM matcher searches aliases in response text/serialized items;
presence is not validated answer-only extraction. Mention counts are alias-entry
hits and citation counts are registered-domain hits, not actual occurrences or
unique citations. SERP organic presence is not validated Top10 coverage. Collection
timestamps are received times, not guaranteed engine generation times. Locale
parameters do not establish that a provider applied personalization.

No aggregate hidden-opportunity score, fake ROI, demand, traffic or causal claim.
Validate extraction/matching, approved query-prompt mapping, sample coverage,
repeated observations and business relevance before taking commercial action.
This dashboard intentionally does not publish or repair legacy releases. A
separate future demo-fixture script may prepare a disposable warehouse; none is
included or executed here.