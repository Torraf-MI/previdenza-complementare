"""Previdenza complementare in Italia: TFR in azienda o fondo pensione, gap della pensione pubblica, fisco, rendita o
capitale, confronto con un PAC in ETF."""

from .analisi import Analisi, analizza
from .configurazione import Configurazione, Costi, carica, esempio, salva, strategie_standard
from .lavoratore import Lavoratore
from .mercato import COMPARTI, Comparto, IpotesiMercato
from .normativa import aliquota_prestazione, aliquota_tfr, risparmio_deduzione, stipendio_netto
from .strategie import Anticipazione, Strategia, Veicolo, simula

__all__ = [
    "Analisi", "Anticipazione", "COMPARTI", "Comparto", "Configurazione", "Costi", "IpotesiMercato", "Lavoratore",
    "Strategia", "Veicolo", "aliquota_prestazione", "aliquota_tfr", "analizza", "carica", "esempio",
    "risparmio_deduzione", "salva", "simula", "stipendio_netto", "strategie_standard",
]
__version__ = "0.1.0"
