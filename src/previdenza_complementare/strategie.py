"""Strategie di accumulo e motore di calcolo: TFR in azienda, fondo pensione, PIP, PAC in ETF, conto deposito.

Ogni strategia ha fino a tre «salvadanai»:

* il **TFR in azienda** (art. 2120 c.c.), rivalutato all'1,5% più il 75% dell'inflazione e tassato alla fine con la
  tassazione separata;
* un **fondo** (fondo pensione, PIP o, nelle ipotesi della scomposizione, un ETF) che riceve TFR, contributo del
  lavoratore e contributo del datore;
* un **risparmio libero** (PAC in ETF o conto deposito) che riceve la parte del budget netto non versata al fondo.

Il confronto è a **parità di sforzo netto**: ogni anno il lavoratore mette di tasca propria la stessa somma in tutte le
strategie. Nel fondo pensione quella somma è il contributo meno il risparmio d'imposta della deduzione; nel PAC è
investita direttamente.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import normativa as nv
from .lavoratore import Lavoratore
from .mercato import Comparto, Scenari

TASSAZIONE_FONDO = "fondo"  # 20% annuo sui rendimenti (12,5% sui titoli di Stato), aliquota 15-9% all'uscita
TASSAZIONE_PLUSVALENZE = "plusvalenze"  # 26% (12,5% sui titoli di Stato) sulle plusvalenze alla vendita
TASSAZIONE_INTERESSI = "interessi"  # 26% sugli interessi ogni anno (conto deposito)


@dataclass
class Veicolo:
    """Un contenitore d'investimento: comparto, costi e regime fiscale."""

    nome: str
    comparto: Comparto | None  # None = liquidità (conto deposito)
    costo: float = 0.0  # costo annuo in % del patrimonio (ISC del fondo, TER dell'ETF)
    costo_fisso: float = 0.0  # € all'anno (quota associativa, commissioni di acquisto del PAC)
    bollo: bool = False
    tassazione: str = TASSAZIONE_FONDO

    def __post_init__(self) -> None:
        if self.tassazione not in (TASSAZIONE_FONDO, TASSAZIONE_PLUSVALENZE, TASSAZIONE_INTERESSI):
            raise ValueError(f"Regime fiscale sconosciuto: {self.tassazione}")


@dataclass
class Anticipazione:
    """Un prelievo prima della pensione: `importo` netto in euro di oggi a `eta` anni."""

    eta: float
    importo: float
    tipo: str = "prima_casa"  # spese_sanitarie, prima_casa, altre_esigenze

    def __post_init__(self) -> None:
        if self.tipo not in nv.ANTICIPAZIONI:
            raise ValueError(f"Tipo di anticipazione sconosciuto: {self.tipo}")


@dataclass
class Strategia:
    nome: str
    tfr: str = "azienda"  # "azienda" o "fondo"
    fondo: Veicolo | None = None
    contributo_lavoratore: float = 0.0  # % della RAL
    contributo_datore: float = 0.0  # % della RAL
    deducibile: bool = True
    risparmio: Veicolo | None = None
    descrizione: str = ""

    def __post_init__(self) -> None:
        if self.tfr not in ("azienda", "fondo"):
            raise ValueError("tfr deve essere 'azienda' o 'fondo'")
        if self.fondo is None and (self.tfr == "fondo" or self.contributo_lavoratore or self.contributo_datore):
            raise ValueError(f"{self.nome}: TFR e contributi al fondo richiedono un fondo")


