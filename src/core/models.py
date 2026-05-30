from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    """Represents a single job listing."""
    id: str                  # unique identifier (board + job_id or url hash)
    title: str
    company: str
    url: str
    board: str               # source board name
    location: str = "Remote"
    description: str = ""
    apply_url: str = ""
    salary: str = ""
    tags: list = field(default_factory=list)
    apply_email: Optional[str] = None   # set if the job explicitly asks to apply by email
    posted_at: str = ""
    apply_type: str = ""     # "email" | "easy_apply" | "ats" | "external" | ""
    recruiter_name: str = ""
    recruiter_url: str = ""
    score: int = 0                              # 0-100 CV relevance score
    match_reasons: list = field(default_factory=list)  # high-value keywords matched

    def __post_init__(self):
        if not self.apply_url:
            self.apply_url = self.url
