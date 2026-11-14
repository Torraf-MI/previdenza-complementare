import numpy as np
import pytest

from previdenza_complementare import normativa as nv
from previdenza_complementare.configurazione import Costi, strategie_standard, veicoli
from previdenza_complementare.lavoratore import Lavoratore
from previdenza_complementare.mercato import COMPARTI
from previdenza_complementare.strategie import Anticipazione, Strategia, Veicolo, budget_netto, deduzioni, simula

SENZA_COSTI = Costi(0, 0, 0, 0, 0, 0)


def lav(**kw):
    base = dict(nome="Test", eta=40, ral=30_000, eta_pensione=60, crescita_reale=0.0)
    base.update(kw)
    return Lavoratore(**base)


def test_deduzioni_con_limite():
    lav_d, dat_d, non = deduzioni(np.array([60_000.0]), np.array([3_000.0]), np.array([3_000.0]))
    assert dat_d[0] == 3_000 and lav_d[0] == pytest.approx(2_300) and non[0] == pytest.approx(700)


def test_tfr_in_azienda_calcolato_a_mano(costanti):
    l_ = lav()
    s = costanti(20, inflazione=0.0)
    e = simula(Strategia("TFR", "azienda"), l_, s)
    q = 30_000 * nv.QUOTA_TFR
    v = 0.0
    for _ in range(20):
        v = v * (1 + 0.015 * 0.83) + q
    assert e.tfr_lordo[0] == pytest.approx(v)
    al = nv.aliquota_tfr(q * 20, 20)
    assert e.imposta_tfr[0] == pytest.approx(al * q * 20)
    assert e.extra["aliquota_tfr"] == pytest.approx(al)


def test_fondo_senza_rendimenti_tassa_tfr_e_dedotti(costanti):
    l_ = lav()
    v = veicoli(SENZA_COSTI)["negoziale"]
    st = Strategia("F", "fondo", fondo=v, contributo_lavoratore=0.01, contributo_datore=0.02)
    e = simula(st, l_, costanti(20))
    versato = 20 * 30_000 * (nv.QUOTA_TFR + 0.03)
    assert e.fondo_lordo[0] == pytest.approx(versato)
    assert e.aliquota_uscita == pytest.approx(0.135)  # 20 anni: 15% − 5 × 0,3%
    assert e.imposta_fondo[0] == pytest.approx(0.135 * versato)
    assert e.risparmio_fiscale == pytest.approx(20 * nv.risparmio_deduzione(30_000, 300))


def test_contributi_non_dedotti_esenti_all_uscita(costanti):
    l_ = lav(ral=100_000)
    v = veicoli(SENZA_COSTI)["negoziale"]
    st = Strategia("F", "fondo", fondo=v, contributo_lavoratore=0.05, contributo_datore=0.02)
    e = simula(st, l_, costanti(20))
    tfr = 20 * 100_000 * nv.QUOTA_TFR
    assert e.imponibile_fondo[0] == pytest.approx(tfr + 20 * nv.LIMITE_DEDUCIBILITA)
    assert e.extra["non_dedotti"] == pytest.approx(20 * (7_000 - nv.LIMITE_DEDUCIBILITA))


def test_fondo_tassa_i_rendimenti_ogni_anno_con_il_credito(costanti):
    l_ = lav()
    v = Veicolo("F", COMPARTI["azionario"], 0, 0)
    s = costanti(20, azioni=0.05, obbligazioni=0.05)
    e = simula(Strategia("F", "fondo", fondo=v), l_, s)
    al = nv.aliquota_rendimenti(COMPARTI["azionario"].quota_titoli_stato(0.75))
    r = 0.05 * (1 - al)
    q = 30_000 * nv.QUOTA_TFR
    atteso = q * ((1 + r) ** 20 - 1) / r
    assert e.fondo_lordo[0] == pytest.approx(atteso)
    # anno negativo: nessuna imposta, credito usato l'anno dopo
    s2 = costanti(2, azioni=0.0, obbligazioni=0.0)
    s2.azioni[0, :] = [0.10, -0.10]
    s2.obbligazioni[0, :] = [0.10, -0.10]
    l2 = lav(eta=58)
    e2 = simula(Strategia("F", "fondo", fondo=v), l2, s2)
    assert e2.imposte_rendimenti[0] == 0


