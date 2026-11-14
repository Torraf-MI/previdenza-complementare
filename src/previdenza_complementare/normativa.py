"""Regole fiscali e previdenziali italiane in vigore nel 2026.

Fonti: TUIR (artt. 11, 13, 17, 19), D.Lgs. 252/2005 sulla previdenza complementare come modificato dalla Legge di
Bilancio 2026 (L. 199/2025), art. 2120 c.c. sul TFR, L. 335/1995 sul sistema contributivo e decreto direttoriale del
20/11/2024 sui coefficienti di trasformazione 2025-2026.

Tutti gli importi sono in euro del 2026. Nelle proiezioni le soglie IRPEF sono applicate ai redditi in termini reali,
cioè come se fossero indicizzate all'inflazione.
"""

from __future__ import annotations

import numpy as np

# ----------------------------------------------------------------------------- IRPEF
SCAGLIONI_IRPEF = ((28_000.0, 0.23), (50_000.0, 0.33), (float("inf"), 0.43))
ADDIZIONALI = 0.023  # regionale + comunale medie, applicate a tutto il reddito imponibile

ALIQUOTA_CONTRIBUTI_LAVORATORE = 0.0919  # contributi INPS a carico del dipendente (FPLD)
ALIQUOTA_IVS = 0.33  # aliquota di computo del sistema contributivo per i dipendenti


def irpef_lorda(reddito):
    """IRPEF lorda per scaglioni 2026 (23% fino a 28.000 €, 33% fino a 50.000 €, 43% oltre)."""
    r = np.maximum(np.asarray(reddito, dtype=float), 0.0)
    imposta = np.zeros_like(r)
    inf = 0.0
    for sup, aliquota in SCAGLIONI_IRPEF:
        imposta += np.clip(r - inf, 0.0, sup - inf) * aliquota
        inf = sup
    return imposta if imposta.ndim else float(imposta)


def detrazione_lavoro(reddito):
    """Detrazione per lavoro dipendente (art. 13 c. 1 TUIR, versione dal 2025)."""
    r = np.asarray(reddito, dtype=float)
    d = np.where(r <= 15_000, 1_955.0,
                 np.where(r <= 28_000, 1_910 + 1_190 * (28_000 - r) / 13_000,
                          np.where(r <= 50_000, 1_910 * (50_000 - r) / 22_000, 0.0)))
    d = d + np.where((r > 25_000) & (r <= 35_000), 65.0, 0.0)
    return d if d.ndim else float(d)


def ulteriore_detrazione_cuneo(reddito):
    """Ulteriore detrazione per i dipendenti tra 20.000 e 40.000 € (L. 207/2024, c. 6)."""
    r = np.asarray(reddito, dtype=float)
    d = np.where((r > 20_000) & (r <= 32_000), 1_000.0,
                 np.where((r > 32_000) & (r <= 40_000), 1_000 * (40_000 - r) / 8_000, 0.0))
    return d if d.ndim else float(d)


def somma_cuneo(reddito):
    """Somma esente per i dipendenti fino a 20.000 € (L. 207/2024, c. 4): non tassata, si aggiunge al netto."""
    r = np.asarray(reddito, dtype=float)
    p = np.where(r <= 8_500, 0.071, np.where(r <= 15_000, 0.053, np.where(r <= 20_000, 0.048, 0.0)))
    s = r * p
    return s if s.ndim else float(s)


def detrazione_pensione(reddito):
    """Detrazione per redditi di pensione (art. 13 c. 3 TUIR, versione dal 2024)."""
    r = np.asarray(reddito, dtype=float)
    d = np.where(r <= 8_500, 1_955.0,
                 np.where(r <= 28_000, 700 + 1_255 * (28_000 - r) / 19_500,
                          np.where(r <= 50_000, 700 * (50_000 - r) / 22_000, 0.0)))
    return d if d.ndim else float(d)


