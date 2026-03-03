from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.llm_client import BaseLLMClient, get_llm_client
from app.core.prompt_templates import PromptTemplate, render_prompt

logger = logging.getLogger(__name__)


# ── Cost estimation ──

COST_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(len(text) // 4, 1)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a call."""
    rates = COST_PER_1K_TOKENS.get(model, {"input": 0.005, "output": 0.015})
    cost = (input_tokens / 1000) * rates["input"] + (output_tokens / 1000) * rates["output"]
    return round(cost, 6)


# ── Rate limiter ──

class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter keyed by workspace_id."""

    def __init__(self, max_calls: int = 10, window_seconds: int = 60):
        self._max_calls = max_calls
        self._window = window_seconds
        self._calls: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, workspace_id: str) -> bool:
        """Return True if the call is allowed."""
        now = time.time()
        with self._lock:
            timestamps = self._calls.get(workspace_id, [])
            cutoff = now - self._window
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= self._max_calls:
                return False
            timestamps.append(now)
            self._calls[workspace_id] = timestamps
            return True

    def remaining(self, workspace_id: str) -> int:
        now = time.time()
        with self._lock:
            timestamps = self._calls.get(workspace_id, [])
            cutoff = now - self._window
            active = [t for t in timestamps if t > cutoff]
            return max(self._max_calls - len(active), 0)


_rate_limiter = SlidingWindowRateLimiter(max_calls=10, window_seconds=60)


# ── Evidence grounding ──

def verify_evidence_grounding(
    evidence_refs: List[str],
    additions: List[str],
    removals: List[str],
) -> tuple:
    """
    Check that evidence strings actually appear in the diff.
    Returns (grounded_refs, is_grounded).
    """
    all_diff_text = " ".join(additions + removals).lower()
    grounded = []
    for ref in evidence_refs:
        ref_lower = ref.lower().strip()
        if not ref_lower:
            continue
        # Substring match or >=60% overlap
        if ref_lower in all_diff_text:
            grounded.append(ref)
        else:
            # Check partial overlap with any single addition/removal
            for line in additions + removals:
                line_lower = line.lower()
                # Check if at least 60% of the evidence words appear in the line
                ref_words = set(ref_lower.split())
                line_words = set(line_lower.split())
                if ref_words and len(ref_words & line_words) / len(ref_words) >= 0.6:
                    grounded.append(ref)
                    break

    is_grounded = len(grounded) >= 1
    return grounded, is_grounded


# ── LLM Call Result ──

@dataclass
class LLMCallResult:
    success: bool
    content: Optional[Dict[str, Any]] = None
    validated_output: Optional[BaseModel] = None
    is_grounded: bool = False
    grounded_evidence: List[str] = field(default_factory=list)
    validation_errors: Optional[List[str]] = None
    raw_response: Optional[str] = None
    model_used: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    attempts: int = 0
    error: Optional[str] = None


# ── LLM Service ──

class LLMService:
    """
    Enhanced LLM service wrapping BaseLLMClient with:
    - JSON schema validation + retry
    - Evidence grounding checks
    - Token/cost tracking
    - Rate limiting per workspace
    """

    def __init__(self, client: Optional[BaseLLMClient] = None):
        self._client = client

    @property
    def client(self) -> BaseLLMClient:
        if self._client is None:
            self._client = get_llm_client()
        return self._client

    def generate_insight(
        self,
        template: PromptTemplate,
        context: Dict[str, Any],
        workspace_id: str,
        additions: Optional[List[str]] = None,
        removals: Optional[List[str]] = None,
        max_retries: int = 2,
    ) -> LLMCallResult:
        """
        Generate a structured insight using a prompt template.

        1. Check rate limit
        2. Render prompt from template
        3. Call LLM with JSON mode
        4. Validate output against schema
        5. Verify evidence grounding
        6. Retry with error feedback if validation fails
        7. Track cost + tokens
        """
        settings = get_settings()

        # Rate limit check
        if not _rate_limiter.check(workspace_id):
            remaining = _rate_limiter.remaining(workspace_id)
            return LLMCallResult(
                success=False,
                error=f"Rate limit exceeded for workspace {workspace_id}. "
                       f"Remaining: {remaining}/min",
            )

        # Render prompt
        try:
            system_prompt, user_prompt = render_prompt(template, context)
        except KeyError as exc:
            return LLMCallResult(
                success=False,
                error=f"Template rendering failed, missing key: {exc}",
            )

        model = settings.LLM_MODEL
        provider = settings.LLM_PROVIDER
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        last_error = None
        raw_response = None

        for attempt in range(1, max_retries + 2):  # max_retries + 1 total attempts
            start_time = time.time()
            try:
                # Estimate input tokens
                prompt_text = system_prompt + user_prompt
                input_tokens = estimate_tokens(prompt_text)

                # Call LLM
                raw = self.client.chat(system_prompt, user_prompt, json_mode=True)
                raw_response = raw

                elapsed_ms = int((time.time() - start_time) * 1000)
                output_tokens = estimate_tokens(raw)
                call_cost = estimate_cost(model, input_tokens, output_tokens)

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_cost += call_cost

                # Parse JSON
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as je:
                    last_error = f"Invalid JSON: {str(je)[:200]}"
                    logger.warning(
                        "Attempt %d/%d: LLM returned invalid JSON: %s",
                        attempt, max_retries + 1, last_error,
                    )
                    # Append error feedback for retry
                    user_prompt = (
                        user_prompt
                        + f"\n\nYour previous response was not valid JSON. "
                        f"Error: {last_error}. Please respond ONLY with valid JSON."
                    )
                    continue

                # Validate against Pydantic schema
                try:
                    validated = template.output_schema.model_validate(parsed)
                except ValidationError as ve:
                    errors = [str(e) for e in ve.errors()]
                    last_error = f"Schema validation failed: {errors[:3]}"
                    logger.warning(
                        "Attempt %d/%d: Schema validation failed: %s",
                        attempt, max_retries + 1, last_error,
                    )
                    user_prompt = (
                        user_prompt
                        + f"\n\nYour previous response had validation errors: "
                        f"{json.dumps(errors[:3])}. Fix them and respond with valid JSON."
                    )
                    continue

                # Evidence grounding check
                evidence_list = parsed.get("evidence", [])
                diff_additions = additions or []
                diff_removals = removals or []
                grounded_refs, is_grounded = verify_evidence_grounding(
                    evidence_list, diff_additions, diff_removals,
                )

                if not is_grounded and evidence_list:
                    logger.warning(
                        "Insight not grounded: none of %d evidence refs matched diff",
                        len(evidence_list),
                    )

                return LLMCallResult(
                    success=True,
                    content=parsed,
                    validated_output=validated,
                    is_grounded=is_grounded,
                    grounded_evidence=grounded_refs,
                    raw_response=raw,
                    model_used=model,
                    provider=provider,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    cost_usd=total_cost,
                    latency_ms=elapsed_ms,
                    attempts=attempt,
                )

            except Exception as exc:
                elapsed_ms = int((time.time() - start_time) * 1000)
                last_error = str(exc)
                logger.error(
                    "Attempt %d/%d: LLM call failed: %s",
                    attempt, max_retries + 1, exc,
                )

        # All retries exhausted
        return LLMCallResult(
            success=False,
            raw_response=raw_response,
            model_used=model,
            provider=provider,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_usd=total_cost,
            latency_ms=0,
            attempts=max_retries + 1,
            error=f"All {max_retries + 1} attempts failed. Last error: {last_error}",
            validation_errors=[last_error] if last_error else None,
        )


_llm_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Singleton factory for LLMService."""
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
    return _llm_service_instance
