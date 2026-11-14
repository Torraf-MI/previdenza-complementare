"""Configurazione dell'analisi: lavoratore, contratto, mercati, strategie; caso dimostrativo e file JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .lavoratore import Lavoratore
from .mercato import COMPARTI, IpotesiMercato
from .prestazione import IpotesiRendita
from .strategie import (
    TASSAZIONE_FONDO,
    TASSAZIONE_INTERESSI,
    TASSAZIONE_PLUSVALENZE,
    Anticipazione,
    Strategia,
    Veicolo,
)


@dataclass
class Costi:
    """Costi annui tipici: ISC dei fondi negoziali e dei PIP (COVIP), TER degli ETF e commissioni del PAC."""

    fondo_negoziale: float = 0.0030
    fondo_negoziale_garantito: float = 0.0045
    quota_associativa: float = 22.0
    pip: float = 0.019
    etf: float = 0.0020
    commissioni_pac: float = 18.0  # 12 acquisti all'anno da 1,50 €


def veicoli(c: Costi, comparto: str = "life_cycle") -> dict[str, Veicolo]:
    cp = COMPARTI[comparto]
    return {
        "negoziale": Veicolo(f"Fondo negoziale {cp.nome.lower()}", cp, c.fondo_negoziale, c.quota_associativa),
        "garantito": Veicolo("Fondo negoziale garantito", COMPARTI["garantito"], c.fondo_negoziale_garantito,
                             c.quota_associativa),
        "pip": Veicolo(f"PIP {cp.nome.lower()}", cp, c.pip, 0.0),
        "etf": Veicolo(f"PAC in ETF {cp.nome.lower()}", cp, c.etf, c.commissioni_pac, bollo=True,
                       tassazione=TASSAZIONE_PLUSVALENZE),
        "deposito": Veicolo("Conto deposito", None, 0.0, 0.0, bollo=True, tassazione=TASSAZIONE_INTERESSI),
    }


def strategie_standard(contributo_lavoratore: float, contributo_datore: float, costi: Costi | None = None,
                       comparto: str = "life_cycle") -> list[Strategia]:
    v = veicoli(costi or Costi(), comparto)
    lav, dat = contributo_lavoratore, contributo_datore
    pl, pd = f"{lav:.1%}".replace(".", ","), f"{dat:.1%}".replace(".", ",")
    return [
        Strategia("TFR in azienda", "azienda", risparmio=v["deposito"],
                  descrizione="Il TFR resta in azienda; il risparmio va su un conto deposito"),
        Strategia("TFR in azienda + PAC in ETF", "azienda", risparmio=v["etf"],
                  descrizione="Il TFR resta in azienda; il risparmio va in un piano di accumulo in ETF con la stessa "
                              "asset allocation del fondo"),
        Strategia("Fondo negoziale: solo TFR", "fondo", fondo=v["negoziale"], risparmio=v["etf"],
                  descrizione="Al fondo solo il TFR, senza contributo proprio (e quindi senza quello del datore); il "
                              "risparmio va nel PAC"),
        Strategia("Fondo negoziale garantito", "fondo", fondo=v["garantito"], contributo_lavoratore=lav,
                  contributo_datore=dat,
                  descrizione=f"TFR, contributo del {pl} e del datore del {pd} nel comparto garantito"),
        Strategia("Fondo negoziale life-cycle", "fondo", fondo=v["negoziale"], contributo_lavoratore=lav,
                  contributo_datore=dat,
                  descrizione=f"TFR, contributo del {pl} e del datore del {pd} nel percorso life-cycle"),
        Strategia("PIP assicurativo", "fondo", fondo=v["pip"], contributo_lavoratore=lav,
                  descrizione=f"TFR e contributo del {pl} in un piano individuale; il contributo del datore si perde"),
    ]


@dataclass
class Configurazione:
    lavoratore: Lavoratore
    contributo_lavoratore: float = 0.012  # minimo previsto dal contratto per avere il contributo del datore
    contributo_datore: float = 0.02
    mercato: IpotesiMercato = field(default_factory=IpotesiMercato)
    costi: Costi = field(default_factory=Costi)
    rendita: IpotesiRendita = field(default_factory=IpotesiRendita)
    comparto: str = "life_cycle"
    strategie: list[Strategia] | None = None
    anticipazioni: list[Anticipazione] = field(default_factory=list)
    riferimento: str = "TFR in azienda"
    fondo: str = "Fondo negoziale life-cycle"  # strategia di riferimento per il budget netto e la prestazione
    alternativa: str = "TFR in azienda + PAC in ETF"
    scenari: int = 2_000
    seme: int = 7
    simula: bool = True
    dimostrativo: bool = False

    def __post_init__(self) -> None:
        if self.strategie is None:
            self.strategie = strategie_standard(self.contributo_lavoratore, self.contributo_datore, self.costi,
                                                self.comparto)
        nomi = [s.nome for s in self.strategie]
        for n in (self.riferimento, self.fondo, self.alternativa):
            if n not in nomi:
                raise ValueError(f"Strategia «{n}» non trovata tra {nomi}")


def esempio() -> Configurazione:
    """Giulia, 33 anni, impiegata con una RAL di 32.000 € e il TFR finora in azienda."""
    lav = Lavoratore("Giulia Conti", eta=33, ral=32_000, eta_pensione=68, sesso="F", anni_contributi=6,
                     tfr_pregresso=12_500, anni_tfr_pregresso=6, crescita_reale=0.02, eta_fine_crescita=50,
                     densita_contributiva=0.9)
    return Configurazione(lav, dimostrativo=True)


# ----------------------------------------------------------------------------- JSON
def _veicolo(d: dict, std: dict[str, Veicolo]) -> Veicolo:
    if isinstance(d, str):
        return std[d]
    d = dict(d)
    base = std.get(d.pop("base", ""), None)
    kw = asdict(base) if base else {}
    kw.pop("comparto", None)
    comparto = d.pop("comparto", None)
    kw.update(d)
    kw.setdefault("nome", "Veicolo")
    kw.setdefault("tassazione", TASSAZIONE_FONDO)
    cp = COMPARTI[comparto] if comparto else (base.comparto if base else None)
    return Veicolo(comparto=cp, **kw)


def da_dizionario(d: dict) -> Configurazione:
    lav = Lavoratore(**d["lavoratore"])
    mercato = IpotesiMercato(**d.get("mercato", {}))
    costi = Costi(**d.get("costi", {}))
    rendita = IpotesiRendita(**d.get("rendita", {}))
    comparto = d.get("comparto", "life_cycle")
    std = veicoli(costi, comparto)
    strategie = None
    if "strategie" in d:
        strategie = []
        for s in d["strategie"]:
            s = dict(s)
            for k in ("fondo", "risparmio"):
                if s.get(k) is not None:
                    s[k] = _veicolo(s[k], std)
            strategie.append(Strategia(**s))
    altri = {k: d[k] for k in ("contributo_lavoratore", "contributo_datore", "riferimento", "fondo", "alternativa",
                               "scenari", "seme") if k in d}
    return Configurazione(lav, mercato=mercato, costi=costi, rendita=rendita, comparto=comparto, strategie=strategie,
                          anticipazioni=[Anticipazione(**a) for a in d.get("anticipazioni", [])], **altri)


def carica(percorso: str | Path) -> Configurazione:
    return da_dizionario(json.loads(Path(percorso).read_text(encoding="utf-8")))


def a_dizionario(cfg: Configurazione) -> dict:
    def veic(v: Veicolo | None):
        if v is None:
            return None
        d = asdict(v)
        d["comparto"] = next((k for k, c in COMPARTI.items() if v.comparto is not None and c.nome == v.comparto.nome),
                             None)
        return d

    strat = []
    for s in cfg.strategie:
        d = {f.name: getattr(s, f.name) for f in fields(s)}
        d["fondo"], d["risparmio"] = veic(s.fondo), veic(s.risparmio)
        strat.append(d)
    return {
        "lavoratore": asdict(cfg.lavoratore), "contributo_lavoratore": cfg.contributo_lavoratore,
        "contributo_datore": cfg.contributo_datore, "comparto": cfg.comparto, "mercato": asdict(cfg.mercato),
        "costi": asdict(cfg.costi), "rendita": asdict(cfg.rendita), "strategie": strat,
        "anticipazioni": [asdict(a) for a in cfg.anticipazioni], "riferimento": cfg.riferimento,
        "fondo": cfg.fondo, "alternativa": cfg.alternativa, "scenari": cfg.scenari, "seme": cfg.seme,
    }


def salva(cfg: Configurazione, percorso: str | Path) -> Path:
    p = Path(percorso)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(a_dizionario(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