def test_pac_tassa_solo_le_plusvalenze_alla_fine(costanti):
    l_ = lav()
    etf = Veicolo("ETF", COMPARTI["azionario"], 0, 0, bollo=False, tassazione="plusvalenze")
    st = Strategia("PAC", "azienda", risparmio=etf)
    budget = np.full(20, 1_000.0)
    e = simula(st, l_, costanti(20, azioni=0.04, obbligazioni=0.04), budget)
    lordo = 1_000 * (1.04**20 - 1) / 0.04
    assert e.risparmio_lordo[0] == pytest.approx(lordo)
    al = nv.aliquota_rendimenti(COMPARTI["azionario"].quota_titoli_stato(0.75), 0.26)
    assert e.imposta_risparmio[0] == pytest.approx(al * (lordo - 20_000))
    assert e.imposte_rendimenti[0] == 0


def test_bollo_riduce_il_pac(costanti):
    l_ = lav()
    budget = np.full(20, 1_000.0)
    con = Veicolo("ETF", COMPARTI["bilanciato"], 0, 0, bollo=True, tassazione="plusvalenze")
    senza = Veicolo("ETF", COMPARTI["bilanciato"], 0, 0, bollo=False, tassazione="plusvalenze")
    s = costanti(20, azioni=0.03, obbligazioni=0.03)
    a = simula(Strategia("a", risparmio=con), l_, s, budget).risparmio_lordo[0]
    b = simula(Strategia("b", risparmio=senza), l_, s, budget).risparmio_lordo[0]
    assert a < b and a / b > 0.97


def test_parita_di_sforzo_netto(costanti):
    l_ = lav()
    std = strategie_standard(0.012, 0.02)
    budget = budget_netto(l_, 0.012, 0.02)
    s = costanti(20, azioni=0.04, obbligazioni=0.02, inflazione=0.02, liquidita=0.02)
    sforzi = {st.nome: simula(st, l_, s, budget).sforzo_netto for st in std}
    assert len({round(v, 6) for v in sforzi.values()}) == 1
    assert budget[0] == pytest.approx(360 - nv.risparmio_deduzione(30_000, 360))


def test_garantito_restituisce_i_versamenti(costanti):
    l_ = lav()
    v = Veicolo("G", COMPARTI["garantito"], 0.01, 0)
    e = simula(Strategia("G", "fondo", fondo=v), l_, costanti(20, azioni=-0.02, obbligazioni=-0.02))
    assert e.fondo_lordo[0] == pytest.approx(20 * 30_000 * nv.QUOTA_TFR)


def test_anticipazione_prima_casa_dal_fondo_al_23(costanti):
    l_ = lav()
    v = veicoli(SENZA_COSTI)["negoziale"]
    st = Strategia("F", "fondo", fondo=v)
    e = simula(st, l_, costanti(20), anticipazioni=[Anticipazione(50, 10_000, "prima_casa")])
    assert e.anticipazioni_nette[0] == pytest.approx(10_000)
    assert e.imposte_anticipazioni[0] == pytest.approx(10_000 / 0.77 * 0.23)
    versato = 20 * 30_000 * nv.QUOTA_TFR
    assert e.fondo_lordo[0] == pytest.approx(versato - 10_000 / 0.77)


def test_anticipazione_prima_degli_8_anni_dal_tfr_o_dal_risparmio(costanti):
    l_ = lav(tfr_pregresso=20_000, anni_tfr_pregresso=10)
    v = veicoli(SENZA_COSTI)
    st = Strategia("F", "fondo", fondo=v["negoziale"], risparmio=v["deposito"])
    e = simula(st, l_, costanti(20), np.full(20, 2_000.0), [Anticipazione(43, 5_000, "prima_casa")])
    # il fondo ha 3 anni: paga il TFR rimasto in azienda; solo le quote (non le rivalutazioni) sono tassate al 23%
    assert e.anticipazioni_nette[0] == pytest.approx(5_000)
    valore = 20_000 * (1 + 0.015 * 0.83) ** 3
    q = 20_000 / valore
    lordo = 5_000 / (1 - 0.23 * q)
    assert e.imposte_anticipazioni[0] == pytest.approx(lordo * 0.23 * q)


def test_pip_costa_piu_del_negoziale(costanti):
    l_ = lav()
    v = veicoli(Costi())
    s = costanti(20, azioni=0.05, obbligazioni=0.03, inflazione=0.02)
    neg = simula(Strategia("N", "fondo", fondo=v["negoziale"], contributo_lavoratore=0.012), l_, s)
    pip = simula(Strategia("P", "fondo", fondo=v["pip"], contributo_lavoratore=0.012), l_, s)
    assert pip.costi[0] > 3 * neg.costi[0]
    assert pip.netto[0] < neg.netto[0]


def test_errori():
    with pytest.raises(ValueError):
        Strategia("x", "fondo")
    with pytest.raises(ValueError):
        Anticipazione(40, 1_000, "vacanze")
    with pytest.raises(ValueError):
        Veicolo("x", None, tassazione="boh")
