"""Response schema for `GET /api/v1/model-info` (PRD §15, Phase 4 M2).

Everything here is read from the committed bundle manifest, so the endpoint cannot
drift from the model that is actually loaded. Scores are decision margins, never
probabilities.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ModelInfoResponse(BaseModel):
    """What the loaded model is, what it was trained on, and how it scores."""

    # Field names deliberately start with `model_`, so the Pydantic namespace must
    # not treat them as reserved.
    model_config = ConfigDict(protected_namespaces=())

    model_name: str = Field(description="Selected classical classifier, e.g. 'svm'.")
    model_version: str = Field(description="Bundle-derived model version, e.g. 'svm-v1.0.0'.")
    bundle_version: str = Field(description="Version of the exported artifact bundle.")
    bundle_exported_at: str = Field(description="UTC timestamp of the bundle export.")

    feature_set_version: str = Field(description="Versioned feature schema the model expects.")
    feature_count: int = Field(description="Number of ordered input features.")
    classes: list[str] = Field(description="Disease labels the model can return.")

    segmentation_config_version: str
    quality_config_version: str
    dataset_version: str
    split_protocol: str
    training_rows: int = Field(description="Development rows used to fit the model.")

    cv_macro_f1_mean: float
    cv_macro_f1_std: float
    cv_accuracy_mean: float
    cv_balanced_accuracy_mean: float

    held_out_rows: int = Field(description="Held-out images used for the single final evaluation.")
    held_out_macro_f1: float
    held_out_accuracy: float
    held_out_status: str = Field(
        description="States that the held-out evaluation happened once, after selection."
    )

    calibrated_probabilities: bool = Field(
        description="False: the bundle exposes decision_function, not probabilities."
    )
    score_kind: str = Field(description="How to read the score, e.g. 'decision_margin'.")
    score_note: str = Field(description="Plain-language explanation of the score.")

    severity_disclaimer: str = Field(
        description="Disclaimer that must accompany any severity display."
    )
    known_failure_cases: list[str] = Field(
        description="Documented limitations carried from the model manifest."
    )
