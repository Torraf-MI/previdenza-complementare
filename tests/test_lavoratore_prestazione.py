import numpy as np
import pytest

from previdenza_complementare import normativa as nv
from previdenza_complementare import prestazione as pr
from previdenza_complementare.lavoratore import Lavoratore


def test_pensione_contributiva_a_mano():
    lav = Lavoratore("T", 30, 30_000, eta_pensione=67, crescita_reale=0.0, crescita_pil_reale=0.0,
                     riduzione_coefficienti=0.0)
    p = lav.pensione_inps()
    montante = 0.33 * 30_000 * 37
    assert p["montante"] == pytest.approx(montante)
    assert p["lorda"] == pytest.approx(montante * 0.05608)
    assert p["netta"] == pytest.approx(p["lorda"] - nv.imposte_pensione(p["lorda"]))
    assert p["gap"] == pytest.approx(max(0.8 * nv.stipendio_netto(30_000) - p["netta"], 0))


def test_densita_e_montante_pregresso():
    a = Lavoratore("T", 30, 30_000, eta_pensione=67, crescita_reale=0.0, crescita_pil_reale=0.0)
    b = Lavoratore("T", 30, 30_000, eta_pensione=67, crescita_reale=0.0, crescita_pil_reale=0.0,
                   densita_contributiva=0.5)
    assert b.pensione_inps()["montante"] == pytest.approx(a.pensione_inps()["montante"] / 2)
    c = Lavoratore("T", 30, 30_000, eta_pensione=67, anni_contributi=5, crescita_reale=0.0, crescita_pil_reale=0.0)
    assert c.stima_montante_inps() == pytest.approx(5 * 0.33 * 30_000)
    with pytest.raises(ValueError):
        Lavoratore("T", 70, 30_000, eta_pensione=67)


def test_ral_cresce_fino_all_eta_indicata():
    lav = Lavoratore("T", 40, 30_000, eta_pensione=60, crescita_reale=0.02, eta_fine_crescita=50)
    r = lav.ral_percorso()
    assert len(r) == 20 and r[0] == 30_000
    assert r[10] == pytest.approx(30_000 * 1.02**10) and r[-1] == pytest.approx(r[10])


def test_gompertz_calibrata():
    a = pr.calibra(20.0, 67)
    assert pr.speranza(a, 67) == pytest.approx(20.0, abs=0.01)
    m = pr.Mortalita("F", 0)
    assert m.speranza(67) == pytest.approx(pr.SPERANZA_67["F"], abs=0.01)
    rng = np.random.default_rng(1)
    assert m.campiona(67, 20_000, rng).mean() == pytest.approx(pr.SPERANZA_67["F"], abs=0.3)
    # gli assicurati vivono più a lungo
    assert pr.Mortalita("F", 0, True).speranza(67) > m.speranza(67) + 2


def test_fattore_rendita():
    m = pr.Mortalita("M", 0, assicurati=True)
    ip = pr.IpotesiRendita(tasso_tecnico=0.0, caricamento=0.0)
    f = pr.fattore_rendita(67, m, ip)
    assert m.speranza(67) < f < m.speranza(67) + 1  # rendita anticipata: circa mezzo anno in più
    assert pr.fattore_rendita(67, m, pr.IpotesiRendita(caricamento=0.015)) == pytest.approx(f * 1.015)


def test_opzioni_di_prestazione():
    o = pr.opzioni(100_000, 0.6, 0.09, 67, "F", 0, n=500)
    nomi = [x.nome for x in o]
    assert nomi[0] == "Rendita vitalizia" and "durata definita" in nomi[2]
    s = [x.sintesi() for x in o]
    assert s[0]["Probabilità di esaurire il capitale"] == 0 and s[0]["Eredità media"] == 0
    netto = 1 - 0.09 * 0.6
    f = pr.fattore_rendita(67, pr.Mortalita("F", 0, True), pr.IpotesiRendita())
    assert o[0].reddito_iniziale == pytest.approx(100_000 / f * netto)
    # la rendita a durata definita si ferma: chi vive oltre resta senza
    assert 0.2 < s[2]["Probabilità di esaurire il capitale"] < 0.8
    assert s[1]["Eredità media"] > 0
