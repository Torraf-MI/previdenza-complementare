import json

import numpy as np
import pytest

from previdenza_complementare import cli, configurazione
from previdenza_complementare.analisi import aliquote_uscita
from previdenza_complementare.report import build_report, contesto


def test_il_fondo_negoziale_batte_il_pac(analisi_demo):
    a = analisi_demo
    t = a.tabella()
    netto = t["Capitale netto"]
    assert netto["Fondo negoziale life-cycle"] > netto["TFR in azienda + PAC in ETF"]
    assert t.loc["PIP assicurativo", "Capitale netto"] < t.loc["Fondo negoziale life-cycle", "Capitale netto"]
    s = a.sintesi_simulazione()
    assert s.loc["Fondo negoziale life-cycle", "Meglio del PAC"] > 0.95
    assert len(a.esiti[0].netto) == 300


def test_scomposizione_somma(analisi_demo):
    d = analisi_demo.scomposizione
    t = analisi_demo.tabella()
    assert d["effetto"].sum() == pytest.approx(t.loc["Fondo negoziale life-cycle", "Capitale netto"])
    assert d["netto"].iloc[0] == pytest.approx(t.loc["TFR in azienda + PAC in ETF", "Capitale netto"])
    assert d.loc["Contributo del datore", "effetto"] > 0


def test_mappa_e_sensibilita(analisi_demo):
    m = analisi_demo.mappa
    assert (m.values > 0).all()
    assert m.loc[25, 90_000] > m.loc[60, 20_000]
    s = analisi_demo.sensibilita
    assert (np.diff(s.values, axis=1) > 0).all() and (np.diff(s.values, axis=0) > 0).all()


def test_aliquote_uscita():
    t = aliquote_uscita(np.array([10, 35]))
    assert list(t["Fondo pensione"]) == pytest.approx([0.15, 0.09])


def test_json_andata_e_ritorno(tmp_path):
    cfg = configurazione.esempio()
    p = configurazione.salva(cfg, tmp_path / "c.json")
    cfg2 = configurazione.carica(p)
    assert [s.nome for s in cfg2.strategie] == [s.nome for s in cfg.strategie]
    assert cfg2.lavoratore == cfg.lavoratore
    assert cfg2.strategie[4].fondo.comparto.nome == "Life-cycle"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("strategie")
    d["anticipazioni"] = [{"eta": 40, "importo": 20_000, "tipo": "prima_casa"}]
    cfg3 = configurazione.da_dizionario(d)
    assert len(cfg3.strategie) == 6 and cfg3.anticipazioni[0].importo == 20_000


def test_esempio_json_del_repository():
    cfg = configurazione.carica("esempi/giulia.json")
    assert cfg.lavoratore.nome == "Giulia Conti"


def test_report_e_cli(tmp_path, analisi_demo, capsys):
    out = build_report(analisi_demo, tmp_path / "r.html")
    html = out.read_text(encoding="utf-8")
    assert "Fondo negoziale life-cycle" in html and "plotly" in html
    assert contesto(analisi_demo)["kpi"]
    assert cli.main(["--demo", "--veloce", "--output", str(tmp_path / "c.html")]) == 0
    assert "Report salvato" in capsys.readouterr().out
    assert (tmp_path / "c.html").exists()
