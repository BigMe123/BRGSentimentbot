"""
Dynamic Alpha Learning Module
Learns optimal blending weights based on risk features
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge, HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import json
from pathlib import Path
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


@dataclass
class AlphaDataPoint:
    """Historical data point for alpha learning"""
    country: str
    vintage_year: int      # When forecast was made
    target_year: int       # Year being forecast
    y_model: float         # Model prediction
    y_cons: float          # Consensus prediction
    y_actual: float        # Realized GDP growth
    feats: dict           # Risk features at vintage time


class DynamicAlphaLearner:
    """
    Learns dynamic alpha based on risk features
    Alpha determines model vs consensus weight
    """

    def __init__(self, cache_dir: str = "data/alpha_models"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self.feat_keys = []
        self.performance_history = []

        # Feature configuration
        self.feature_config = {
            # Model Uncertainty
            'model_conf': {'default': 0.5, 'scale': False},
            'resid_rolling_mae_4': {'default': 1.0, 'scale': True},

            # Consensus Risk
            'consensus_disp': {'default': 0.3, 'scale': True},
            'consensus_gap_prev': {'default': 0.5, 'scale': True},

            # Macro Volatility
            'pmi_var_6m': {'default': 5.0, 'scale': True},
            'fx_vol_3m': {'default': 0.1, 'scale': True},
            'oil_vol_3m': {'default': 0.2, 'scale': True},
            'yieldcurve_var_3m': {'default': 0.3, 'scale': True},

            # Country Structure
            'dm_flag': {'default': 1, 'scale': False},
            'oil_exporter': {'default': 0, 'scale': False},
            'china_exposure': {'default': 0.2, 'scale': False},
            'election_proximity': {'default': 0, 'scale': False}
        }

    def extract_features(self, country: str, vintage_date: datetime,
                        model_data: Dict, consensus_data: Dict,
                        market_data: Optional[Dict] = None) -> Dict[str, float]:
        """
        Extract risk features for alpha determination
        """
        features = {}

        # Model Uncertainty
        features['model_conf'] = model_data.get('confidence', 0.5)

        # Calculate rolling MAE if history available
        if 'history' in model_data:
            recent_errors = model_data['history'][-4:]
            if recent_errors:
                features['resid_rolling_mae_4'] = np.mean([abs(e) for e in recent_errors])
            else:
                features['resid_rolling_mae_4'] = 1.0
        else:
            features['resid_rolling_mae_4'] = 1.0

        # Consensus Risk
        if consensus_data and 'individual' in consensus_data:
            values = list(consensus_data['individual'].values())
            if len(values) > 1:
                features['consensus_disp'] = np.std(values)
            else:
                features['consensus_disp'] = 0.3
        else:
            features['consensus_disp'] = 0.3

        # Previous gap
        if 'previous_gap' in model_data:
            features['consensus_gap_prev'] = abs(model_data['previous_gap'])
        else:
            features['consensus_gap_prev'] = 0.5

        # Macro Volatility (from market data if available)
        if market_data:
            features['pmi_var_6m'] = market_data.get('pmi_variance', 5.0)
            features['fx_vol_3m'] = market_data.get('fx_volatility', 0.1)
            features['oil_vol_3m'] = market_data.get('oil_volatility', 0.2)
            features['yieldcurve_var_3m'] = market_data.get('yield_variance', 0.3)
        else:
            # Use defaults
            features['pmi_var_6m'] = 5.0
            features['fx_vol_3m'] = 0.1
            features['oil_vol_3m'] = 0.2
            features['yieldcurve_var_3m'] = 0.3

        # Country Structure
        dm_countries = ['USA', 'DEU', 'JPN', 'GBR', 'FRA', 'ITA', 'CAN', 'AUS']
        features['dm_flag'] = 1 if country in dm_countries else 0

        oil_exporters = ['RUS', 'SAU', 'NOR', 'CAN', 'MEX', 'NGA']
        features['oil_exporter'] = 1 if country in oil_exporters else 0

        # China exposure (high for Asian exporters)
        high_china_exposure = ['KOR', 'TWN', 'SGP', 'HKG', 'AUS', 'NZL']
        features['china_exposure'] = 0.5 if country in high_china_exposure else 0.2

        # Election proximity (simplified - would need real calendar)
        features['election_proximity'] = 0  # 0-1, closer to election = higher

        return features

    def _optimal_alpha(self, y_model: float, y_cons: float, y_actual: float) -> float:
        """
        Find optimal alpha that minimizes error vs actual
        """
        # Grid search for best alpha
        grid = np.linspace(0.0, 1.0, 101)
        errors = np.abs(y_actual - (grid * y_model + (1 - grid) * y_cons))
        return float(grid[np.argmin(errors)])

    def build_training_matrix(self, history_points: List[AlphaDataPoint]) -> Tuple:
        """
        Build feature matrix and optimal alpha targets
        """
        X, y = [], []

        # Get all unique feature keys
        feat_keys = sorted({k for p in history_points for k in p.feats.keys()})

        for point in history_points:
            if point.y_cons is None or point.y_model is None or point.y_actual is None:
                continue

            # Calculate optimal alpha for this historical point
            alpha_star = self._optimal_alpha(point.y_model, point.y_cons, point.y_actual)

            # Build feature vector
            x_vec = [point.feats.get(k, self.feature_config.get(k, {}).get('default', 0))
                     for k in feat_keys]

            X.append(x_vec)
            y.append(alpha_star)

        return np.array(X), np.array(y), feat_keys

    def train_alpha_model(self, history_points: List[AlphaDataPoint],
                         model_type: str = 'huber') -> Tuple:
        """
        Train model to predict optimal alpha from features
        Uses Huber loss for robustness to outliers (UK/KOR cases)
        """
        X, y, feat_keys = self.build_training_matrix(history_points)

        if len(X) < 10:
            print(f"Warning: Only {len(X)} training points, using fallback alpha")
            return None, feat_keys

        # Choose base model - default to Huber for outlier robustness
        if model_type == 'huber':
            # Huber regressor - robust to outliers with epsilon tuning
            base = HuberRegressor(
                epsilon=1.35,  # Standard value, robust to ~95% of outliers
                alpha=0.01,    # L2 regularization
                max_iter=1000,
                fit_intercept=True
            )
        elif model_type == 'gbr':
            # Keep original GBR option for comparison
            base = GradientBoostingRegressor(
                loss="absolute_error",
                max_depth=3,
                n_estimators=200,
                learning_rate=0.05,
                random_state=42
            )
        else:
            base = Ridge(alpha=1.0, random_state=42)

        # Pipeline with scaling
        model = Pipeline([
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            ("regressor", base)
        ])

        # Train
        model.fit(X, y)

        # Store for later use
        self.model = model
        self.feat_keys = feat_keys

        # Calculate training performance with robust metrics
        y_pred = model.predict(X)
        train_mae = np.mean(np.abs(y - y_pred))
        train_rmse = np.sqrt(np.mean((y - y_pred) ** 2))

        # Calculate Huber loss for comparison
        residuals = y - y_pred
        epsilon = 1.35 if model_type == 'huber' else 1.0
        huber_loss = np.mean(np.where(np.abs(residuals) <= epsilon,
                                     0.5 * residuals**2,
                                     epsilon * (np.abs(residuals) - 0.5 * epsilon)))

        print(f"Alpha model trained ({model_type}): MAE={train_mae:.3f}, "
              f"RMSE={train_rmse:.3f}, Huber={huber_loss:.3f}")

        return model, feat_keys

    def infer_alpha(self, feats_now: Dict[str, float],
                   min_alpha: float = 0.0, max_alpha: float = 0.90,
                   return_reasons: bool = False) -> Union[float, Tuple[float, List[str]]]:
        """
        Predict optimal alpha for current features

        Args:
            feats_now: Current risk features
            min_alpha: Minimum allowed alpha
            max_alpha: Maximum allowed alpha
            return_reasons: If True, return (alpha, reasons) tuple

        Returns:
            alpha or (alpha, reason_codes) if return_reasons=True
        """
        reasons = []

        if self.model is None:
            # Fallback to rule-based
            alpha, fallback_reasons = self._rule_based_alpha(feats_now)
            reasons.extend(fallback_reasons)
        else:
            reasons.append("ml_model_prediction")

            # Build feature vector
            x = np.array([[feats_now.get(k, self.feature_config.get(k, {}).get('default', 0))
                          for k in self.feat_keys]])

            # Predict
            alpha_hat = float(self.model.predict(x)[0])
            reasons.append(f"raw_alpha_{alpha_hat:.3f}")

            # AGGRESSIVE CONSENSUS BIAS: Default to consensus unless model is very confident
            # And shows clear directional advantage
            model_conf = feats_now.get('model_conf', 0.5)
            consensus_disp = feats_now.get('consensus_disp', 0.3)

            # NEAR-PURE CONSENSUS: Only use model in very rare cases
            # Essentially defaults to consensus (α ≈ 0) unless perfect conditions
            if model_conf < 0.9 or consensus_disp > 0.2:
                alpha_hat = alpha_hat * 0.01  # Essentially zero model weight
                reasons.append("consensus_default_mode")
            elif alpha_hat > 0.3:
                alpha_hat = alpha_hat * 0.2  # Still heavily discount
                reasons.append("minimal_model_signal")

            # Clip to bounds
            alpha_hat = np.clip(alpha_hat, 0.0, 1.0)

            # Add reasoning for alpha level
            if alpha_hat > 0.3:  # Lowered threshold
                reasons.append("moderate_model_weight")
            elif alpha_hat < 0.1:
                reasons.append("consensus_dominant")
            else:
                reasons.append("minimal_blending")

            # Apply guardrails
            alpha = float(np.clip(alpha_hat, min_alpha, max_alpha))

            # Note if bounds were hit
            if alpha == min_alpha and alpha_hat < min_alpha:
                reasons.append(f"min_bound_applied_{min_alpha}")
            elif alpha == max_alpha and alpha_hat > max_alpha:
                reasons.append(f"max_bound_applied_{max_alpha}")

        # Add feature-based reasoning
        self._add_feature_reasoning(feats_now, reasons)

        if return_reasons:
            return alpha, reasons
        return alpha

    def _add_feature_reasoning(self, feats: Dict[str, float], reasons: List[str]) -> None:
        """Add reasoning based on feature values"""

        # Model confidence reasoning
        conf = feats.get('model_conf', 0.5)
        if conf > 0.8:
            reasons.append("very_high_confidence")
        elif conf > 0.6:
            reasons.append("high_confidence")
        elif conf < 0.3:
            reasons.append("low_confidence")
        elif conf < 0.5:
            reasons.append("medium_confidence")

        # Consensus dispersion reasoning
        disp = feats.get('consensus_disp', 0.3)
        if disp > 0.6:
            reasons.append("high_consensus_disagreement")
        elif disp > 0.4:
            reasons.append("medium_consensus_disagreement")
        else:
            reasons.append("low_consensus_disagreement")

        # Macro volatility reasoning
        pmi_var = feats.get('pmi_var_6m', 5.0)
        if pmi_var > 12:
            reasons.append("very_high_macro_volatility")
        elif pmi_var > 8:
            reasons.append("high_macro_volatility")
        elif pmi_var < 4:
            reasons.append("low_macro_volatility")

        # Country type reasoning
        if feats.get('dm_flag', 1) == 1:
            reasons.append("developed_market")
        else:
            reasons.append("emerging_market")

        if feats.get('oil_exporter', 0) == 1:
            reasons.append("commodity_exporter")

        china_exp = feats.get('china_exposure', 0.2)
        if china_exp > 0.4:
            reasons.append("high_china_exposure")

    def _rule_based_alpha(self, feats: Dict[str, float]) -> Tuple[float, List[str]]:
        """
        Fallback rule-based alpha when no model available
        Returns alpha and reasoning codes
        """
        alpha = 0.0  # Pure consensus default
        reasons = ["fallback_rules", "pure_consensus_default"]

        # High model confidence -> trust model more
        if feats.get('model_conf', 0.5) > 0.8:  # Higher threshold
            alpha += 0.2
            reasons.append("high_confidence_boost")
        elif feats.get('model_conf', 0.5) < 0.3:
            alpha -= 0.05  # Keep low
            reasons.append("low_confidence_penalty")

        # High consensus dispersion -> be cautious
        if feats.get('consensus_disp', 0.3) > 0.5:
            alpha -= 0.05  # Keep minimal model weight
            reasons.append("high_dispersion_caution")

        # High macro volatility -> trust consensus more
        if feats.get('pmi_var_6m', 5) > 10:
            alpha -= 0.05
            reasons.append("high_volatility_conservative")

        # DM countries -> only slight model bias
        if feats.get('dm_flag', 1) == 1:
            alpha += 0.05  # Reduced from 0.1
            reasons.append("developed_market_bias")

        return np.clip(alpha, 0.0, 0.90), reasons

    def format_reason_codes(self, reason_codes: List[str]) -> str:
        """
        Format reason codes into human-readable explanation
        """
        if not reason_codes:
            return "No specific reasoning available"

        # Readable mappings
        reason_map = {
            'ml_model_prediction': 'ML model prediction',
            'fallback_rules': 'Rule-based fallback',
            'high_confidence': 'High model confidence',
            'very_high_confidence': 'Very high model confidence',
            'low_confidence': 'Low model confidence',
            'medium_confidence': 'Medium model confidence',
            'high_confidence_boost': 'Confidence boost applied',
            'low_confidence_penalty': 'Confidence penalty applied',
            'high_consensus_disagreement': 'High consensus disagreement',
            'medium_consensus_disagreement': 'Medium consensus disagreement',
            'low_consensus_disagreement': 'Low consensus disagreement',
            'high_dispersion_caution': 'Caution due to high dispersion',
            'high_macro_volatility': 'High macro volatility',
            'very_high_macro_volatility': 'Very high macro volatility',
            'low_macro_volatility': 'Low macro volatility',
            'high_volatility_conservative': 'Conservative due to volatility',
            'developed_market': 'Developed market',
            'emerging_market': 'Emerging market',
            'developed_market_bias': 'DM bias applied',
            'commodity_exporter': 'Commodity exporter',
            'high_china_exposure': 'High China exposure',
            'high_model_weight': 'High model weight (α>0.7)',
            'high_consensus_weight': 'High consensus weight (α<0.3)',
            'balanced_blending': 'Balanced model-consensus blend',
            'high_dispersion_low_confidence': 'High dispersion + low confidence → consensus',
            'persistent_large_gap': 'Persistent large gap → reduced weight',
            'election_uncertainty': 'Election uncertainty → conservative',
            'commodity_volatility': 'Commodity volatility → conservative',
            'crisis_mode_detected': 'Crisis mode → heavy consensus bias',
            'model_breakdown': 'Model breakdown → minimal model weight',
            'consensus_breakdown': 'Consensus breakdown → equal weighting',
            'em_stress_conditions': 'EM stress → conservative blending',
            'extreme_depression_cap': 'Extreme recession forecast capped',
            'extreme_boom_cap': 'Extreme growth forecast capped',
            'deep_recession_caution': 'Deep recession → consensus preference',
            'high_growth_outlier': 'High growth outlier → conservative'
        }

        # Convert to readable format
        readable_reasons = []
        for reason in reason_codes:
            if reason.startswith('raw_alpha_'):
                alpha_val = reason.split('_')[-1]
                readable_reasons.append(f"Raw α={alpha_val}")
            elif reason.startswith('min_bound_applied_'):
                bound_val = reason.split('_')[-1]
                readable_reasons.append(f"Min α={bound_val} applied")
            elif reason.startswith('max_bound_applied_'):
                bound_val = reason.split('_')[-1]
                readable_reasons.append(f"Max α={bound_val} applied")
            else:
                readable_reasons.append(reason_map.get(reason, reason.replace('_', ' ').title()))

        # Group into key categories for display
        key_reasons = []
        if any('ML model' in r or 'Raw α' in r for r in readable_reasons):
            key_reasons.append('🤖 ML-driven')
        if any('fallback' in r.lower() for r in readable_reasons):
            key_reasons.append('📋 Rule-based')
        if any('consensus' in r.lower() for r in readable_reasons):
            key_reasons.append('🎯 Consensus-aware')
        if any('volatility' in r.lower() or 'conservative' in r.lower() for r in readable_reasons):
            key_reasons.append('⚠️ Risk-adjusted')
        if any('crisis' in r.lower() or 'breakdown' in r.lower() or 'extreme' in r.lower() or 'cap' in r.lower() for r in readable_reasons):
            key_reasons.append('🚨 Guardrails')

        # Return compact summary with top 3 specific reasons
        summary = ' + '.join(key_reasons) if key_reasons else 'Standard'
        top_specifics = [r for r in readable_reasons if not any(x in r for x in ['ML model', 'fallback', 'Raw α'])][:3]

        if top_specifics:
            return f"{summary}: {', '.join(top_specifics)}"
        else:
            return summary

    def adjust_alpha_with_rules(self, alpha: float, feats: Dict[str, float]) -> Tuple[float, List[str]]:
        """
        Apply business rules and guardrails to alpha
        """
        reasons = []
        original_alpha = alpha

        # Rule 1: High dispersion + low confidence -> pull to consensus
        if feats.get('consensus_disp', 0) >= 0.7 and feats.get('model_conf', 1) < 0.4:
            alpha = min(alpha, 0.35)
            reasons.append("high_dispersion_low_confidence")

        # Rule 2: Very high macro volatility -> be conservative
        if feats.get('pmi_var_6m', 0) > 12:
            alpha = min(alpha, 0.45)
            reasons.append("high_macro_volatility")

        # Rule 3: Large previous gap that persisted -> reduce weight
        if feats.get('consensus_gap_prev', 0) > 1.5:
            alpha = max(alpha - 0.1, 0.2)
            reasons.append("persistent_large_gap")

        # Rule 4: Election proximity -> increase uncertainty
        if feats.get('election_proximity', 0) > 0.7:
            alpha = min(alpha, 0.5)
            reasons.append("election_uncertainty")

        # Rule 5: Oil exporter with high oil volatility
        if feats.get('oil_exporter', 0) == 1 and feats.get('oil_vol_3m', 0) > 0.3:
            alpha = min(alpha, 0.4)
            reasons.append("commodity_volatility")

        return alpha, reasons

    def apply_guardrails(self, y_model: float, y_consensus: float, alpha: float,
                        feats: Dict[str, float]) -> Tuple[float, float, List[str]]:
        """
        Apply extreme scenario guardrails to prevent unreasonable calibration

        Returns:
            (adjusted_alpha, adjusted_y_final, guardrail_reasons)
        """
        guardrail_reasons = []
        original_alpha = alpha

        # Calculate initial blend
        y_final = self.blend(y_model, y_consensus, alpha)

        # Guardrail 1: Extreme forecast gaps (>5pp difference)
        forecast_gap = abs(y_model - y_consensus) if y_consensus is not None else 0
        if forecast_gap > 5.0:
            # Force more conservative blending for extreme gaps
            alpha = min(alpha, 0.25)
            guardrail_reasons.append(f"extreme_gap_{forecast_gap:.1f}pp")

        # Guardrail 2: Negative growth predictions require extra caution
        if y_final < -2.0:
            # For deep recession predictions, trust consensus more
            alpha = min(alpha, 0.3)
            guardrail_reasons.append("deep_recession_caution")

        # Guardrail 3: Very high growth predictions (>6%) need validation
        if y_final > 6.0:
            # High growth outliers - be conservative
            alpha = min(alpha, 0.4)
            guardrail_reasons.append("high_growth_outlier")

        # Guardrail 4: Crisis mode detection
        crisis_indicators = 0
        if feats.get('pmi_var_6m', 0) > 15:
            crisis_indicators += 1
        if feats.get('fx_vol_3m', 0) > 0.25:
            crisis_indicators += 1
        if feats.get('consensus_disp', 0) > 0.8:
            crisis_indicators += 1
        if feats.get('model_conf', 1) < 0.25:
            crisis_indicators += 1

        if crisis_indicators >= 3:
            # Crisis mode - heavily favor consensus
            alpha = min(alpha, 0.2)
            guardrail_reasons.append("crisis_mode_detected")

        # Guardrail 5: Model breakdown detection
        if feats.get('model_conf', 1) < 0.15:
            # Model completely unreliable
            alpha = min(alpha, 0.1)
            guardrail_reasons.append("model_breakdown")

        # Guardrail 6: Consensus breakdown (extreme dispersion)
        if feats.get('consensus_disp', 0) > 1.2:
            # Consensus completely unreliable - fall back to simple average
            alpha = 0.5
            guardrail_reasons.append("consensus_breakdown")

        # Guardrail 7: Emerging market stress
        if (feats.get('dm_flag', 1) == 0 and
            feats.get('fx_vol_3m', 0) > 0.3 and
            forecast_gap > 3.0):
            alpha = min(alpha, 0.25)
            guardrail_reasons.append("em_stress_conditions")

        # Guardrail 8: Sanity check - prevent forecasts outside reasonable bounds
        y_final_adjusted = self.blend(y_model, y_consensus, alpha)

        if y_final_adjusted < -15.0:  # Extreme depression scenario
            # Cap at -12% and force consensus weight
            alpha = 0.1
            y_final_adjusted = self.blend(y_model, y_consensus, alpha)
            if y_final_adjusted < -12.0:
                y_final_adjusted = -12.0
            guardrail_reasons.append("extreme_depression_cap")

        elif y_final_adjusted > 15.0:  # Unrealistic boom scenario
            # Cap at 12% and force consensus weight
            alpha = 0.1
            y_final_adjusted = self.blend(y_model, y_consensus, alpha)
            if y_final_adjusted > 12.0:
                y_final_adjusted = 12.0
            guardrail_reasons.append("extreme_boom_cap")

        # Log guardrail activation
        if guardrail_reasons:
            alpha_change = abs(alpha - original_alpha)
            if alpha_change > 0.01:
                guardrail_reasons.append(f"alpha_adjusted_{original_alpha:.3f}_to_{alpha:.3f}")

        return alpha, y_final_adjusted, guardrail_reasons

    def blend(self, y_model: float, y_consensus: float, alpha: float) -> float:
        """
        Blend model and consensus predictions
        """
        if y_consensus is None:
            return y_model
        return alpha * y_model + (1 - alpha) * y_consensus

    def calculate_uncertainty_bands(self, y_central: float, feats: Dict[str, float],
                                   historical_std: float = 0.8,
                                   consensus_individual: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """
        Calculate dispersion-aware uncertainty bands
        Bands scale with consensus disagreement and macro volatility
        """
        # Base standard deviation from historical performance
        sigma_base = historical_std

        # Enhanced dispersion-aware scaling
        risk_multiplier = 1.0

        # Primary driver: consensus dispersion (more responsive scaling)
        consensus_disp = feats.get('consensus_disp', 0.3)
        if consensus_disp > 0.6:
            # High dispersion -> much wider bands
            risk_multiplier += 0.8 * consensus_disp
        elif consensus_disp > 0.4:
            # Medium dispersion -> moderate widening
            risk_multiplier += 0.5 * consensus_disp
        else:
            # Low dispersion -> slight widening
            risk_multiplier += 0.3 * consensus_disp

        # Direct consensus spread calculation if individual forecasts available
        if consensus_individual and len(consensus_individual) > 1:
            values = list(consensus_individual.values())
            consensus_spread = np.std(values)
            # Use the larger of feature-based or calculated dispersion
            effective_disp = max(consensus_disp, consensus_spread)
            risk_multiplier = 1.0 + 0.6 * effective_disp

        # Macro volatility amplifies uncertainty
        pmi_var = feats.get('pmi_var_6m', 5.0)
        if pmi_var > 10:
            risk_multiplier += 0.4 * (pmi_var / 10)  # High PMI volatility
        else:
            risk_multiplier += 0.2 * (pmi_var / 10)  # Normal scaling

        # Financial volatility
        fx_vol = feats.get('fx_vol_3m', 0.1)
        risk_multiplier += 0.3 * fx_vol  # More responsive to FX vol

        # Model confidence penalty (more aggressive)
        model_conf = feats.get('model_conf', 0.5)
        if model_conf < 0.3:
            risk_multiplier *= 1.4  # Low confidence -> much wider bands
        elif model_conf < 0.5:
            risk_multiplier *= 1.2  # Medium confidence -> wider bands

        # Country-specific adjustments
        if feats.get('dm_flag', 1) == 0:  # Emerging markets
            risk_multiplier *= 1.1

        if feats.get('oil_exporter', 0) == 1:  # Commodity exporters
            oil_vol = feats.get('oil_vol_3m', 0.2)
            risk_multiplier += 0.2 * oil_vol

        # Cap extreme multipliers
        risk_multiplier = min(risk_multiplier, 3.0)  # Max 3x base uncertainty

        sigma_t = sigma_base * risk_multiplier

        # Calculate percentiles with dispersion-aware asymmetry
        asymmetry_factor = 1.0
        if consensus_disp > 0.5:
            # High dispersion can create asymmetric uncertainty
            asymmetry_factor = 1.1

        return {
            'p10': round(y_central - 1.28 * sigma_t * asymmetry_factor, 2),
            'p20': round(y_central - 0.84 * sigma_t, 2),
            'p50': round(y_central, 2),
            'p80': round(y_central + 0.84 * sigma_t, 2),
            'p90': round(y_central + 1.28 * sigma_t, 2),
            'uncertainty': round(sigma_t, 2),
            'consensus_contribution': round(0.6 * consensus_disp, 3),
            'volatility_contribution': round(0.2 * (pmi_var / 10), 3),
            'confidence_penalty': round((2.0 - model_conf) * 0.1, 3) if model_conf < 0.5 else 0.0
        }

    def save_model(self, path: Optional[Path] = None):
        """Save trained model to disk"""
        if self.model is None:
            return

        if path is None:
            path = self.cache_dir / f"alpha_model_{datetime.now().strftime('%Y%m%d')}.pkl"

        import pickle
        with open(path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'feat_keys': self.feat_keys,
                'timestamp': datetime.now().isoformat()
            }, f)

        print(f"Model saved to {path}")

    def load_model(self, path: Optional[Path] = None):
        """Load trained model from disk"""
        if path is None:
            # Find latest model
            models = list(self.cache_dir.glob("alpha_model_*.pkl"))
            if not models:
                print("No saved models found")
                return False
            path = max(models)

        import pickle
        with open(path, 'rb') as f:
            data = pickle.load(f)
            self.model = data['model']
            self.feat_keys = data['feat_keys']
            print(f"Loaded model from {path}")
            return True


def generate_synthetic_history(countries: List[str], n_years: int = 5) -> List[AlphaDataPoint]:
    """
    Generate synthetic historical data for testing
    Based on known model performance characteristics
    """
    np.random.seed(42)
    history = []

    # Known characteristics
    country_profiles = {
        'USA': {'model_bias': -0.2, 'model_std': 0.5, 'consensus_std': 0.3},
        'DEU': {'model_bias': 0.1, 'model_std': 0.6, 'consensus_std': 0.3},
        'JPN': {'model_bias': -0.8, 'model_std': 0.8, 'consensus_std': 0.4},
        'GBR': {'model_bias': 1.0, 'model_std': 1.2, 'consensus_std': 0.4},
        'FRA': {'model_bias': -0.5, 'model_std': 0.7, 'consensus_std': 0.3},
        'KOR': {'model_bias': 1.2, 'model_std': 0.9, 'consensus_std': 0.4},
        'CHN': {'model_bias': 0.3, 'model_std': 0.8, 'consensus_std': 0.5},
        'IND': {'model_bias': -0.2, 'model_std': 1.0, 'consensus_std': 0.6}
    }

    for country in countries:
        if country not in country_profiles:
            continue

        profile = country_profiles[country]

        for year_offset in range(n_years):
            vintage_year = 2019 + year_offset
            target_year = vintage_year + 1

            # Generate actual GDP
            y_actual = np.random.normal(2.0, 1.5)

            # Generate model prediction with bias
            y_model = y_actual + profile['model_bias'] + np.random.normal(0, profile['model_std'])

            # Generate consensus (generally more accurate)
            y_cons = y_actual + np.random.normal(0, profile['consensus_std'])

            # Generate features
            feats = {
                'model_conf': np.random.uniform(0.3, 0.8),
                'resid_rolling_mae_4': abs(profile['model_bias']) + np.random.uniform(0, 0.5),
                'consensus_disp': np.random.uniform(0.2, 0.8),
                'consensus_gap_prev': abs(y_model - y_cons),
                'pmi_var_6m': np.random.uniform(3, 12),
                'fx_vol_3m': np.random.uniform(0.05, 0.25),
                'oil_vol_3m': np.random.uniform(0.1, 0.4),
                'yieldcurve_var_3m': np.random.uniform(0.1, 0.5),
                'dm_flag': 1 if country in ['USA', 'DEU', 'JPN', 'GBR', 'FRA'] else 0,
                'oil_exporter': 1 if country in ['RUS', 'SAU', 'NOR'] else 0,
                'china_exposure': 0.5 if country in ['KOR', 'AUS'] else 0.2,
                'election_proximity': np.random.uniform(0, 1)
            }

            history.append(AlphaDataPoint(
                country=country,
                vintage_year=vintage_year,
                target_year=target_year,
                y_model=y_model,
                y_cons=y_cons,
                y_actual=y_actual,
                feats=feats
            ))

    return history


def demo_dynamic_alpha():
    """Demonstrate dynamic alpha learning"""
    print("=" * 80)
    print("DYNAMIC ALPHA LEARNING DEMONSTRATION")
    print("=" * 80)

    # Generate synthetic history
    countries = ['USA', 'DEU', 'JPN', 'GBR', 'FRA', 'KOR']
    history = generate_synthetic_history(countries, n_years=5)

    # Initialize learner
    learner = DynamicAlphaLearner()

    # Train model
    print("\n1. Training Alpha Model on Historical Data")
    print("-" * 40)
    model, feat_keys = learner.train_alpha_model(history)

    # Test on new predictions
    print("\n2. Inferring Alpha for Current Predictions")
    print("-" * 40)

    test_scenarios = [
        {
            'country': 'USA',
            'feats': {'model_conf': 0.7, 'consensus_disp': 0.3, 'pmi_var_6m': 5, 'dm_flag': 1},
            'y_model': 2.1,
            'y_cons': 2.3
        },
        {
            'country': 'JPN',
            'feats': {'model_conf': 0.4, 'consensus_disp': 0.5, 'pmi_var_6m': 8, 'dm_flag': 1},
            'y_model': 0.5,
            'y_cons': 1.2
        },
        {
            'country': 'GBR',
            'feats': {'model_conf': 0.3, 'consensus_disp': 0.7, 'pmi_var_6m': 12, 'dm_flag': 1},
            'y_model': 3.0,
            'y_cons': 1.8
        }
    ]

    for scenario in test_scenarios:
        # Get alpha with full reasoning
        alpha, initial_reasons = learner.infer_alpha(scenario['feats'], return_reasons=True)
        alpha_adj, rule_reasons = learner.adjust_alpha_with_rules(alpha, scenario['feats'])
        all_reasons = initial_reasons + rule_reasons

        y_final = learner.blend(scenario['y_model'], scenario['y_cons'], alpha_adj)
        bands = learner.calculate_uncertainty_bands(y_final, scenario['feats'])

        # Format reasoning for display
        reason_summary = learner.format_reason_codes(all_reasons)

        print(f"\n{scenario['country']}:")
        print(f"  Features: conf={scenario['feats']['model_conf']:.1f}, "
              f"disp={scenario['feats'].get('consensus_disp', 0):.1f}, "
              f"pmi_var={scenario['feats'].get('pmi_var_6m', 0):.0f}")
        print(f"  Alpha: {alpha:.2f} → {alpha_adj:.2f}")
        print(f"  💡 Reasoning: {reason_summary}")
        if rule_reasons:
            print(f"  🔧 Rule adjustments: {', '.join(rule_reasons)}")
        print(f"  Forecast: model={scenario['y_model']:.1f}, cons={scenario['y_cons']:.1f}, "
              f"final={y_final:.2f}")
        print(f"  Uncertainty: [{bands['p10']:.1f}, {bands['p90']:.1f}] "
              f"(width={bands['p90']-bands['p10']:.1f})")
        print(f"  Risk breakdown: consensus={bands['consensus_contribution']:.2f}, "
              f"volatility={bands['volatility_contribution']:.2f}, "
              f"confidence_penalty={bands.get('confidence_penalty', 0):.2f}")

    # Save model
    print("\n3. Saving Model")
    print("-" * 40)
    learner.save_model()

    print("\n✅ Dynamic alpha learning complete!")


if __name__ == "__main__":
    demo_dynamic_alpha()