from fastapi import APIRouter, HTTPException
from cache import get_job_status
from models.schemas import JobStatusResponse, EnrichedProduct

router = APIRouter()


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job(job_id: str):
    """
    Polled by the extension every few seconds after a cache miss.
    Returns status + enriched product data when complete.
    """
    job = await get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    status = job.get("status", "queued")

    if status == "complete":
        return JobStatusResponse(
            status="complete",
            data=EnrichedProduct(**job["data"]),
        )

    if status == "failed":
        return JobStatusResponse(
            status="failed",
            error=job.get("error", "Unknown error"),
        )

    # queued or processing
    return JobStatusResponse(
        status=status,
        eta_seconds=job.get("eta_seconds", 10),
    )