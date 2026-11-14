"""Analisi completa: pensione pubblica, confronto delle strategie, scomposizione del vantaggio, prestazione."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from . import normativa as nv
from . import prestazione as pr
from .configurazione import Configurazione
from .lavoratore import Lavoratore
from .mercato import genera_scenari, scenario_atteso
from .strategie import Esito, Strategia, budget_netto, simula


@dataclass
class Analisi:
    cfg: Configurazione
    inps: dict
    budget: np.ndarray
    attesi: list[Esito]  # scenario centrale
    esiti: list[Esito] | None  # Monte Carlo
    fattore_rendita: float
    scomposizione: pd.DataFrame
    mappa: pd.DataFrame
    opzioni: list[pr.Opzione]
    sensibilita: pd.DataFrame

    def _per_nome(self, lista: list[Esito] | None, nome: str) -> Esito:
        return next(e for e in (lista or self.attesi) if e.strategia.nome == nome)

    def atteso(self, nome: str) -> Esito:
        return self._per_nome(self.attesi, nome)

    def esito(self, nome: str) -> Esito:
        return self._per_nome(self.esiti, nome) if self.esiti else self.atteso(nome)

    def rendita(self, capitale_netto: float | np.ndarray) -> float | np.ndarray:
        """Rendita vitalizia netta annua (euro di oggi) che il capitale netto può comprare."""
        return capitale_netto / self.fattore_rendita

    def tabella(self) -> pd.DataFrame:
        """Confronto nello scenario centrale, importi in euro di oggi."""
        rif = self.atteso(self.cfg.riferimento)
        righe = {}
        for e in self.attesi:
            netto = float(e.netto[0])
            righe[e.strategia.nome] = {
                "Sforzo netto": e.sforzo_netto, "Contributi del datore": e.contributi_datore,
                "Risparmio d'imposta": e.risparmio_fiscale, "Capitale lordo": float(e.lordo[0]),
                "Costi": float(e.costi[0]), "Imposte sui rendimenti": float(e.imposte_rendimenti[0]),
                "Imposte all'uscita": float(e.imposte_uscita[0]), "Capitale netto": netto,
                "Rendita mensile netta": self.rendita(netto) / 12,
                "Rispetto al TFR in azienda": netto - float(rif.netto[0]),
                "Gap coperto": min(self.rendita(netto) / self.inps["gap"], 9.99) if self.inps["gap"] > 0 else 1.0,
            }
        return pd.DataFrame(righe).T

    def sintesi_simulazione(self) -> pd.DataFrame | None:
        if not self.esiti:
            return None
        alt = self.esito(self.cfg.alternativa).netto
        rif = self.esito(self.cfg.riferimento).netto
        righe = {}
        for e in self.esiti:
            x = e.netto
            righe[e.strategia.nome] = {
                "Mediana": float(np.median(x)), "5° percentile": float(np.percentile(x, 5)),
                "95° percentile": float(np.percentile(x, 95)),
                "Rendita mensile mediana": float(np.median(self.rendita(x))) / 12,
                "Meglio del TFR in azienda": float(np.mean(x > rif)),
                "Meglio del PAC": float(np.mean(x > alt)),
                "Gap coperto (mediana)": float(np.median(self.rendita(x))) / self.inps["gap"]
                if self.inps["gap"] > 0 else 1.0,
            }
        return pd.DataFrame(righe).T


def _hybrid(base: Strategia, **kw) -> Strategia:
    return replace(base, **kw)


def scomponi(cfg: Configurazione, budget: np.ndarray, anni_extra: int = 0) -> pd.DataFrame:
    """Da «TFR in azienda + PAC» al fondo negoziale, una differenza alla volta (scenario centrale)."""
    lav = cfg.lavoratore
    s = scenario_atteso(cfg.mercato, lav.anni + anni_extra)
    fondo = next(x for x in cfg.strategie if x.nome == cfg.fondo)
    pac = next(x for x in cfg.strategie if x.nome == cfg.alternativa)
    etf = replace(pac.risparmio, nome="ETF")
    if fondo.fondo is None:
        raise ValueError("La strategia di riferimento deve avere un fondo")
    etf_fondo = replace(etf, comparto=fondo.fondo.comparto)
    costi_fondo = replace(etf_fondo, costo=fondo.fondo.costo, costo_fisso=fondo.fondo.costo_fisso, bollo=False)
    passi = [
        ("TFR in azienda + PAC in ETF", pac),
        ("TFR investito invece che in azienda",
         Strategia("p1", "fondo", fondo=etf_fondo, deducibile=False, risparmio=pac.risparmio)),
        ("Contributo del datore",
         Strategia("p2", "fondo", fondo=etf_fondo, contributo_datore=fondo.contributo_datore, deducibile=False,
                   risparmio=pac.risparmio)),
        ("Deduzione dei contributi",
         Strategia("p3", "fondo", fondo=etf_fondo, contributo_lavoratore=fondo.contributo_lavoratore,
                   contributo_datore=fondo.contributo_datore, risparmio=pac.risparmio)),
        ("Costi più bassi e niente bollo",
         Strategia("p4", "fondo", fondo=costi_fondo, contributo_lavoratore=fondo.contributo_lavoratore,
                   contributo_datore=fondo.contributo_datore, risparmio=pac.risparmio)),
        ("Fiscalità del fondo (20% e 15-9%)", fondo),
    ]
    righe, prec = [], None
    for nome, st in passi:
        e = simula(st, lav, s, budget, cfg.anticipazioni)
        v = float(e.netto[0])
        righe.append({"passo": nome, "netto": v, "effetto": v - prec if prec is not None else v})
        prec = v
    return pd.DataFrame(righe).set_index("passo")


def mappa_vantaggio(cfg: Configurazione, eta: list[int] | None = None, ral: list[int] | None = None) -> pd.DataFrame:
    """Vantaggio del fondo sul PAC (capitale netto, euro di oggi) per età di adesione e RAL."""
    eta = eta or [25, 30, 35, 40, 45, 50, 55, 60]
    ral = ral or [20_000, 28_000, 35_000, 42_000, 50_000, 60_000, 75_000, 90_000]
    fondo = next(x for x in cfg.strategie if x.nome == cfg.fondo)
    pac = next(x for x in cfg.strategie if x.nome == cfg.alternativa)
    base = cfg.lavoratore
    out = pd.DataFrame(index=eta, columns=ral, dtype=float)
    s = scenario_atteso(cfg.mercato, int(base.eta_pensione - min(eta)) + 1)
    for e in eta:
        for r in ral:
            lav = replace(base, eta=e, ral=r, tfr_pregresso=0.0, anni_tfr_pregresso=0.0, montante_inps=None)
            b = budget_netto(lav, fondo.contributo_lavoratore, fondo.contributo_datore)
            vf = float(simula(fondo, lav, s, b).netto[0])
            vp = float(simula(pac, lav, s, b).netto[0])
            out.loc[e, r] = (vf - vp) / max(vp, 1.0)
    out.index.name, out.columns.name = "Età di adesione", "RAL"
    return out


def aliquote_uscita(anni: np.ndarray, tfr_annuo: float = 2_500.0) -> pd.DataFrame:
    """Aliquota sulla parte tassabile: fondo pensione, TFR in azienda, ETF (sulle sole plusvalenze)."""
    return pd.DataFrame({
        "Fondo pensione": nv.aliquota_prestazione(anni),
        "TFR in azienda": [nv.aliquota_tfr(tfr_annuo * a, a) for a in anni],
        "ETF (sulle plusvalenze)": np.full(len(anni), nv.ALIQUOTA_REDDITI_FINANZIARI),
    }, index=anni)


def analizza(cfg: Configurazione) -> Analisi:
    lav: Lavoratore = cfg.lavoratore
    inps = lav.pensione_inps()
    fondo = next(x for x in cfg.strategie if x.nome == cfg.fondo)
    budget = budget_netto(lav, fondo.contributo_lavoratore, fondo.contributo_datore)
    s_att = scenario_atteso(cfg.mercato, lav.anni)
    attesi = [simula(st, lav, s_att, budget, cfg.anticipazioni) for st in cfg.strategie]
    esiti = None
    if cfg.simula:
        sc = genera_scenari(cfg.mercato, lav.anni, cfg.scenari, cfg.seme)
        esiti = [simula(st, lav, sc, budget, cfg.anticipazioni) for st in cfg.strategie]
    mort = pr.Mortalita(lav.sesso, lav.anni, assicurati=True)
    fattore = pr.fattore_rendita(lav.eta_pensione, mort, cfg.rendita)
    ef = next(e for e in attesi if e.strategia.nome == cfg.fondo)
    montante = float(ef.fondo_lordo[0])
    quota_imp = float(ef.imponibile_fondo[0]) / montante if montante > 0 else 0.0
    opz = pr.opzioni(montante, quota_imp, ef.aliquota_uscita, lav.eta_pensione, lav.sesso, lav.anni, cfg.rendita,
                     cfg.mercato, n=min(cfg.scenari, 2_000) if cfg.simula else 500, seme=cfg.seme + 4)
    return Analisi(cfg, inps, budget, attesi, esiti, fattore, scomponi(cfg, budget), mappa_vantaggio(cfg), opz,
                   sensibilita_inps(lav))





def sensibilita_inps(lav: Lavoratore, crescite: tuple[float, ...] = (0.003, 0.008, 0.013),
                     eta: tuple[float, ...] = (67, 68, 69, 70)) -> pd.DataFrame:
    """Tasso di sostituzione netto della pensione pubblica per crescita del PIL reale ed età di pensionamento."""
    out = pd.DataFrame(index=[f"PIL reale {g:.1%}".replace(".", ",") for g in crescite], columns=list(eta), dtype=float)
    for g, nome in zip(crescite, out.index):
        for e in eta:
            if e <= lav.eta:
                continue
            out.loc[nome, e] = replace(lav, crescita_pil_reale=g, eta_pensione=e).pensione_inps()["sostituzione_netta"]
    out.columns.name = "Età di pensionamento"
    return out
