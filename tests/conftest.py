import numpy as np
import pytest

from previdenza_complementare import configurazione
from previdenza_complementare.analisi import analizza
from previdenza_complementare.mercato import Scenari


@pytest.fixture(scope="session")
def analisi_demo():
    cfg = configurazione.esempio()
    cfg.scenari = 300
    return analizza(cfg)


def scenari_costanti(anni: int, azioni=0.0, obbligazioni=0.0, inflazione=0.0, liquidita=0.0) -> Scenari:
    def f(x):
        return np.full((1, anni), x, dtype=float)

    return Scenari(f(azioni), f(obbligazioni), f(inflazione), f(liquidita))


@pytest.fixture
def costanti():
    return scenari_costanti
