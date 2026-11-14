"""Riga di comando: pensione pubblica, TFR, fondo pensione e PAC a confronto.

Esempi::

    previdenza-complementare --demo
    previdenza-complementare --config esempi/giulia.json --output output/report.html
    previdenza-complementare --demo --veloce --grafici docs/img
"""

from __future__ import annotations

import argparse
import sys

from . import configurazione
from .analisi import analizza
from .report import _eur, _pct, build_report, salva_grafici

NOTA_DEMO = ("Caso dimostrativo: la lavoratrice e i suoi dati sono di fantasia; le regole sono quelle italiane del "
             "2026 e i costi sono valori tipici pubblicati dalla COVIP.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="previdenza-complementare", description=__doc__.splitlines()[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--config", help="File JSON con lavoratore, contratto, mercati e strategie")
    src.add_argument("--demo", action="store_true", help="Usa il caso dimostrativo")
    p.add_argument("--output", default="output/report.html", help="Percorso del report HTML")
    p.add_argument("--grafici", help="Cartella dove salvare anche i grafici PNG (richiede kaleido)")
    p.add_argument("--offline", action="store_true", help="Include plotly.js nel report (funziona senza rete)")
    p.add_argument("--veloce", action="store_true", help="Salta la simulazione Monte Carlo")
    p.add_argument("--scenari", type=int, help="Numero di scenari della simulazione")
    p.add_argument("--eta-pensione", type=float, help="Età di pensionamento")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = configurazione.esempio() if args.demo else configurazione.carica(args.config)
    if args.veloce:
        cfg.simula = False
    if args.scenari:
        cfg.scenari = args.scenari
    if args.eta_pensione:
        cfg.lavoratore.eta_pensione = args.eta_pensione
    a = analizza(cfg)
    path = build_report(a, args.output, data_note=configurazione_nota(cfg), offline=args.offline)
    if args.grafici:
        salva_grafici(a, args.grafici)

    lav, p = cfg.lavoratore, a.inps
    print(f"{lav.nome}, {lav.eta:.0f} anni, RAL {_eur(lav.ral)}: pensione a {lav.eta_pensione:.0f} anni")
    print(f"  pensione INPS netta {_eur(p['netta'])} l'anno, il {_pct(p['sostituzione_netta'], 0)} dell'ultimo "
          f"netto; gap rispetto all'obiettivo {_eur(p['gap'])} l'anno")
    print(f"  sforzo netto il primo anno: {_eur(float(a.budget[0]))}\n")
    t = a.tabella()
    sim = a.sintesi_simulazione()
    print("Capitale netto al pensionamento (euro di oggi, scenario centrale)")
    for n, r in t.iterrows():
        extra = ""
        if sim is not None:
            extra = f"   batte il PAC nel {_pct(sim.loc[n, 'Meglio del PAC'], 0):>5} degli scenari"
        print(f"  {n:<30} {_eur(r['Capitale netto']):>11}   rendita {_eur(r['Rendita mensile netta']):>7} al "
              f"mese{extra}")
    print(f"\nReport salvato in {path}")
    return 0


def configurazione_nota(cfg) -> str:
    return NOTA_DEMO if cfg.dimostrativo else ""


if __name__ == "__main__":
    sys.exit(main())
