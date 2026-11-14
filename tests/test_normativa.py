import numpy as np
import pytest

from previdenza_complementare import normativa as nv


def test_irpef_scaglioni_2026():
    assert nv.irpef_lorda(28_000) == pytest.approx(6_440)
    assert nv.irpef_lorda(50_000) == pytest.approx(6_440 + 22_000 * 0.33)
    assert nv.irpef_lorda(60_000) == pytest.approx(13_700 + 10_000 * 0.43)
    assert nv.irpef_lorda(-5) == 0


def test_detrazioni_lavoro_e_pensione():
    assert nv.detrazione_lavoro(15_000) == pytest.approx(1_955)
    assert nv.detrazione_lavoro(20_000) == pytest.approx(1_910 + 1_190 * 8 / 13)
    assert nv.detrazione_lavoro(30_000) == pytest.approx(1_910 * 20 / 22 + 65)
    assert nv.detrazione_lavoro(50_000) == 0
    assert nv.detrazione_pensione(8_000) == pytest.approx(1_955)
    assert nv.detrazione_pensione(28_000) == pytest.approx(700)
    assert nv.ulteriore_detrazione_cuneo(36_000) == pytest.approx(500)


def test_risparmio_deduzione_include_il_decalage_delle_detrazioni():
    # imponibile tra 28.000 e 32.000: 33% + perdita della detrazione (1.910/22.000) + addizionali
    atteso = 0.33 + 1_910 / 22_000 + nv.ADDIZIONALI
    assert nv.risparmio_deduzione(32_000, 1_000) / 1_000 == pytest.approx(atteso, abs=1e-6)
    # tra 32.000 e 40.000 si perde anche l'ulteriore detrazione del cuneo: oltre il 56%
    assert nv.aliquota_marginale_effettiva(40_000) == pytest.approx(atteso + 1 / 8, abs=1e-6)
    # la deduzione non può superare il reddito
    assert nv.risparmio_deduzione(10_000, 50_000) == pytest.approx(nv.imposte_lavoro(10_000 * 0.9081)
                                                                   - nv.imposte_lavoro(0))


def test_stipendio_netto_plausibile():
    assert 24_000 < nv.stipendio_netto(32_000) < 25_000
    assert nv.stipendio_netto(np.array([30_000, 60_000])).shape == (2,)


def test_tfr():
    assert nv.QUOTA_TFR == pytest.approx(0.0691, abs=1e-4)
    assert nv.rivalutazione_tfr(0.02) == pytest.approx(0.03)
    # reddito di riferimento 2.000 × 12 = 24.000 €: aliquota media 23%
    assert nv.aliquota_tfr(20_000, 10) == pytest.approx(0.23)
    # 4.000 € l'anno: riferimento 48.000 €
    assert nv.aliquota_tfr(40_000, 10) == pytest.approx(nv.irpef_lorda(48_000) / 48_000)


def test_aliquota_prestazione_dal_15_al_9():
    assert nv.aliquota_prestazione(10) == pytest.approx(0.15)
    assert nv.aliquota_prestazione(15) == pytest.approx(0.15)
    assert nv.aliquota_prestazione(25) == pytest.approx(0.12)
    assert nv.aliquota_prestazione(35) == pytest.approx(0.09)
    assert nv.aliquota_prestazione(45) == pytest.approx(0.09)


def test_aliquota_rendimenti_con_titoli_di_stato():
    assert nv.aliquota_rendimenti(0.0) == pytest.approx(0.20)
    assert nv.aliquota_rendimenti(0.5) == pytest.approx(0.1625)
    assert nv.aliquota_rendimenti(0.5, 0.26) == pytest.approx(0.1925)


def test_coefficienti_di_trasformazione():
    assert nv.coefficiente_trasformazione(67) == pytest.approx(0.05608)
    assert nv.coefficiente_trasformazione(71) == pytest.approx(0.06510)
    assert nv.coefficiente_trasformazione(67.5) == pytest.approx((0.05608 + 0.05808) / 2)
    assert nv.coefficiente_trasformazione(75) == pytest.approx(0.06510)
    assert nv.coefficiente_trasformazione(67, 10, 0.01) == pytest.approx(0.05608 * 0.99**10)


def test_limite_deducibilita_2026():
    assert nv.LIMITE_DEDUCIBILITA == 5_300