def trattamento_integrativo(reddito):
    """Trattamento integrativo di 1.200 € fino a 15.000 € di reddito se l'imposta supera la detrazione (D.L. 3/2020)."""
    r = np.asarray(reddito, dtype=float)
    capiente = irpef_lorda(r) > detrazione_lavoro(r) - 75
    t = np.where((r <= 15_000) & capiente & (r > 0), 1_200.0, 0.0)
    return t if t.ndim else float(t)


def imposte_lavoro(imponibile):
    """IRPEF netta più addizionali su un reddito di lavoro dipendente (al netto dei contributi INPS).

    Il risultato può essere negativo: trattamento integrativo e somma del cuneo fiscale sono pagati in busta paga.
    """
    r = np.asarray(imponibile, dtype=float)
    netta = np.maximum(irpef_lorda(r) - detrazione_lavoro(r) - ulteriore_detrazione_cuneo(r), 0.0)
    t = netta + ADDIZIONALI * np.maximum(r, 0.0) - somma_cuneo(r) - trattamento_integrativo(r)
    return t if t.ndim else float(t)


def imposte_pensione(reddito):
    """IRPEF netta più addizionali su una pensione."""
    r = np.asarray(reddito, dtype=float)
    t = np.maximum(irpef_lorda(r) - detrazione_pensione(r), 0.0) + ADDIZIONALI * np.maximum(r, 0.0)
    return t if t.ndim else float(t)


def stipendio_netto(ral):
    """Stipendio netto annuo di un dipendente: RAL meno contributi, IRPEF e addizionali."""
    imponibile = np.asarray(ral, dtype=float) * (1 - ALIQUOTA_CONTRIBUTI_LAVORATORE)
    n = imponibile - imposte_lavoro(imponibile)
    return n if np.ndim(n) else float(n)


def risparmio_deduzione(ral, deduzione):
    """Imposte risparmiate deducendo `deduzione` dal reddito (IRPEF, detrazioni e addizionali)."""
    imponibile = np.asarray(ral, dtype=float) * (1 - ALIQUOTA_CONTRIBUTI_LAVORATORE)
    d = np.minimum(np.asarray(deduzione, dtype=float), imponibile)
    s = imposte_lavoro(imponibile) - imposte_lavoro(imponibile - d)
    return s if np.ndim(s) else float(s)


def aliquota_marginale_effettiva(ral, delta: float = 1_000.0):
    """Quota di un euro dedotto che torna in tasca: include l'effetto del décalage delle detrazioni."""
    return risparmio_deduzione(ral, delta) / delta


# ----------------------------------------------------------------------------- TFR
QUOTA_TFR = 1 / 13.5 - 0.005  # 6,91% della retribuzione: quota annua meno il contributo aggiuntivo IVS dello 0,5%
RIVALUTAZIONE_TFR_FISSA = 0.015
RIVALUTAZIONE_TFR_INFLAZIONE = 0.75
IMPOSTA_RIVALUTAZIONE_TFR = 0.17
ANTICIPAZIONE_TFR_MAX = 0.70  # art. 2120 c.c., dopo 8 anni di servizio, una sola volta


def rivalutazione_tfr(inflazione):
    """Tasso di rivalutazione annuo del TFR in azienda: 1,5% fisso più il 75% dell'inflazione."""
    return RIVALUTAZIONE_TFR_FISSA + RIVALUTAZIONE_TFR_INFLAZIONE * np.asarray(inflazione, dtype=float)


def aliquota_tfr(tfr, anni):
    """Aliquota media della tassazione separata del TFR (art. 19 TUIR).

    Il reddito di riferimento è il TFR diviso per gli anni di lavoro e moltiplicato per 12; l'aliquota è quella media
    IRPEF su quel reddito, senza detrazioni.
    """
    tfr = np.asarray(tfr, dtype=float)
    rif = np.where(anni > 0, tfr / max(anni, 1) * 12, 0.0)
    a = np.where(rif > 0, irpef_lorda(rif) / np.where(rif > 0, rif, 1.0), 0.23)
    return a if a.ndim else float(a)


