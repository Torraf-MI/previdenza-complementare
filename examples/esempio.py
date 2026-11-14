"""Uso come libreria: pensione pubblica, rimborso IRPEF e confronto tra fondo pensione e PAC per un lavoratore."""

import pandas as pd

from previdenza_complementare import (
    Configurazione,
    Lavoratore,
    aliquota_prestazione,
    analizza,
    risparmio_deduzione,
)

pd.set_option("display.width", 160)

# le regole
print(f"Aliquota sulla prestazione dopo 10, 25 e 35 anni: "
      f"{[f'{aliquota_prestazione(a):.1%}' for a in (10, 25, 35)]}")
for ral in (25_000, 32_000, 40_000, 60_000):
    print(f"RAL {ral:>6,} €: 1.000 € versati al fondo fanno risparmiare {risparmio_deduzione(ral, 1_000):,.0f} €")

# un lavoratore
marco = Lavoratore("Marco Neri", eta=45, ral=48_000, eta_pensione=67, sesso="M", anni_contributi=20,
                   tfr_pregresso=60_000, anni_tfr_pregresso=20)
p = marco.pensione_inps()
print(f"\nPensione INPS netta stimata: {p['netta']:,.0f} € l'anno ({p['sostituzione_netta']:.0%} dell'ultimo netto)")

a = analizza(Configurazione(marco, contributo_lavoratore=0.01, contributo_datore=0.015, scenari=500))
t = a.tabella()
print(t[["Capitale netto", "Rendita mensile netta", "Rispetto al TFR in azienda"]].round(0))
print(a.scomposizione.round(0))
