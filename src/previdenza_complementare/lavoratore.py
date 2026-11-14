"""Il lavoratore: carriera, stipendio netto e pensione pubblica con il sistema contributivo."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import normativa as nv


@dataclass
class Lavoratore:
    """Un dipendente del settore privato. Gli importi sono in euro di oggi; la crescita della RAL è reale."""

    nome: str
    eta: float
    ral: float
    eta_pensione: float = 67.0
    sesso: str = "F"
    anni_contributi: float = 0.0
    crescita_reale: float = 0.01
    eta_fine_crescita: float = 55.0
    montante_inps: float | None = None  # se manca è stimato dagli anni di contributi
    tfr_pregresso: float = 0.0  # TFR già maturato e rimasto in azienda
    anni_tfr_pregresso: float = 0.0
    tasso_sostituzione_obiettivo: float = 0.80  # reddito netto desiderato in pensione, in % dell'ultimo netto
    crescita_pil_reale: float = 0.008  # rivalutazione reale del montante contributivo
    riduzione_coefficienti: float = 0.004  # riduzione annua dei coefficienti con la speranza di vita
    densita_contributiva: float = 1.0  # quota dei contributi pieni versati negli anni futuri (part-time, pause)

    def __post_init__(self) -> None:
        if self.eta_pensione <= self.eta:
            raise ValueError("L'età di pensionamento deve essere successiva all'età attuale")
        if self.sesso not in ("F", "M"):
            raise ValueError("sesso deve essere 'F' o 'M'")

    @property
    def anni(self) -> int:
        """Anni interi che mancano al pensionamento."""
        return int(round(self.eta_pensione - self.eta))

    def ral_percorso(self) -> np.ndarray:
        """RAL reale per ogni anno da oggi al pensionamento (lunghezza `anni`)."""
        eta = self.eta + np.arange(self.anni)
        anni_crescita = np.clip(eta - self.eta, 0, max(self.eta_fine_crescita - self.eta, 0))
        return self.ral * (1 + self.crescita_reale) ** anni_crescita

    @property
    def ultima_ral(self) -> float:
        return float(self.ral_percorso()[-1])

    def stima_montante_inps(self) -> float:
        """Montante contributivo accumulato finora, se non è dato: 33% di una RAL che è cresciuta come previsto."""
        if self.montante_inps is not None:
            return self.montante_inps
        n = int(round(self.anni_contributi))
        if n <= 0:
            return 0.0
        passati = self.ral / (1 + self.crescita_reale) ** np.arange(n, 0, -1)
        riv = (1 + self.crescita_pil_reale) ** np.arange(n - 1, -1, -1)
        return float(np.sum(nv.ALIQUOTA_IVS * passati * riv))

    def pensione_inps(self) -> dict:
        """Pensione pubblica stimata con il sistema contributivo, in euro di oggi."""
        ral = self.ral_percorso()
        g = self.crescita_pil_reale
        montante = self.stima_montante_inps() * (1 + g) ** self.anni
        riv = (1 + g) ** np.arange(self.anni - 1, -1, -1)
        montante += float(np.sum(nv.ALIQUOTA_IVS * self.densita_contributiva * ral * riv))
        coeff = nv.coefficiente_trasformazione(self.eta_pensione, self.anni, self.riduzione_coefficienti)
        lorda = montante * coeff
        netta = lorda - nv.imposte_pensione(lorda)
        ultimo_netto = nv.stipendio_netto(ral[-1])
        obiettivo = self.tasso_sostituzione_obiettivo * ultimo_netto
        return {
            "montante": montante, "coefficiente": coeff, "lorda": lorda, "netta": netta,
            "ultima_ral": float(ral[-1]), "ultimo_netto": ultimo_netto,
            "sostituzione_lorda": lorda / ral[-1], "sostituzione_netta": netta / ultimo_netto,
            "obiettivo": obiettivo, "gap": max(obiettivo - netta, 0.0),
            "anni_contributi": self.anni_contributi + self.anni * self.densita_contributiva,
        }