# ----------------------------------------------------------------------------- previdenza complementare
LIMITE_DEDUCIBILITA = 5_300.0  # dal 2026 (era 5.164,57 €)
ALIQUOTA_RENDIMENTI_FONDO = 0.20
ALIQUOTA_TITOLI_STATO = 0.125
ALIQUOTA_PRESTAZIONE_MAX = 0.15
ALIQUOTA_PRESTAZIONE_MIN = 0.09
RIDUZIONE_ANNUA_PRESTAZIONE = 0.003
ALIQUOTA_ANTICIPAZIONI_ALTRE = 0.23  # anticipazioni per casa e altre esigenze, riscatti per altre cause
QUOTA_CAPITALE_MAX = 0.50  # quota massima del montante liquidabile in capitale
ASSEGNO_SOCIALE_ANNUO = 546.24 * 13  # circa 7.100 € nel 2026

ANTICIPAZIONI = {
    # tipo: (quota massima della posizione, anni minimi di partecipazione, tassazione agevolata?)
    "spese_sanitarie": (0.75, 0, True),
    "prima_casa": (0.75, 8, False),
    "altre_esigenze": (0.30, 8, False),
}


def aliquota_prestazione(anni_partecipazione):
    """Aliquota sulle prestazioni: 15%, ridotta dello 0,30% per ogni anno oltre il quindicesimo, fino al 9%."""
    anni = np.asarray(anni_partecipazione, dtype=float)
    a = np.clip(ALIQUOTA_PRESTAZIONE_MAX - RIDUZIONE_ANNUA_PRESTAZIONE * np.maximum(anni - 15, 0),
                ALIQUOTA_PRESTAZIONE_MIN, ALIQUOTA_PRESTAZIONE_MAX)
    return a if a.ndim else float(a)


def aliquota_rendimenti(quota_titoli_stato: float, aliquota: float = ALIQUOTA_RENDIMENTI_FONDO) -> float:
    """Aliquota effettiva sui rendimenti: i titoli di Stato e equiparati sono tassati al 12,5%."""
    q = min(max(quota_titoli_stato, 0.0), 1.0)
    return aliquota * (1 - q) + ALIQUOTA_TITOLI_STATO * q


# ----------------------------------------------------------------------------- risparmio privato
ALIQUOTA_REDDITI_FINANZIARI = 0.26
IMPOSTA_BOLLO = 0.002  # sui conti titoli e i conti deposito; i fondi pensione ne sono esenti


# ----------------------------------------------------------------------------- pensione pubblica
COEFFICIENTI_TRASFORMAZIONE = {  # biennio 2025-2026, D.D. 20/11/2024
    57: 0.04204, 58: 0.04308, 59: 0.04419, 60: 0.04536, 61: 0.04661, 62: 0.04795, 63: 0.04936,
    64: 0.05088, 65: 0.05250, 66: 0.05423, 67: 0.05608, 68: 0.05808, 69: 0.06024, 70: 0.06258, 71: 0.06510,
}


def coefficiente_trasformazione(eta: float, anni_da_oggi: float = 0.0, riduzione_annua: float = 0.0) -> float:
    """Coefficiente di trasformazione del montante contributivo per età (interpolato per frazioni d'anno).

    `riduzione_annua` proietta la revisione biennale legata alla speranza di vita: ogni anno il coefficiente a parità
    di età si riduce di quella percentuale.
    """
    eta = min(max(eta, 57.0), 71.0)
    lo = int(np.floor(eta))
    hi = min(lo + 1, 71)
    ct = COEFFICIENTI_TRASFORMAZIONE
    c = ct[lo] + (ct[hi] - ct[lo]) * (eta - lo)
    return c * (1 - riduzione_annua) ** max(anni_da_oggi, 0.0)
