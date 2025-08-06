"""Time-series forecasting via a simple GAN model."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

import pandas as pd
import torch
from torch import nn


class Generator(nn.Module):
    """Tiny generator network for time-series GAN."""

    def __init__(self, noise_dim: int, hidden_dim: int, seq_len: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(noise_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, seq_len),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:  # pragma: no cover - simple wrapper
        return self.net(z)


class Discriminator(nn.Module):
    """Tiny discriminator network."""

    def __init__(self, seq_len: int, hidden_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(seq_len, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # pragma: no cover - simple wrapper
        return self.net(x)


@dataclass
class ForecastResult:
    """Forecast output with confidence bands."""

    forecast: pd.DataFrame


class TimeSeriesGAN:
    """Simple GAN for volatility forecasting.

    The model is intentionally lightweight so tests run quickly.
    """

    def __init__(
        self,
        seq_len: int = 10,
        noise_dim: int = 16,
        hidden_dim: int = 32,
        device: str | None = None,
    ) -> None:
        self.seq_len = seq_len
        self.noise_dim = noise_dim
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.gen = Generator(noise_dim, hidden_dim, seq_len).to(self.device)
        self.disc = Discriminator(seq_len, hidden_dim).to(self.device)
        self.gen_opt = torch.optim.Adam(self.gen.parameters(), lr=1e-3)
        self.disc_opt = torch.optim.Adam(self.disc.parameters(), lr=1e-3)
        self.history: List[float] = []

    def _create_sequences(self, data: torch.Tensor) -> torch.Tensor:
        seqs = []
        for i in range(len(data) - self.seq_len + 1):
            seqs.append(data[i : i + self.seq_len])
        return torch.stack(seqs)

    def fit(self, series: pd.Series, epochs: int = 100) -> "TimeSeriesGAN":
        """Train the GAN on a volatility series."""

        torch.manual_seed(0)
        data = torch.tensor(series.values, dtype=torch.float32, device=self.device)
        seqs = self._create_sequences(data)
        for epoch in range(epochs):
            # --- train discriminator
            z = torch.randn(len(seqs), self.noise_dim, device=self.device)
            fake = self.gen(z)
            real = seqs
            disc_loss = -(
                torch.log(self.disc(real) + 1e-8).mean()
                + torch.log(1 - self.disc(fake) + 1e-8).mean()
            )
            self.disc_opt.zero_grad()
            disc_loss.backward()
            self.disc_opt.step()

            # --- train generator
            z = torch.randn(len(seqs), self.noise_dim, device=self.device)
            fake = self.gen(z)
            gen_loss = -torch.log(self.disc(fake) + 1e-8).mean()
            self.gen_opt.zero_grad()
            gen_loss.backward()
            self.gen_opt.step()

            if epoch % 10 == 0:
                self.history.append(float(gen_loss.detach().cpu()))
        self.last_seq = data[-self.seq_len :].detach().cpu()
        return self

    def forecast(self, n_steps: int, samples: int = 100) -> ForecastResult:
        """Generate forecasts for ``n_steps`` ahead.

        The method samples ``samples`` future paths and returns mean with
        95% confidence bands.
        """

        self.gen.eval()
        paths = []
        base = self.last_seq.clone().to(self.device)
        for _ in range(samples):
            seq = base.clone()
            generated = []
            for _ in range(n_steps):
                z = torch.randn(1, self.noise_dim, device=self.device)
                step = self.gen(z)[0, -1]
                generated.append(step)
                seq = torch.cat([seq[1:], step.view(1)])
            paths.append(torch.stack(generated))
        paths_t = torch.stack(paths)  # (samples, n_steps)
        mean = paths_t.mean(dim=0).cpu().numpy()
        std = paths_t.std(dim=0).cpu().numpy()
        df = pd.DataFrame(
            {
                "mean": mean,
                "lower": mean - 1.96 * std,
                "upper": mean + 1.96 * std,
            }
        )
        return ForecastResult(df)