@dataclass
class Esito:
    """Risultato di una strategia: importi in euro di oggi, uno per scenario."""

    strategia: Strategia
    fondo_lordo: np.ndarray
    imposta_fondo: np.ndarray
    imponibile_fondo: np.ndarray
    aliquota_uscita: float
    tfr_lordo: np.ndarray
    imposta_tfr: np.ndarray
    risparmio_lordo: np.ndarray
    imposta_risparmio: np.ndarray
    sforzo_netto: float  # somma dei versamenti netti del lavoratore
    contributi_lavoratore: float
    risparmio_fiscale: float
    contributi_datore: float
    tfr_versato: float
    costi: np.ndarray
    imposte_rendimenti: np.ndarray
    anticipazioni_nette: np.ndarray
    imposte_anticipazioni: np.ndarray
    percorso: np.ndarray  # patrimonio lordo totale a fine anno (scenari × anni), euro di oggi
    extra: dict = field(default_factory=dict)

    @property
    def fondo_netto(self) -> np.ndarray:
        return self.fondo_lordo - self.imposta_fondo

    @property
    def tfr_netto(self) -> np.ndarray:
        return self.tfr_lordo - self.imposta_tfr

    @property
    def risparmio_netto(self) -> np.ndarray:
        return self.risparmio_lordo - self.imposta_risparmio

    @property
    def lordo(self) -> np.ndarray:
        return self.fondo_lordo + self.tfr_lordo + self.risparmio_lordo

    @property
    def netto(self) -> np.ndarray:
        """Capitale netto disponibile al pensionamento, in euro di oggi."""
        return self.fondo_netto + self.tfr_netto + self.risparmio_netto

    @property
    def imposte_uscita(self) -> np.ndarray:
        return self.imposta_fondo + self.imposta_tfr + self.imposta_risparmio


def deduzioni(ral: np.ndarray, lav: np.ndarray, dat: np.ndarray, limite: float = nv.LIMITE_DEDUCIBILITA):
    """Contributi dedotti e non dedotti: il limite si applica alla somma di lavoratore e datore (non al TFR)."""
    dat_d = np.minimum(dat, limite)
    lav_d = np.clip(limite - dat_d, 0.0, lav)
    return lav_d, dat_d, (lav - lav_d) + (dat - dat_d)


def budget_netto(lav: Lavoratore, contributo_lavoratore: float, contributo_datore: float) -> np.ndarray:
    """Sforzo netto annuo (euro di oggi) di chi versa `contributo_lavoratore` al fondo con la deduzione."""
    ral = lav.ral_percorso()
    c_lav, c_dat = ral * contributo_lavoratore, ral * contributo_datore
    lav_d, _, _ = deduzioni(ral, c_lav, c_dat)
    return c_lav - nv.risparmio_deduzione(ral, lav_d)


def _rendimento(v: Veicolo, s: Scenari, anni: int) -> tuple[np.ndarray, np.ndarray]:
    """Rendimento lordo annuo (scenari × anni) e quota di titoli di Stato per anno."""
    if v.comparto is None:
        return s.liquidita[:, :anni], np.zeros(anni)
    w = v.comparto.pesi(anni)
    return v.comparto.rendimenti(s, anni), np.array([v.comparto.quota_titoli_stato(x) for x in w])


