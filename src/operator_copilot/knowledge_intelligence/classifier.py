"""Extensible Topic Classification component for Knowledge Intelligence Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from operator_copilot.course_generator.prompts import CLASSIFICATION_PROMPT
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.schemas.academy import KnowledgeExtractionLLMOutput, TopicClassificationLLMOutput

DEFAULT_CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "Assistenza tecnica": (
        "assistenza",
        "ticket",
        "supporto",
        "helpdesk",
        "sla",
        "contattare",
        "segnalazione",
        "otrs",
    ),
    "Gestione degli errori": (
        "errore",
        "anomalia",
        "blocco",
        "fallit",
        "errat",
        "ripristino",
        "warning",
        "attenzione",
    ),
    "Sicurezza e autorizzazioni": (
        "password",
        "mfa",
        "autenticazione",
        "blocco dell'account",
        "permessi",
        "ruoli",
        "credenziali",
        "firma digitale",
        "accesso",
    ),
    "Normativa e regolamenti": (
        "normativa",
        "legge",
        "decreto",
        "agid",
        "regolamento",
        "delibera",
        "art.",
        "obbligo di legge",
    ),
    "Amministrazione e contabilità": (
        "bilancio",
        "mandat",
        "accertament",
        "liquidazion",
        "siope",
        "pagopa",
        "iuv",
        "fattur",
        "imu",
        "tari",
        "tribut",
        "ragioneria",
    ),
    "Gestione documentale": (
        "protocollo",
        "conservazione",
        "determina",
        "delibera",
        "fascicolo",
        "gestione documentale",
        "registro giornaliero",
        "albo",
    ),
    "Utilizzo del software": (
        "schermata",
        "menu",
        "pulsante",
        "portlet",
        "cwol",
        "cityware",
        "maschera",
        "f7",
        "f3",
    ),
    "Best practice operative": (
        "consigli",
        "suggerimenti",
        "buona pratica",
        "evitare",
        "corretta modalità",
        "migliorare la qualità",
    ),
    "Procedure operative": (
        "procedura",
        "passaggi",
        "eseguire",
        "compilare",
        "inserire",
        "creare",
        "duplicazione",
    ),
}


@dataclass
class ClassificationResult:
    category: str
    secondary_categories: list[str] = field(default_factory=list)
    rationale: str = ""
    mode: str = "deterministic"


class TopicClassifier:
    """Classifies extracted topics against an extensible set of operational categories."""

    def __init__(
        self,
        generator: AnswerGenerator | None = None,
        custom_rules: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.generator = generator
        self.rules: dict[str, tuple[str, ...]] = {**DEFAULT_CATEGORY_RULES}
        if custom_rules:
            self.rules.update(custom_rules)

    def register_category(self, name: str, keywords: tuple[str, ...]) -> None:
        """Dynamically extend supported training categories."""
        self.rules[name] = keywords

    def list_categories(self) -> list[str]:
        return list(self.rules.keys())

    def classify(
        self,
        extracted: KnowledgeExtractionLLMOutput,
        *,
        context_text: str = "",
        bundle: Any = None,
    ) -> ClassificationResult:
        """Classify topic using LLM if active, otherwise multi-keyword deterministic scoring."""
        if self.generator is not None:
            parsed, used_llm, _ = self.generator.invoke_structured(
                CLASSIFICATION_PROMPT,
                {
                    "categories": ", ".join(self.list_categories()),
                    "title": extracted.title,
                    "summary": extracted.summary,
                    "context": context_text[:3000],
                },
                TopicClassificationLLMOutput,
            )
            if parsed is not None and used_llm and parsed.category in self.rules:
                return ClassificationResult(
                    category=parsed.category,
                    secondary_categories=parsed.secondary_categories,
                    rationale=parsed.rationale,
                    mode="llm",
                )

        corpus_lower = " ".join(
            [
                extracted.title,
                extracted.summary,
                " ".join(extracted.rules),
                " ".join(extracted.constraints),
                context_text[:2500],
            ]
        ).lower()

        scores: dict[str, int] = {}
        for cat, kws in self.rules.items():
            hits = sum(2 if kw in extracted.title.lower() else (1 if kw in corpus_lower else 0) for kw in kws)
            if hits > 0:
                scores[cat] = hits

        if not scores:
            return ClassificationResult(
                category="Procedure operative",
                rationale="Classificazione predefinita in assenza di keyword specifiche.",
                mode="deterministic",
            )

        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        primary = ordered[0][0]
        secondary = [c for c, _ in ordered[1:3]]
        return ClassificationResult(
            category=primary,
            secondary_categories=secondary,
            rationale=f"Classificato in '{primary}' tramite match semantico-lessicale (categorie secondarie: {', '.join(secondary) or 'nessuna'}).",
            mode="deterministic",
        )
