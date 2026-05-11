"""Shared `AspectCritic` definitions consumed by `evals.py`."""
from __future__ import annotations

from dataclasses import dataclass

from ragas.metrics import AspectCritic


@dataclass(frozen=True)
class CriticSpec:
    name: str
    definition: str


CRITICS: list[CriticSpec] = [
    CriticSpec(
        name="brazilian_portuguese",
        definition=(
            "The response must be written in Brazilian Portuguese. Return 1 "
            "if the response is clearly Brazilian Portuguese (vocabulary, "
            "grammar and spelling), and 0 otherwise. Technical names of "
            "products, services or protocols (e.g. Kubernetes, RabbitMQ, "
            "JWT) are allowed in English without penalty."
        ),
    ),
    CriticSpec(
        name="grounded_in_input",
        definition=(
            "Evaluate whether every component, service, integration and "
            "specific technology mentioned in the response is reasonably "
            "supported by the OCR text provided in user_input. Allow minor "
            "OCR corrections (e.g. 'Auth Servc' -> 'Auth Service') and "
            "explicitly stated assumptions. Return 1 if the response is "
            "well grounded with no clear hallucinations, and 0 if it "
            "introduces components/technologies that have no plausible "
            "origin in the OCR text."
        ),
    ),
    CriticSpec(
        name="risks_and_mitigations",
        definition=(
            "Return 1 if the response lists at least three distinct "
            "architectural risks AND each risk has an associated mitigation "
            "or recommendation. Otherwise return 0. The response is in "
            "Brazilian Portuguese, so accept synonyms such as 'risco', "
            "'mitigação', 'recomendação'."
        ),
    ),
    CriticSpec(
        name="components_match_topology",
        definition=(
            "Return 1 if the components extracted in the response cover the "
            "main building blocks of the architecture described in the OCR "
            "user_input (it is acceptable to merge or split components, but "
            "the bulk of named services / databases / queues / gateways "
            "should be represented). Return 0 if the response misses most "
            "of the topology or invents large parts of it."
        ),
    ),
]


def get_critic_spec(name: str) -> CriticSpec:
    for spec in CRITICS:
        if spec.name == name:
            return spec
    raise KeyError(f"Unknown critic: {name}")


def build_aspect_critic(spec: CriticSpec, llm):
    """Build a single Ragas `AspectCritic` from a `CriticSpec`."""
    return AspectCritic(name=spec.name, definition=spec.definition, llm=llm)


def build_all_aspect_critics(llm):
    """Build every shared `AspectCritic`. Used by the script runner."""
    return [build_aspect_critic(spec, llm) for spec in CRITICS]
