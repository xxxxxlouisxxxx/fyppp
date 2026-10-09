"""Raw-first evidence finalization for successful injected collection results."""

from __future__ import annotations

from geo_research.storage.raw_store import RawEvidence, RawWriteResult
from geo_research.storage.repositories import RawEvidenceRepository


class RawEvidenceFinalizer:
    """Finalizes immutable artifacts before committing their Bronze metadata."""

    def __init__(self, repository: RawEvidenceRepository) -> None:
        self.repository = repository

    def finalize(self, evidence: RawEvidence) -> RawWriteResult:
        """Write raw files first, then transactionally record their metadata."""
        result = self.repository.raw_store.write(evidence)
        self.repository.record(evidence, result)
        return result
