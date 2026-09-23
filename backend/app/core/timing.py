import time
import logging
import sys
import uuid

logger = logging.getLogger("rag_timing")
logger.setLevel(logging.INFO)

if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setLevel(logging.INFO)
    _formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
    logger.propagate = False


class StageTimer:
    def __init__(self, request_id: str | None = None):
        self.request_id = request_id or str(uuid.uuid4())[:8]
        self.start = time.perf_counter()
        self.last = self.start
        self.marks: dict[str, float] = {}

    def mark(self, stage_name: str, extra: str = ""):
        now = time.perf_counter()
        elapsed_since_last = (now - self.last) * 1000
        elapsed_total = (now - self.start) * 1000
        self.marks[stage_name] = round(elapsed_since_last, 1)
        self.last = now
        suffix = f" | {extra}" if extra else ""
        logger.info(
            f"[{self.request_id}] {stage_name}: {elapsed_since_last:.0f}ms "
            f"(total: {elapsed_total:.0f}ms){suffix}"
        )

    def summary(self) -> dict:
        total = round((self.last - self.start) * 1000, 1)
        return {"request_id": self.request_id, "stages_ms": self.marks, "total_ms": total}
