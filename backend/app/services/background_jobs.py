import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Thread-safe in-memory job store for background PDF processing
_jobs_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


class JobStatus:
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BackgroundJobService:
    """Service to create, update, and inspect status of background PDF ingestion jobs."""

    def create_job(self, paper_id: str, pdf_url: Optional[str] = None) -> str:
        """Create a new job and return unique job_id."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with _jobs_lock:
            _jobs[job_id] = {
                "job_id": job_id,
                "paper_id": paper_id,
                "pdf_url": pdf_url,
                "status": JobStatus.QUEUED,
                "current_step": "Job queued for background execution",
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
        return job_id

    def update_job(
        self,
        job_id: str,
        status: str,
        current_step: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Update job status and current step description."""
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = status
                if current_step:
                    _jobs[job_id]["current_step"] = current_step
                if error:
                    _jobs[job_id]["error"] = error
                _jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Retrieve current job status object."""
        with _jobs_lock:
            if job_id in _jobs:
                return dict(_jobs[job_id])
        return {
            "job_id": job_id,
            "status": JobStatus.FAILED,
            "error": f"Job ID '{job_id}' not found.",
        }


background_job_service = BackgroundJobService()
