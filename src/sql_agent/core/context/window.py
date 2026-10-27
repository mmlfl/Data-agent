"""Single source of truth for model-window reserves."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextWindowBudget:
    total: int
    safety: int
    output: int

    @property
    def input(self):
        return self.total - self.safety - self.output

    @classmethod
    def from_config(cls, config):
        return cls(config.context_window_tokens, int(config.context_window_tokens * config.context_safety_ratio),
                   config.max_tokens or config.context_output_reserve_tokens)
