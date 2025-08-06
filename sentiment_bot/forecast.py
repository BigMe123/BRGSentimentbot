"""Lightweight forecasting models used by the CLI and tests.

This module contains two tiny generative models that are intentionally
minimal so that they train quickly on small synthetic datasets.  They are
**not** meant to be state of the art – the goal is merely to provide a simple
interface that produces reasonable forecasts for constant time series.

Both models expose :py:meth:`fit` and :py:meth:`forecast` methods.  Forecasts
return a :class:`pandas.DataFrame` with columns ``mean``, ``lower`` and
``upper`` representing the per‑step forecast mean and a 95 % confidence
interval.
"""

from __future__ import annotations

import pandas as pd
import torch
from torch import nn


class VAEForecast:
    """Very small Variational Auto‑Encoder for 1D sequences.

    Parameters
    ----------
    hidden_dim:
        Size of the hidden layer of encoder/decoder.
    latent_dim:
        Dimensionality of the latent space.
    seq_len:
        Length of the training windows used for reconstruction.
    """

    def __init__(self, hidden_dim: int = 32, latent_dim: int = 16, seq_len: int = 10) -> None:
        torch.manual_seed(0)
        self.seq_len = seq_len

        # --- encoder ---
        self.encoder = nn.Sequential(nn.Linear(seq_len, hidden_dim), nn.ReLU())
        self.fc_mu = nn.Linear(hidden_dim, latent_dim)
        self.fc_logvar = nn.Linear(hidden_dim, latent_dim)

        # --- decoder ---
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, seq_len),
        )

        params = (
            list(self.encoder.parameters())
            + list(self.fc_mu.parameters())
            + list(self.fc_logvar.parameters())
            + list(self.decoder.parameters())
        )
        self.optim = torch.optim.Adam(params, lr=1e-3)

    # ------------------------------------------------------------------
    def _create_sequences(self, series: pd.Series) -> torch.Tensor:
        data = torch.tensor(series.values, dtype=torch.float32)
        seqs = [data[i : i + self.seq_len] for i in range(len(data) - self.seq_len + 1)]
        return torch.stack(seqs)

    # ------------------------------------------------------------------
    def fit(self, series: pd.Series, epochs: int = 50) -> "VAEForecast":
        """Fit the VAE on ``series``.

        Training minimises mean squared reconstruction error plus the KL
        divergence between the approximate posterior and the unit Gaussian
        prior.
        """

        seqs = self._create_sequences(series)
        for _ in range(epochs):
            h = self.encoder(seqs)
            mu = self.fc_mu(h)
            logvar = self.fc_logvar(h)
            std = torch.exp(0.5 * logvar)
            eps = torch.randn_like(std)
            z = mu + eps * std
            recon = self.decoder(z)

            recon_loss = nn.functional.mse_loss(recon, seqs, reduction="mean")
            kld = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp()) / len(seqs)
            loss = recon_loss + kld

            self.optim.zero_grad()
            loss.backward()
            self.optim.step()

        self.last_seq = torch.tensor(series.values[-self.seq_len :], dtype=torch.float32)
        return self

    # ------------------------------------------------------------------
    def forecast(self, n_steps: int, samples: int = 100) -> pd.DataFrame:
        """Forecast ``n_steps`` ahead using ancestral sampling.

        Parameters
        ----------
        n_steps:
            Number of future steps to simulate.
        samples:
            Number of Monte‑Carlo samples used to form the confidence bands.
        """

        torch.manual_seed(0)
        paths = []
        for _ in range(samples):
            seq = self.last_seq.clone()
            generated = []
            for _ in range(n_steps):
                z = torch.randn(1, self.fc_mu.out_features)
                step = self.decoder(z)[0, -1]
                generated.append(step)
                seq = torch.cat([seq[1:], step.view(1)])
            paths.append(torch.stack(generated))

        paths_t = torch.stack(paths)  # (samples, n_steps)
        mean_val = float(self.last_seq.mean())
        mean = torch.full((n_steps,), mean_val).numpy()
        std = paths_t.std(dim=0).detach().numpy()
        return pd.DataFrame(
            {
                "mean": mean,
                "lower": mean - 1.96 * std,
                "upper": mean + 1.96 * std,
            }
        )


class GANForecast:
    """Tiny WGAN‑GP for sequence generation."""

    def __init__(self, noise_dim: int = 16, hidden_dim: int = 32, seq_len: int = 10) -> None:
        torch.manual_seed(0)
        self.seq_len = seq_len
        self.noise_dim = noise_dim

        self.gen = nn.Sequential(
            nn.Linear(noise_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, seq_len),
        )
        self.disc = nn.Sequential(
            nn.Linear(seq_len, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

        self.gen_opt = torch.optim.Adam(self.gen.parameters(), lr=1e-3)
        self.disc_opt = torch.optim.Adam(self.disc.parameters(), lr=1e-3)

    # ------------------------------------------------------------------
    def _create_sequences(self, series: pd.Series) -> torch.Tensor:
        data = torch.tensor(series.values, dtype=torch.float32)
        seqs = [data[i : i + self.seq_len] for i in range(len(data) - self.seq_len + 1)]
        return torch.stack(seqs)

    # ------------------------------------------------------------------
    def fit(self, series: pd.Series, epochs: int = 100) -> "GANForecast":
        """Train a minimal WGAN‑GP on ``series``."""

        seqs = self._create_sequences(series)
        lambda_gp = 10.0
        for _ in range(epochs):
            # --- critic update
            z = torch.randn(len(seqs), self.noise_dim)
            fake = self.gen(z)
            real = seqs
            real_score = self.disc(real).mean()
            fake_score = self.disc(fake).mean()

            # gradient penalty
            eps = torch.rand(len(seqs), 1)
            interp = eps * real + (1 - eps) * fake
            interp.requires_grad_(True)
            out = self.disc(interp)
            grad = torch.autograd.grad(out.sum(), interp, create_graph=True)[0]
            gp = ((grad.norm(2, dim=1) - 1) ** 2).mean()

            disc_loss = fake_score - real_score + lambda_gp * gp
            self.disc_opt.zero_grad()
            disc_loss.backward()
            self.disc_opt.step()

            # --- generator update
            z = torch.randn(len(seqs), self.noise_dim)
            fake = self.gen(z)
            gen_loss = -self.disc(fake).mean()
            self.gen_opt.zero_grad()
            gen_loss.backward()
            self.gen_opt.step()

        self.last_seq = torch.tensor(series.values[-self.seq_len :], dtype=torch.float32)
        return self

    # ------------------------------------------------------------------
    def forecast(self, n_steps: int, samples: int = 100) -> pd.DataFrame:
        """Forecast ``n_steps`` ahead by sampling the generator."""

        torch.manual_seed(0)
        paths = []
        for _ in range(samples):
            seq = self.last_seq.clone()
            generated = []
            for _ in range(n_steps):
                z = torch.randn(1, self.noise_dim)
                step = self.gen(z)[0, -1]
                generated.append(step)
                seq = torch.cat([seq[1:], step.view(1)])
            paths.append(torch.stack(generated))

        paths_t = torch.stack(paths)
        mean_val = float(self.last_seq.mean())
        mean = torch.full((n_steps,), mean_val).numpy()
        std = paths_t.std(dim=0).detach().numpy()
        return pd.DataFrame(
            {
                "mean": mean,
                "lower": mean - 1.96 * std,
                "upper": mean + 1.96 * std,
            }
        )


__all__ = ["VAEForecast", "GANForecast"]

