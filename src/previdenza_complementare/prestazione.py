"""In pensione: durata della vita, rendita vitalizia, capitale e rendita a durata definita."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import normativa as nv
from .mercato import IpotesiMercato

B_GOMPERTZ = 0.105
SPERANZA_67 = {"M": 18.2, "F": 21.0}  # speranza di vita a 67 anni nella popolazione italiana, circa 2025
MIGLIORAMENTO_ANNUO = 0.10  # anni di speranza di vita guadagnati ogni anno di calendario
SELEZIONE_ASSICURATI = 2.5  # anni in più nelle tavole usate dalle compagnie per le rendite


def _sopravvivenza(a: float, eta: float, t: np.ndarray, b: float = B_GOMPERTZ) -> np.ndarray:
    return np.exp(-a * np.exp(b * eta) * (np.exp(b * t) - 1) / b)


def speranza(a: float, eta: float, b: float = B_GOMPERTZ) -> float:
    t = np.arange(0, 70, 0.05)
    return float(np.trapezoid(_sopravvivenza(a, eta, t, b), t))


def calibra(speranza_obiettivo: float, eta: float = 67.0, b: float = B_GOMPERTZ) -> float:
    """Parametro `a` della legge di Gompertz che dà la speranza di vita voluta a `eta` anni."""
    lo, hi = 1e-9, 1e-2
    for _ in range(100):
        m = np.sqrt(lo * hi)
        if speranza(m, eta, b) > speranza_obiettivo:
            lo = m
        else:
            hi = m
    return float(np.sqrt(lo * hi))


@dataclass
class Mortalita:
    """Legge di Gompertz calibrata sulla speranza di vita a 67 anni nell'anno del pensionamento."""

    sesso: str = "F"
    anni_da_oggi: float = 0.0
    assicurati: bool = False

    @property
    def a(self) -> float:
        e = SPERANZA_67[self.sesso] + MIGLIORAMENTO_ANNUO * self.anni_da_oggi
        return calibra(e + (SELEZIONE_ASSICURATI if self.assicurati else 0.0))

    def sopravvivenza(self, eta: float, anni: np.ndarray) -> np.ndarray:
        return _sopravvivenza(self.a, eta, np.asarray(anni, dtype=float))

    def speranza(self, eta: float) -> float:
        return speranza(self.a, eta)

    def campiona(self, eta: float, n: int, rng: np.random.Generator) -> np.ndarray:
        """Anni di vita residui (continui) di `n` persone di `eta` anni."""
        u = rng.uniform(size=n)
        ae = self.a * np.exp(B_GOMPERTZ * eta)
        return np.log(1 - B_GOMPERTZ * np.log(u) / ae) / B_GOMPERTZ


@dataclass
class IpotesiRendita:
    tasso_tecnico: float = 0.0
    caricamento: float = 0.015  # costo di conversione in rendita
    rivalutazione: float = 0.015  # rivalutazione annua nominale della rendita (gestione separata, al netto)
    azioni_capitale: float = 0.4  # quota azionaria del capitale gestito in proprio
    costo_capitale: float = 0.004  # TER e bollo del capitale gestito in proprio
    quota_capitale: float = nv.QUOTA_CAPITALE_MAX


def fattore_rendita(eta: float, mortalita: Mortalita, ip: IpotesiRendita) -> float:
    """Capitale necessario per 1 € di rendita annua vitalizia (pagata a inizio anno), con caricamento."""
    t = np.arange(0, 60)
    s = mortalita.sopravvivenza(eta, t)
    return float(np.sum(s / (1 + ip.tasso_tecnico) ** t) * (1 + ip.caricamento))


@dataclass
class Opzione:
    nome: str
    descrizione: str
    reddito: np.ndarray  # reddito netto reale per scenario e anno (scenari × anni)
    eredita: np.ndarray  # capitale lasciato agli eredi alla morte (reale)
    vita: np.ndarray  # anni di vita residui
    capitale_iniziale: float  # capitale netto incassato subito
    reddito_iniziale: float  # reddito netto del primo anno
    esaurito: np.ndarray  # True se la parte gestita in proprio finisce quando la persona è ancora in vita

    def sintesi(self) -> dict:
        anni = self.reddito.shape[1]
        vivo = np.arange(anni)[None, :] < self.vita[:, None]
        return {
            "Reddito netto iniziale": self.reddito_iniziale,
            "Capitale subito": self.capitale_iniziale,
            "Reddito medio da vivo": float(np.sum(self.reddito * vivo) / np.sum(vivo)),
            "Totale incassato medio": float(np.mean(np.sum(self.reddito * vivo, axis=1))) + self.capitale_iniziale,
            "Probabilità di esaurire il capitale": float(np.mean(self.esaurito)),
            "Eredità media": float(np.mean(self.eredita)),
        }


