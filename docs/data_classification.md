# Data Classification

| Category | Sensitivity | Git policy | Retention policy | Redaction requirement | Permitted test usage |
| --- | --- | --- | --- | --- | --- |
| Credentials | Critical | Never commit | Secret-store lifecycle only | Always; no value logging | Synthetic placeholders only |
| Request payloads | Sensitive | Do not commit production payloads | Retain per approved research/audit policy | Remove credentials and personal/sensitive inputs | Sanitized fixtures only |
| Raw API responses | Sensitive | Never commit production responses | Immutable, checksum-backed retention policy | Redact credentials and review sensitive content | Sanitized, provenance-marked fixtures |
| Bronze metadata | Internal | Generated production data excluded | Retain with release/audit policy | Remove secret-like fields | Synthetic or sanitized datasets |
| Parsed evidence | Internal/Sensitive | Generated production data excluded | Retain by research/release policy | Redact inherited sensitive content | Sanitized fixtures and synthetic data |
| Metrics | Internal | Generated reports/data excluded unless explicitly approved aggregate | Retain by release policy | Suppress sensitive dimensions where needed | Synthetic and approved aggregate fixtures |
| Logs | Sensitive | Never commit | Short operational retention | Mandatory credential and payload redaction | Synthetic logs only |
| Generated reports | Internal/Sensitive | Do not commit generated reports | Release retention policy | Validate no secrets/raw sensitive content | Synthetic or approved aggregate examples |
| Test fixtures | Internal | Commit only sanitized fixtures | Version with code while valid | No credentials; document provenance | Permitted after review |

No category permits real credentials in tests. Raw response fixtures must identify their source contract version and sanitization status before use.