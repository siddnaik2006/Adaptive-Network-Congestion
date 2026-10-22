"""Ridge autoregressive forecasting with empirical calibration-residual congestion risk estimation.

Inputs: Last 10 link utilization observations (window=10).
Outputs: Point forecast 5 samples ahead (horizon=5).
Risk: Empirical residual probability of exceeding congestion threshold (0.85).
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np

WINDOW = 10
HORIZON = 5
THRESHOLD = 0.85

def features(values: List[float]) -> np.ndarray:
    """Extract autoregressive features: intercept, lag window, recent slope, and window std."""
    x = np.asarray(values[-WINDOW:], dtype=float)
    if len(x) < WINDOW:
        x = np.pad(x, (WINDOW - len(x), 0), mode='edge')
    slope = x[-1] - x[-4] if len(x) >= 4 else 0.0
    return np.r_[1.0, x, slope, float(np.std(x))]

class Predictor:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.ready = self.path.exists()
        if self.ready:
            d = json.loads(self.path.read_text(encoding='utf-8'))
            self.weights = np.array(d['weights'])
            self.residuals = np.array(d['residuals'])
            self.metadata = d['metadata']
        else:
            self.weights = np.array([])
            self.residuals = np.array([])
            self.metadata = {
                'model': 'Ridge autoregressive forecast + empirical residual risk',
                'status': 'untrained',
                'description': 'Predictor not yet trained. Run python scripts/train.py or start server to train synthetic defaults.'
            }
            
    def predict(self, history: List[float]) -> Dict[str, Any]:
        """Produce point forecast and risk given recent utilization observations."""
        n_obs = len(history)
        if not self.ready or n_obs < WINDOW:
            return {
                'forecast': None,
                'risk': None,
                'status': f"warming up ({n_obs}/{WINDOW} samples)" if self.ready else 'untrained',
                'samples_collected': n_obs,
                'samples_required': WINDOW,
            }
        forecast = float(np.clip(features(history) @ self.weights, 0.0, 1.5))
        risk = float(np.mean(forecast + self.residuals >= THRESHOLD))
        return {
            'forecast': round(forecast, 4),
            'risk': round(risk, 4),
            'status': 'ready',
            'samples_collected': n_obs,
            'samples_required': WINDOW,
        }

def train(sequences: List[List[float]], path: Path, provenance: str) -> Dict[str, Any]:
    """Train Ridge autoregressive model, compute empirical calibration residuals, and evaluate test split."""
    if len(sequences) < 6:
        raise ValueError('At least six independent sequences required for train/calibration/test splits')
        
    def samples(seq_list: List[List[float]]) -> Tuple[np.ndarray, np.ndarray]:
        X, y = [], []
        for a in seq_list:
            for t in range(WINDOW, len(a) - HORIZON):
                X.append(features(a[t - WINDOW:t]))
                y.append(a[t + HORIZON - 1])
        if not X:
            raise ValueError('Sequences must have at least 16 observations')
        return np.array(X), np.array(y)
        
    n = len(sequences)
    cut = max(2, int(n * 0.6))
    cal = max(cut + 1, int(n * 0.8))
    
    X, y = samples(sequences[:cut])
    C, cy = samples(sequences[cut:cal])
    T, ty = samples(sequences[cal:])
    
    # Ridge regression with L2 regularization (excluding intercept)
    regularizer = np.eye(X.shape[1]) * 0.03
    regularizer[0, 0] = 0.0
    weights = np.linalg.solve(X.T @ X + regularizer, X.T @ y)
    
    # Calibration residuals: error between actual and predicted utilization on calibration set
    residuals = cy - np.clip(C @ weights, 0.0, 1.5)
    
    # Test set evaluation
    pred = np.clip(T @ weights, 0.0, 1.5)
    risks = np.mean(pred[:, None] + residuals[None, :] >= THRESHOLD, axis=1)
    actual_congestion = ty >= THRESHOLD
    predicted_congestion = risks >= 0.6
    
    tp = int(np.sum(actual_congestion & predicted_congestion))
    fp = int(np.sum(~actual_congestion & predicted_congestion))
    fn = int(np.sum(actual_congestion & ~predicted_congestion))
    
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    mae = float(np.mean(np.abs(pred - ty)))
    rmse = float(np.sqrt(np.mean((pred - ty) ** 2)))
    
    meta = {
        'model': 'Ridge autoregressive forecast + empirical residual risk',
        'algorithm_family': 'Linear autoregression with L2 shrinkage and empirical residual bootstrap',
        'provenance': provenance,
        'window_samples': WINDOW,
        'horizon_samples': HORIZON,
        'sample_seconds': 1,
        'congestion_threshold': THRESHOLD,
        'split': 'Independent sequences: 60% train / 20% calibration / 20% test',
        'train_samples': int(len(y)),
        'calibration_samples': int(len(cy)),
        'test_samples': int(len(ty)),
        'mae': round(mae, 4),
        'rmse': round(rmse, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'disclaimer': 'Holdout RMSE/MAE measures forecasting accuracy on test sequences. F1 measures threshold classification (>= 0.85). Not a guarantee of route optimality under unexpected network failures.',
    }
    
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({'weights': weights.tolist(), 'residuals': residuals.tolist(), 'metadata': meta}, indent=2),
        encoding='utf-8'
    )
    return meta

def synthetic_sequences(seed: int = 42, count: int = 36) -> List[List[float]]:
    """Generate realistic synthetic traffic utilization sequences for baseline demonstration."""
    rng = np.random.default_rng(seed)
    result = []
    for i in range(count):
        t = np.arange(160)
        start = float(rng.uniform(0.1, 0.4))
        peak = float(rng.uniform(0.88, 1.25))
        a = np.full(160, start, dtype=float)
        begin = int(rng.integers(20, 45))
        duration = int(rng.integers(25, 50))
        if i % 3 == 0:
            a[begin:begin + duration] = np.linspace(start, peak, duration)
            a[begin + duration:begin + duration + 30] = peak
        elif i % 3 == 1:
            a[begin:begin + duration] = peak
        else:
            a = start + 0.22 * np.sin(t / 15.0) + np.linspace(0.0, 0.65, 160)
        noise = rng.normal(0.0, 0.025, 160)
        result.append(np.clip(a + noise, 0.0, 1.5).tolist())
    return result
