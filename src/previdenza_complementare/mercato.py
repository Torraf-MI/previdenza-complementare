"""Mercati: scenari di rendimento di azioni e obbligazioni, inflazione e percorsi di investimento (comparti)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class IpotesiMercato:
    """Rendimenti nominali annui attesi (media aritmetica), volatilità e inflazione."""

    azioni: float = 0.065
    vol_azioni: float = 0.16
    obbligazioni: float = 0.03
    vol_obbligazioni: float = 0.055
    correlazione: float = 0.15
    inflazione: float = 0.02
    vol_inflazione: float = 0.01
    persistenza_inflazione: float = 0.6
    liquidita_spread: float = 0.0025  # rendimento del conto deposito sopra l'inflazione


@dataclass
class Scenari:
    """Rendimenti nominali annui (scenari × anni) e inflazione."""

    azioni: np.ndarray
    obbligazioni: np.ndarray
    inflazione: np.ndarray
    liquidita: np.ndarray

    @property
    def n(self) -> int:
        return self.azioni.shape[0]

    @property
    def anni(self) -> int:
        return self.azioni.shape[1]

    def indice_prezzi(self) -> np.ndarray:
        """Indice dei prezzi alla fine di ogni anno (scenari × anni), base 1 oggi."""
        return np.cumprod(1 + self.inflazione, axis=1)


def genera_scenari(ip: IpotesiMercato, anni: int, n: int = 2_000, seme: int = 7) -> Scenari:
    """Rendimenti lognormali correlati di azioni e obbligazioni e inflazione AR(1)."""
    rng = np.random.default_rng(seme)
    z = rng.standard_normal((n, anni, 2))
    c = np.array([[1.0, ip.correlazione], [ip.correlazione, 1.0]])
    z = z @ np.linalg.cholesky(c).T
    out = []
    for k, (m, s) in enumerate(((ip.azioni, ip.vol_azioni), (ip.obbligazioni, ip.vol_obbligazioni))):
        s2 = np.log(1 + s**2 / (1 + m) ** 2)
        mu = np.log(1 + m) - s2 / 2
        out.append(np.exp(mu + np.sqrt(s2) * z[:, :, k]) - 1)
    eps = rng.standard_normal((n, anni)) * ip.vol_inflazione * np.sqrt(1 - ip.persistenza_inflazione**2)
    infl = np.empty((n, anni))
    prec = np.full(n, ip.inflazione)
    for t in range(anni):
        prec = ip.inflazione + ip.persistenza_inflazione * (prec - ip.inflazione) + eps[:, t]
        infl[:, t] = prec
    return Scenari(out[0], out[1], infl, infl + ip.liquidita_spread)


def scenario_atteso(ip: IpotesiMercato, anni: int) -> Scenari:
    """Un solo scenario con i rendimenti mediani (geometrici) e l'inflazione attesa: la proiezione «centrale»."""
    def geo(m, s):
        return (1 + m) / np.sqrt(1 + s**2 / (1 + m) ** 2) - 1

    def f(x):
        return np.full((1, anni), x)

    return Scenari(f(geo(ip.azioni, ip.vol_azioni)), f(geo(ip.obbligazioni, ip.vol_obbligazioni)),
                   f(ip.inflazione), f(ip.inflazione + ip.liquidita_spread))


@dataclass
class Comparto:
    """Linea d'investimento: quota azionaria (costante o con percorso life-cycle) e garanzia.

    Con il percorso life-cycle la quota azionaria è `azioni` fino a `anni_inizio_discesa` anni dal pensionamento,
    poi scende in modo lineare fino a `azioni_finale` a `anni_fine_discesa` anni dal pensionamento.
    """

    nome: str
    azioni: float
    life_cycle: bool = False
    azioni_finale: float = 0.2
    anni_inizio_discesa: int = 15
    anni_fine_discesa: int = 5
    garanzia: bool = False  # restituzione dei contributi versati al pensionamento
    quota_titoli_stato_obbligazioni: float = 0.6
    descrizione: str = ""

    def peso_azioni(self, anni_al_pensionamento: float) -> float:
        if not self.life_cycle:
            return self.azioni
        a, b = self.anni_inizio_discesa, self.anni_fine_discesa
        if anni_al_pensionamento >= a:
            return self.azioni
        if anni_al_pensionamento <= b:
            return self.azioni_finale
        return self.azioni_finale + (self.azioni - self.azioni_finale) * (anni_al_pensionamento - b) / (a - b)

    def pesi(self, anni: int) -> np.ndarray:
        """Quota azionaria per ciascuno degli `anni` che mancano al pensionamento."""
        return np.array([self.peso_azioni(anni - t) for t in range(anni)])

    def quota_titoli_stato(self, peso_azioni: float) -> float:
        return (1 - peso_azioni) * self.quota_titoli_stato_obbligazioni

    def rendimenti(self, s: Scenari, anni: int | None = None) -> np.ndarray:
        anni = anni or s.anni
        w = self.pesi(anni)
        return w * s.azioni[:, :anni] + (1 - w) * s.obbligazioni[:, :anni]


COMPARTI = {
    "garantito": Comparto("Garantito", 0.15, garanzia=True, quota_titoli_stato_obbligazioni=0.8,
                          descrizione="15% azioni, restituzione dei versamenti al pensionamento"),
    "obbligazionario": Comparto("Obbligazionario", 0.15, descrizione="15% azioni, 85% obbligazioni"),
    "bilanciato": Comparto("Bilanciato", 0.45, descrizione="45% azioni, 55% obbligazioni"),
    "azionario": Comparto("Azionario", 0.75, descrizione="75% azioni, 25% obbligazioni"),
    "life_cycle": Comparto("Life-cycle", 0.75, life_cycle=True, azioni_finale=0.2,
                           descrizione="75% azioni fino a 15 anni dalla pensione, poi in discesa fino al 20%"),
}
