"""
gdot_earthwork -- read earthwork cut/fill volumes off road cross-section
plan sets (scanned or vector PDF).

    from gdot_earthwork import process_plan_set
    result = process_plan_set("plans.pdf")
"""
__version__ = "2.0.0"

from .config import PipelineConfig, get_config  # noqa: E402
from .plan_set import PlanSetResult, SectionResult, process_plan_set  # noqa: E402

__all__ = ["PipelineConfig", "get_config", "process_plan_set", "PlanSetResult", "SectionResult", "__version__"]
