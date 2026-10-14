"""Golden dataset: what a correct run looks like for each task, written before any model sees it."""
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

Category = Literal["normal", "ambiguous", "wrong_tool", "tool_failure", "constraint"]
DATASETS_DIR = Path(__file__).parent / "datasets"


class ExpectedCall(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class RefundOutcome(BaseModel):
    order_id: int
    amount: float


class AddressOutcome(BaseModel):
    order_id: int
    # Kept to document the intent. The stored trace redacts addresses, so only the order id can be
    # verified today (see docs/day-3-evaluation-plan.md, option B).
    new_address: str | None = None


class Outcome(BaseModel):
    """World state implied by the *successful* mutating tool calls."""

    refunds: list[RefundOutcome] = Field(default_factory=list)
    address_changes: list[AddressOutcome] = Field(default_factory=list)


class EvalCase(BaseModel):
    id: str
    category: Category
    task: str
    required_calls: list[ExpectedCall] = Field(default_factory=list)  # ordered subsequence the trace must contain
    optional_calls: list[ExpectedCall] = Field(default_factory=list)  # tolerated, not demanded
    forbidden_tools: list[str] = Field(default_factory=list)
    outcome: Outcome = Field(default_factory=Outcome)
    answer_must_match_any: list[str] = Field(default_factory=list)  # regexes, case-insensitive
    answer_must_not_match: list[str] = Field(default_factory=list)
    optimal_tool_calls: int
    efficiency_slack: int = 1
    reference_answer: str  # what a correct agent says; used to build the scripted reference run


class Dataset(BaseModel):
    version: str
    description: str = ""
    cases: list[EvalCase]
    content_hash: str = ""  # filled in by load_dataset; identifies exactly which expectations were used

    def case(self, case_id: str) -> EvalCase:
        for c in self.cases:
            if c.id == case_id:
                return c
        raise KeyError(case_id)


DEFAULT_DATASET = "golden-v2"


def load_dataset(name: str = DEFAULT_DATASET, directory: Path = DATASETS_DIR) -> Dataset:
    raw = (directory / f"{name}.json").read_bytes()
    dataset = Dataset.model_validate(json.loads(raw))
    return dataset.model_copy(update={"content_hash": hashlib.sha256(raw).hexdigest()[:12]})
