"""Advanced analyzers for professional sentiment analysis."""

import logging

logger = logging.getLogger(__name__)

# Lazy imports — heavy deps (spacy, torch, networkx) may not be installed
_IMPORTS = {
    "SentimentEnsemble": ".sentiment_ensemble",
    "AspectExtractor": ".aspect_extraction",
    "AspectSentimentAnalyzer": ".aspect_sentiment",
    "TopicAnalyzer": ".topic_nli",
    "DocumentClusterer": ".cluster",
    "SarcasmDetector": ".sarcasm",
    "EventExtractor": ".event_extractor",
    "NarrativeBuilder": ".narrative_builder",
    "ContradictionDetector": ".contradiction_detector",
    "EventGraph": ".event_graph",
    "ConfidenceCalibrator": ".confidence_calibrator",
    "SentimentForecaster": ".forecaster",
    "LLMJudge": ".llm_judge",
    "SourceInfluenceTracker": ".source_influence",
    "ActiveLearner": ".active_learner",
    # BRG RAMME pipeline
    "RiskAwareEnsemble": ".finance_pipeline",
    "RAMMEResult": ".finance_pipeline",
    "DriftDetector": ".drift_detector",
    "DriftReport": ".drift_detector",
    "compute_agreement": ".model_agreement",
    "AgreementStats": ".model_agreement",
}

__all__ = list(_IMPORTS.keys())

_loaded = {}

def __getattr__(name):
    if name in _IMPORTS:
        if name not in _loaded:
            import importlib
            try:
                mod = importlib.import_module(_IMPORTS[name], __package__)
                _loaded[name] = getattr(mod, name)
            except (ImportError, AttributeError) as e:
                logger.debug(f"Could not import {name}: {e}")
                raise ImportError(f"{name} requires missing dependency: {e}") from e
        return _loaded[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