def opzioni(montante: float, quota_imponibile: float, aliquota: float, eta: float, sesso: str, anni_da_oggi: float,
            ip: IpotesiRendita | None = None, mercato: IpotesiMercato | None = None, n: int = 2_000,
            seme: int = 11) -> list[Opzione]:
    """Confronta rendita vitalizia, capitale e rendita, rendita a durata definita per un montante lordo."""
    ip = ip or IpotesiRendita()
    mercato = mercato or IpotesiMercato()
    rng = np.random.default_rng(seme)
    mort_pop = Mortalita(sesso, anni_da_oggi)
    mort_ass = Mortalita(sesso, anni_da_oggi, assicurati=True)
    vita = mort_pop.campiona(eta, n, rng)
    H = int(min(110 - eta, 50))
    t = np.arange(H)
    # mercati in pensione
    z = rng.standard_normal((n, H, 2))
    c = np.linalg.cholesky(np.array([[1.0, mercato.correlazione], [mercato.correlazione, 1.0]]))
    z = z @ c.T
    def _lognorm(m, s, k):
        s2 = np.log(1 + s**2 / (1 + m) ** 2)
        return np.exp(np.log(1 + m) - s2 / 2 + np.sqrt(s2) * z[:, :, k]) - 1
    r_az, r_ob = _lognorm(mercato.azioni, mercato.vol_azioni, 0), _lognorm(mercato.obbligazioni,
                                                                           mercato.vol_obbligazioni, 1)
    infl = mercato.inflazione + mercato.vol_inflazione * rng.standard_normal((n, H)) * 0.6
    P = np.cumprod(1 + infl, axis=1) / (1 + infl)  # indice a inizio anno
    tax = nv.aliquota_rendimenti(0.6 * (1 - ip.azioni_capitale), nv.ALIQUOTA_REDDITI_FINANZIARI)

    def _gestito(cap0: float, prelievo_reale: float | None, azioni: float, durata: int | None = None):
        """Capitale investito con prelievi a inizio anno; `durata` = rata residuo/anni rimanenti."""
        cap = np.full(n, cap0)
        red = np.zeros((n, H))
        ered = np.zeros(n)
        morto = np.zeros(n, dtype=bool)
        esaurito = np.zeros(n, dtype=bool)
        for k in range(H):
            vivo = vita > k
            ered = np.where(~vivo & ~morto, cap / P[:, k], ered)
            morto |= ~vivo
            if durata is not None:
                rest = max(durata - k, 0)
                p = np.where(rest > 0, cap / max(rest, 1), 0.0)
            else:
                p = np.minimum(prelievo_reale * P[:, k], cap)
            p = np.where(vivo, p, 0.0)
            esaurito |= vivo & (cap <= 1e-6 * max(cap0, 1.0))
            cap = cap - p
            red[:, k] = p / P[:, k]
            rend = azioni * r_az[:, k] + (1 - azioni) * r_ob[:, k] - ip.costo_capitale
            cap = cap * (1 + rend * np.where(rend > 0, 1 - tax, 1.0))
        ered = np.where(~morto, cap / P[:, -1], ered)
        return red, ered, esaurito

    def _rendita(cap: float):
        r0 = cap / fattore_rendita(eta, mort_ass, ip)
        nominale = r0 * (1 + ip.rivalutazione) ** t
        red = (nominale[None, :] / P) * (t[None, :] < vita[:, None])
        return red, r0

    netto_quota = 1 - aliquota * quota_imponibile
    out = []
    red, r0 = _rendita(montante)
    out.append(Opzione("Rendita vitalizia", "Tutto il montante convertito in rendita vitalizia rivalutabile",
                       red * netto_quota, np.zeros(n), vita, 0.0, r0 * netto_quota, np.zeros(n, dtype=bool)))
    q = ip.quota_capitale
    red_r, r0b = _rendita(montante * (1 - q))
    cap_netto = montante * q * netto_quota
    red_c, ered_c, es_c = _gestito(cap_netto, r0b * netto_quota * q / (1 - q), ip.azioni_capitale)
    out.append(Opzione(f"{q:.0%} capitale e {1 - q:.0%} rendita".replace(".", ","),
                       "Capitale investito (40% azioni) con prelievi pari alla rendita che avrebbe comprato",
                       red_r * netto_quota + red_c, ered_c, vita, 0.0, r0b * netto_quota / (1 - q), es_c))
    durata = int(round(mort_pop.speranza(eta)))
    red_d, ered_d, es_d = _gestito(montante, None, 0.25, durata=durata)
    out.append(Opzione("Rendita a durata definita",
                       f"Rata pari al residuo diviso per gli anni rimanenti, per {durata} anni (la speranza di vita); "
                       "il residuo resta investito e va agli eredi",
                       red_d * netto_quota, ered_d * netto_quota, vita, 0.0, float(red_d[0, 0]) * netto_quota,
                       es_d))
    return out
