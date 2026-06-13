from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalConfig:
    address: str
    namespace: str
    task_queue: str

    @classmethod
    def from_settings(cls, settings) -> "TemporalConfig":
        return cls(
            address=settings.temporal_address,
            namespace=settings.temporal_namespace,
            task_queue=settings.task_queue,
        )
