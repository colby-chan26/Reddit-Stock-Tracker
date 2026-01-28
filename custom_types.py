from dataclasses import dataclass
from enum import Enum

class SubmissionType(Enum):
    POST = 'POST'
    COMMENT = 'COMMENT'
    REPLY = 'REPLY'

@dataclass
class SubmissionData:
    """Data class to store parsed Reddit submission information."""
    post_id: str  # Parent post ID (same as submission_id for posts)
    submission_id: str  # This item's own ID
    score: int
    created_utc: int
    author: str
    subreddit: str
    type: SubmissionType