def simula(strategia: Strategia, lav: Lavoratore, s: Scenari, budget: np.ndarray | None = None,
           anticipazioni: list[Anticipazione] | None = None) -> Esito:
    """Accumulo dalla data di oggi al pensionamento in tutti gli scenari."""
    T = lav.anni
    if s.anni < T:
        raise ValueError(f"Servono scenari di almeno {T} anni")
    n = s.n
    ral = lav.ral_percorso()
    P = s.indice_prezzi()[:, :T]
    budget = np.zeros(T) if budget is None else np.asarray(budget, dtype=float)
    ant = sorted(anticipazioni or [], key=lambda a: a.eta)
    f, r = strategia.fondo, strategia.risparmio

    # flussi reali annui
    c_tfr = ral * nv.QUOTA_TFR
    c_lav = ral * strategia.contributo_lavoratore
    c_dat = ral * strategia.contributo_datore
    if strategia.deducibile:
        lav_d, dat_d, non_ded = deduzioni(ral, c_lav, c_dat)
        risp_fisc = nv.risparmio_deduzione(ral, lav_d)
    else:
        lav_d, dat_d, non_ded = np.zeros(T), np.minimum(c_dat, nv.LIMITE_DEDUCIBILITA), c_lav + c_dat - np.minimum(
            c_dat, nv.LIMITE_DEDUCIBILITA)
        risp_fisc = np.zeros(T)
    costo_lav = c_lav - risp_fisc
    c_risp = np.maximum(budget - costo_lav, 0.0) if r is not None else np.zeros(T)
    sforzo = costo_lav + c_risp
    tfr_al_fondo = strategia.tfr == "fondo"

    if f is not None:
        rf, qf = _rendimento(f, s, T)
        al_f = (np.array([nv.aliquota_rendimenti(q) for q in qf]) if f.tassazione == TASSAZIONE_FONDO
                else np.array([nv.aliquota_rendimenti(q, nv.ALIQUOTA_REDDITI_FINANZIARI) for q in qf]))
    if r is not None:
        rr, qr = _rendimento(r, s, T)
        al_r = np.array([nv.aliquota_rendimenti(q, nv.ALIQUOTA_REDDITI_FINANZIARI) for q in qr])

    z = np.zeros(n)
    F, F_imp, F_base, F_vers, F_cred = z.copy(), z.copy(), z.copy(), z.copy(), z.copy()
    A, A_quote, A_quote_reali = np.full(n, lav.tfr_pregresso), np.full(n, lav.tfr_pregresso), lav.tfr_pregresso
    R, R_base = z.copy(), z.copy()
    costi, imp_rend, ant_nette, imp_ant = z.copy(), z.copy(), z.copy(), z.copy()
    anticipato_tfr = np.zeros(n, dtype=bool)
    percorso = np.zeros((n, T))
    anni_servizio = lav.anni_tfr_pregresso

    def _cresci(V, cred, rend, aliquota, v: Veicolo, Pt):
        nonlocal costi, imp_rend
        lordo = V * (1 + rend)
        c = V * v.costo + v.costo_fisso * Pt + (lordo * nv.IMPOSTA_BOLLO if v.bollo else 0.0)
        c = np.where(V > 0, c, 0.0)
        nuovo = lordo - c
        imposta = np.zeros_like(V)
        if v.tassazione in (TASSAZIONE_FONDO, TASSAZIONE_INTERESSI):
            risultato = nuovo - V
            if v.tassazione == TASSAZIONE_FONDO:
                netto = risultato - cred
                imposta = np.where(netto > 0, aliquota * netto, 0.0)
                cred = np.where(netto > 0, 0.0, -netto)
            else:
                imposta = np.maximum(risultato, 0.0) * aliquota
            nuovo = nuovo - imposta
        costi += c / Pt
        imp_rend += imposta / Pt
        return nuovo, cred

    for t in range(T):
        Pt = P[:, t]
        if f is not None:
            F, F_cred = _cresci(F, F_cred, rf[:, t], al_f[t], f, Pt)
        if r is not None:
            R, _ = _cresci(R, np.zeros(n), rr[:, t], al_r[t], r, Pt)
        A = A * (1 + nv.rivalutazione_tfr(s.inflazione[:, t]) * (1 - nv.IMPOSTA_RIVALUTAZIONE_TFR))

        # versamenti di fine anno (nominali)
        if f is not None:
            vers = (c_tfr[t] * tfr_al_fondo + c_lav[t] + c_dat[t]) * Pt
            F = F + vers
            F_vers = F_vers + vers
            F_base = F_base + (c_lav[t] + c_dat[t]) * Pt
            F_imp = F_imp + (c_tfr[t] * tfr_al_fondo + lav_d[t] + dat_d[t]) * Pt
        if not tfr_al_fondo:
            A = A + c_tfr[t] * Pt
            A_quote = A_quote + c_tfr[t] * Pt
            A_quote_reali += c_tfr[t]
        if r is not None:
            R = R + c_risp[t] * Pt
            R_base = R_base + c_risp[t] * Pt
        if not tfr_al_fondo:
            anni_servizio += 1

        # anticipazioni a fine anno
        eta_t = lav.eta + t + 1
        for a in ant:
            if not (eta_t - 1 < a.eta <= eta_t):
                continue
            quota_max, anni_min, agevolata = nv.ANTICIPAZIONI[a.tipo]
            serve = np.full(n, a.importo) * Pt
            if f is not None and t + 1 >= anni_min:
                if f.tassazione == TASSAZIONE_FONDO:
                    al = nv.aliquota_prestazione(t + 1) if agevolata else nv.ALIQUOTA_ANTICIPAZIONI_ALTRE
                    quota_tass = np.where(F > 0, np.minimum(F_imp, F) / np.where(F > 0, F, 1), 0)
                else:
                    al = al_f[t]
                    quota_tass = np.where(F > 0, np.maximum(F - F_base, 0) / np.where(F > 0, F, 1), 0)
                lordo = np.minimum(serve / (1 - al * quota_tass), quota_max * F)
                imposta = lordo * al * quota_tass
                k = np.where(F > 0, 1 - lordo / np.where(F > 0, F, 1), 1.0)
                F, F_imp, F_base, F_vers = F * k, F_imp * k, F_base * k, F_vers * k
                serve = serve - (lordo - imposta)
                ant_nette += (lordo - imposta) / Pt
                imp_ant += imposta / Pt
            if a.tipo != "altre_esigenze" and anni_servizio >= 8:
                puo = (~anticipato_tfr) & (serve > 1e-6)
                al = nv.aliquota_tfr(A_quote_reali, anni_servizio)
                quota_tass = np.where(A > 0, A_quote / np.where(A > 0, A, 1), 0)
                lordo = np.where(puo, np.minimum(serve / (1 - al * quota_tass), nv.ANTICIPAZIONE_TFR_MAX * A), 0.0)
                imposta = lordo * al * quota_tass
                k = np.where(A > 0, 1 - lordo / np.where(A > 0, A, 1), 1.0)
                A, A_quote = A * k, A_quote * k
                A_quote_reali = A_quote_reali * float(np.mean(k))
                anticipato_tfr |= lordo > 0
                serve = serve - (lordo - imposta)
                ant_nette += (lordo - imposta) / Pt
                imp_ant += imposta / Pt
            if r is not None:
                quota_tass = (np.where(R > 0, np.maximum(R - R_base, 0) / np.where(R > 0, R, 1), 0)
                              if r.tassazione == TASSAZIONE_PLUSVALENZE else 0.0)
                al = al_r[t]
                lordo = np.minimum(np.maximum(serve, 0) / (1 - al * quota_tass), R)
                imposta = lordo * al * quota_tass
                k = np.where(R > 0, 1 - lordo / np.where(R > 0, R, 1), 1.0)
                R, R_base = R * k, R_base * k
                serve = serve - (lordo - imposta)
                ant_nette += (lordo - imposta) / Pt
                imp_ant += imposta / Pt
        percorso[:, t] = (F + A + R) / Pt

    PT = P[:, -1]
    # uscita dal fondo
    anni_part = T
    if f is not None and f.comparto is not None and f.comparto.garanzia:
        F = np.maximum(F, F_vers)
    if f is not None and f.tassazione == TASSAZIONE_FONDO:
        aliquota_uscita = nv.aliquota_prestazione(anni_part)
        imponibile = np.minimum(F_imp, F)
        imp_f = aliquota_uscita * imponibile
    elif f is not None:
        aliquota_uscita = float(al_f[-1])
        imponibile = np.maximum(F - F_base, 0.0)
        imp_f = aliquota_uscita * imponibile
    else:
        aliquota_uscita, imponibile, imp_f = 0.0, z.copy(), z.copy()
    # TFR in azienda: tassazione separata sulle quote (le rivalutazioni sono già tassate al 17%)
    al_tfr = nv.aliquota_tfr(A_quote_reali, max(anni_servizio, 1)) if A_quote_reali > 0 else 0.0
    imp_a = al_tfr * A_quote
    # risparmio libero
    if r is not None and r.tassazione == TASSAZIONE_PLUSVALENZE:
        imp_r = al_r[-1] * np.maximum(R - R_base, 0.0)
    else:
        imp_r = z.copy()

    return Esito(
        strategia=strategia, fondo_lordo=F / PT, imposta_fondo=imp_f / PT, imponibile_fondo=imponibile / PT,
        aliquota_uscita=float(aliquota_uscita), tfr_lordo=A / PT, imposta_tfr=imp_a / PT, risparmio_lordo=R / PT,
        imposta_risparmio=imp_r / PT, sforzo_netto=float(sforzo.sum()), contributi_lavoratore=float(c_lav.sum()),
        risparmio_fiscale=float(risp_fisc.sum()), contributi_datore=float(c_dat.sum()),
        tfr_versato=float(c_tfr.sum()), costi=costi, imposte_rendimenti=imp_rend, anticipazioni_nette=ant_nette,
        imposte_anticipazioni=imp_ant, percorso=percorso,
        extra={"aliquota_tfr": float(al_tfr), "non_dedotti": float(non_ded.sum())},
    )
