"""Golden OCR samples used to drive the Ragas evaluation suite.

Each sample mimics the noisy text we receive from `LlmOCRAdapter` for a real
diagram. The `expected_components` / `expected_risks_keywords` fields are not
ground-truth labels for retrieval-style metrics — they are hints used by
custom Ragas `AspectCritic` definitions and by lightweight structural
assertions that complement the LLM-as-a-judge metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArchitectureSample:
    """A single OCR diagram sample plus the qualitative expectations."""

    id: str
    source_hint: str
    ocr_text: str
    expected_components: list[str] = field(default_factory=list)
    expected_risks_keywords: list[str] = field(default_factory=list)
    must_be_in_portuguese: bool = True


SAMPLES: list[ArchitectureSample] = [
    ArchitectureSample(
        id="ecommerce_microservices",
        source_hint="png",
        ocr_text=(
            "Cliente -> [Web App / React] -> [API Gateway]\n"
            "[API Gateway] -> [Auth Servc] (JWT)\n"
            "[API Gateway] -> [Orders Service] -> [Postgres orders_db]\n"
            "[API Gateway] -> [Catalog Service] -> [Postgres catalog_db]\n"
            "[Orders Service] --(async)--> [RabbitMQ payments.queue]\n"
            "[Payments Worker] <- [RabbitMQ payments.queue]\n"
            "[Payments Worker] -> Stripe (HTTPS)\n"
            "[Catalog Service] -> [Redis cache]\n"
            "Logs -> CloudWatch\n"
        ),
        expected_components=[
            "API Gateway",
            "Auth Service",
            "Orders Service",
            "Catalog Service",
            "RabbitMQ",
            "Postgres",
            "Redis",
        ],
        expected_risks_keywords=[
            "single point of failure",
            "ponto único",
            "escalabilidade",
            "consist",
            "retry",
            "idempot",
        ],
    ),
    ArchitectureSample(
        id="data_pipeline_lambda",
        source_hint="pdf",
        ocr_text=(
            "S3 raw-bucket --(event)--> Lambda ingest\n"
            "Lambda ingest -> Kinesis stream events\n"
            "Kinesis stream events -> Lambda transform\n"
            "Lambda transform -> S3 curated-bucket\n"
            "S3 curated-bucket -> Athena (queries)\n"
            "Athena -> QuickSight (dashboards)\n"
            "DLQ: SQS dlq-ingest, SQS dlq-transform\n"
            "Secrets: AWS Secrets Manager\n"
        ),
        expected_components=[
            "S3",
            "Lambda",
            "Kinesis",
            "Athena",
            "QuickSight",
            "SQS",
        ],
        expected_risks_keywords=[
            "cold start",
            "throttl",
            "custo",
            "particion",
            "schema",
            "DLQ",
        ],
    ),
    ArchitectureSample(
        id="legacy_monolith_db",
        source_hint="png",
        ocr_text=(
            "Browser -> NGINX (TLS) -> Monolith App (Java 8 / Tomcat)\n"
            "Monolith App -> Oracle DB (single instance)\n"
            "Cron Jobs run inside Monolith (nightly reports)\n"
            "Backups: rsync to NFS share\n"
            "No load balancer, no replicas\n"
        ),
        expected_components=[
            "NGINX",
            "Monolith",
            "Oracle",
        ],
        expected_risks_keywords=[
            "single point of failure",
            "ponto único",
            "alta disponibilidade",
            "backup",
            "escalabilidade",
            "indisponibilidade",
        ],
    ),
]


def get_sample(sample_id: str) -> ArchitectureSample:
    for sample in SAMPLES:
        if sample.id == sample_id:
            return sample
    raise KeyError(f"Unknown architecture sample: {sample_id}")
