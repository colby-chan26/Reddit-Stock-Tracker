from dataclasses import dataclass
from enum import Enum

class SubmissionType(Enum):
    POST = 'POST'
    COMMENT = 'COMMENT'
    REPLY = 'REPLY'

@dataclass
class SubmissionData:
    """Data class to store parsed Reddit submission information."""
    submission_id: str
    score: int
    created_utc: int
    author: str
    subreddit: str
    type: SubmissionType