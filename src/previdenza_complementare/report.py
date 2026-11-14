"""Grafici interattivi (plotly) e report HTML per il lavoratore."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from jinja2 import Environment, PackageLoader, select_autoescape
from plotly.offline import get_plotlyjs, get_plotlyjs_version

from . import normativa as nv
from .analisi import Analisi, aliquote_uscita
from .mercato import COMPARTI

BLU, BLU_SCURO, ACQUA, ARANCIO = "#2a78d6", "#1c5cab", "#1baf7a", "#eb6834"
ROSSO, GIALLO, VIOLA, GRIGIO = "#e34948", "#e8a317", "#8a5cd1", "#8c8b86"
TESTO, TESTO_SECONDARIO, GRIGLIA = "#222222", "#52514e", "#e6e5e1"
PALETTE = [GRIGIO, ARANCIO, GIALLO, VIOLA, ACQUA, ROSSO, BLU, BLU_SCURO]
PLOTLY_CDN = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"


def _eur(x: float, dec: int = 0) -> str:
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'−' if x < -0.5 * 10**-dec else ''}{s} €"


def _pct(x: float, dec: int = 1, segno: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    s = f"{x * 100:+.{dec}f}%" if segno else f"{x * 100:.{dec}f}%"
    return s.replace(".", ",").replace("-", "−")


def _num(x: float, dec: int = 0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "−")


def _layout(fig: go.Figure, titolo: str, altezza: int = 420) -> go.Figure:
    fig.update_layout(
        title={"text": titolo, "x": 0, "font": {"size": 15, "color": TESTO}},
        height=altezza, template="plotly_white",
        font={"family": "Segoe UI, Helvetica, Arial, sans-serif", "size": 12, "color": TESTO_SECONDARIO},
        margin={"l": 70, "r": 20, "t": 60, "b": 50}, separators=",.",
        hoverlabel={"bgcolor": "white", "font_color": TESTO}, legend={"orientation": "h", "y": -0.16, "x": 0},
    )
    fig.update_xaxes(gridcolor=GRIGLIA, zeroline=False)
    fig.update_yaxes(gridcolor=GRIGLIA, zerolinecolor="#bdbcb6")
    return fig


def _a_capo(testo: str, larghezza: int = 16) -> str:
    righe, riga = [], ""
    for parola in testo.split():
        if riga and len(riga) + len(parola) + 1 > larghezza:
            righe.append(riga)
            riga = parola
        else:
            riga = f"{riga} {parola}".strip()
    return "<br>".join(righe + [riga])


def _colori(a: Analisi) -> dict[str, str]:
    return {s.nome: PALETTE[i % len(PALETTE)] for i, s in enumerate(a.cfg.strategie)}


def _esiti(a: Analisi):
    return a.esiti if a.esiti else a.attesi


# ----------------------------------------------------------------------------- grafici
def grafico_pensione(a: Analisi) -> go.Figure:
    """Reddito netto in pensione: INPS più rendita complementare, rispetto all'ultimo stipendio."""
    p = a.inps
    nomi = [e.strategia.nome for e in _esiti(a)][::-1]
    rendite = [float(np.median(a.rendita(e.netto))) for e in _esiti(a)][::-1]
    fig = go.Figure()
    fig.add_bar(y=nomi, x=[p["netta"]] * len(nomi), name="Pensione INPS netta", orientation="h",
                marker_color="#c9d8ec", hovertemplate="Pensione INPS netta: %{x:,.0f} € l'anno<extra></extra>")
    fig.add_bar(y=nomi, x=rendite, name="Rendita dal TFR e dal risparmio", orientation="h", marker_color=BLU_SCURO,
                text=[f"+{_eur(r / 12)} al mese" for r in rendite], textposition="outside", cliponaxis=False,
                hovertemplate="%{y}<br>rendita netta: %{x:,.0f} € l'anno<extra></extra>")
    fig.add_vline(x=p["ultimo_netto"], line_color=GRIGIO, line_dash="dot",
                  annotation_text=f"ultimo stipendio netto {_eur(p['ultimo_netto'])}",
                  annotation_position="top right")
    fig.add_vline(x=p["obiettivo"], line_color=ROSSO, line_dash="dash",
                  annotation_text=f"obiettivo: {_pct(a.cfg.lavoratore.tasso_sostituzione_obiettivo, 0)} dell'ultimo "
                                  "netto", annotation_position="top left")
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Reddito netto annuo in pensione (€ di oggi)", tickformat=",.0f",
                     range=[0, max(p["ultimo_netto"], p["netta"] + max(rendite)) * 1.2])
    fig.update_yaxes(automargin=True)
    return _layout(fig, f"Il reddito in pensione a {_num(a.cfg.lavoratore.eta_pensione)} anni: INPS più rendita "
                        "(scenario mediano)", 160 + 48 * len(nomi))


def grafico_scomposizione(a: Analisi) -> go.Figure:
    d = a.scomposizione
    passi = list(d.index)
    misure = ["absolute"] + ["relative"] * (len(passi) - 1) + ["total"]
    x = [_a_capo(v) for v in passi + [a.cfg.fondo]]
    y = list(d["effetto"]) + [d["netto"].iloc[-1]]
    fig = go.Figure(go.Waterfall(
        orientation="v", x=x, y=y, measure=misure,
        text=[_eur(v) if i in (0, len(y) - 1) else f"+{_eur(v)}" if v >= 0 else _eur(v) for i, v in enumerate(y)],
        textposition="outside", cliponaxis=False,
        increasing={"marker": {"color": ACQUA}}, decreasing={"marker": {"color": ROSSO}},
        totals={"marker": {"color": BLU_SCURO}}, connector={"line": {"color": "#bdbcb6"}},
        hovertemplate="%{x}: %{y:,.0f} €<extra></extra>"))
    fig.update_yaxes(title="Capitale netto al pensionamento (€ di oggi)", tickformat=",.0f",
                     range=[0, max(d["netto"]) * 1.15])
    fig.update_xaxes(tickangle=0, automargin=True)
    fig.update_layout(showlegend=False)
    return _layout(fig, "Da dove viene il vantaggio del fondo pensione sul PAC in ETF", 460)


def grafico_composizione(a: Analisi) -> go.Figure:
    """Il capitale netto (scenario centrale) diviso per origine."""
    t = a.tabella().iloc[::-1]
    nomi = list(t.index)
    voci = {
        "Versato da te (netto)": (t["Sforzo netto"], GIALLO),
        "Contributo del datore": (t["Contributi del datore"], ACQUA),
        "Rimborso IRPEF": (t["Risparmio d'imposta"], VIOLA),
    }
    tfr = np.array([e.tfr_versato + a.cfg.lavoratore.tfr_pregresso for e in a.attesi][::-1])
    voci["TFR"] = (tfr, "#c9d8ec")
    base = sum(v for v, _ in voci.values())
    voci["Rendimenti meno costi e imposte"] = (t["Capitale netto"] - base, BLU_SCURO)
    fig = go.Figure()
    for nome, (v, col) in voci.items():
        fig.add_bar(y=nomi, x=v, name=nome, orientation="h", marker_color=col,
                    hovertemplate=f"%{{y}}<br>{nome}: %{{x:,.0f}} €<extra></extra>")
    fig.add_scatter(y=nomi, x=t["Capitale netto"], mode="text", text=[_eur(x) for x in t["Capitale netto"]],
                    textposition="middle right", showlegend=False, hoverinfo="skip", cliponaxis=False)
    fig.update_layout(barmode="relative")
    fig.update_xaxes(title="Capitale netto al pensionamento (€ di oggi)", tickformat=",.0f",
                     range=[min(0, (t["Capitale netto"] - base).min() * 1.1), t["Capitale netto"].max() * 1.22])
    fig.update_yaxes(automargin=True)
    return _layout(fig, "Che cosa c'è nel capitale finale: chi ha messo i soldi e quanto hanno reso", 160 + 48 * len(t))


def grafico_simulazione(a: Analisi) -> go.Figure:
    col = _colori(a)
    fig = go.Figure()
    for e in _esiti(a):
        n = e.strategia.nome
        fig.add_box(x=e.netto, name=n, marker_color=col[n], boxpoints=False, hovertemplate=f"{n}<extra></extra>")
    fig.update_xaxes(title="Capitale netto al pensionamento (€ di oggi)", tickformat=",.0f")
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_layout(showlegend=False)
    n = len(a.esiti[0].netto) if a.esiti else 1
    return _layout(fig, f"Simulazione: {_num(n)} scenari di mercati e inflazione", 160 + 45 * len(a.cfg.strategie))


def grafico_accumulo(a: Analisi) -> go.Figure:
    col = _colori(a)
    eta = a.cfg.lavoratore.eta + np.arange(1, a.cfg.lavoratore.anni + 1)
    scelte = [a.cfg.riferimento, a.cfg.alternativa, a.cfg.fondo]
    fig = go.Figure()
    for nome in scelte:
        e = a.esito(nome)
        p = e.percorso
        c = col[nome]
        if p.shape[0] > 1:
            lo, hi = np.percentile(p, 10, axis=0), np.percentile(p, 90, axis=0)
            fig.add_scatter(x=np.r_[eta, eta[::-1]], y=np.r_[hi, lo[::-1]], fill="toself", fillcolor=c,
                            opacity=0.15, line={"width": 0}, showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=eta, y=np.median(p, axis=0), mode="lines", name=nome, line={"color": c, "width": 2.6},
                        hovertemplate=f"{nome}<br>%{{x}} anni: %{{y:,.0f}} €<extra></extra>")
    fig.update_xaxes(title="Età")
    fig.update_yaxes(title="Patrimonio lordo accumulato (€ di oggi)", tickformat=",.0f")
    return _layout(fig, "L'accumulo anno per anno: mediana e intervallo tra il 10° e il 90° percentile", 440)


def grafico_mappa(a: Analisi) -> go.Figure:
    m = a.mappa
    fig = go.Figure(go.Heatmap(
        z=m.values, x=[_eur(c) for c in m.columns], y=[f"{i} anni" for i in m.index],
        colorscale=[[0, "#effaf5"], [1, "#0b7a52"]], zmin=0,
        text=[[_pct(v, 0, segno=True) for v in r] for r in m.values], texttemplate="%{text}",
        hovertemplate="adesione a %{y}, RAL %{x}<br>fondo rispetto al PAC: %{text}<extra></extra>",
        colorbar={"title": "Vantaggio", "tickformat": ".0%"}))
    fig.update_xaxes(title="RAL di oggi", side="bottom")
    fig.update_yaxes(title="Età di adesione", autorange="reversed")
    return _layout(fig, "Quanto capitale netto in più dà il fondo negoziale rispetto al PAC, per età e reddito", 460)


def grafico_aliquote(a: Analisi) -> go.Figure:
    anni = np.arange(1, 41)
    tfr = a.cfg.lavoratore.ral * nv.QUOTA_TFR
    t = aliquote_uscita(anni, tfr)
    colori = {"Fondo pensione": ACQUA, "TFR in azienda": ARANCIO, "ETF (sulle plusvalenze)": ROSSO}
    fig = go.Figure()
    for c in t.columns:
        fig.add_scatter(x=anni, y=t[c], mode="lines", name=c, line={"color": colori[c], "width": 2.6},
                        hovertemplate=f"{c}<br>%{{x}} anni: %{{y:.1%}}<extra></extra>")
    fig.update_xaxes(title="Anni di partecipazione (o di lavoro, per il TFR)")
    fig.update_yaxes(title="Aliquota sulla parte tassabile", tickformat=".0%", range=[0, 0.3])
    return _layout(fig, "Le aliquote all'uscita: il fondo scende fino al 9% dopo 35 anni", 380)


def grafico_deduzione(a: Analisi) -> go.Figure:
    ral = np.arange(12_000, 100_001, 250)
    m = nv.aliquota_marginale_effettiva(ral, 1_000.0)
    fig = go.Figure(go.Scatter(x=ral, y=m, mode="lines", line={"color": VIOLA, "width": 2.4}, name="Rimborso",
                               hovertemplate="RAL %{x:,.0f} €: %{y:.1%} del contributo<extra></extra>"))
    r0 = a.cfg.lavoratore.ral
    m0 = nv.aliquota_marginale_effettiva(r0, 1_000.0)
    fig.add_scatter(x=[r0], y=[m0], mode="markers+text", marker={"color": ROSSO, "size": 11},
                    text=[f"{a.cfg.lavoratore.nome.split()[0]}: {_pct(m0, 0)}"], textposition="top center",
                    showlegend=False, hoverinfo="skip")
    fig.update_xaxes(title="RAL (€)", tickformat=",.0f")
    fig.update_yaxes(title="Imposte risparmiate su 1.000 € versati", tickformat=".0%", range=[0, 0.7])
    fig.update_layout(showlegend=False)
    return _layout(fig, "Quanto rimborsa il fisco: IRPEF, addizionali e la perdita delle detrazioni", 380)


def grafico_prestazione(a: Analisi) -> go.Figure:
    eta0 = a.cfg.lavoratore.eta_pensione
    colori = [BLU_SCURO, ARANCIO, VIOLA, ACQUA]
    fig = go.Figure()
    for i, o in enumerate(a.opzioni):
        H = o.reddito.shape[1]
        vivo = np.arange(H)[None, :] < o.vita[:, None]
        med = np.array([np.median(o.reddito[vivo[:, k], k]) if vivo[:, k].sum() > 20 else np.nan for k in range(H)])
        fig.add_scatter(x=eta0 + np.arange(H), y=med, mode="lines", name=o.nome,
                        line={"color": colori[i % 4], "width": 2.6},
                        hovertemplate=f"{o.nome}<br>%{{x:.0f}} anni: %{{y:,.0f}} € l'anno<extra></extra>")
    fig.update_xaxes(title="Età")
    fig.update_yaxes(title="Reddito netto annuo (€ di oggi)", tickformat=",.0f", rangemode="tozero")
    return _layout(fig, "Rendita o capitale: il reddito mediano dal fondo, finché si è in vita", 400)


def _grafici(a: Analisi) -> dict:
    g = {"pensione": grafico_pensione(a), "scomposizione": grafico_scomposizione(a),
         "composizione": grafico_composizione(a), "mappa": grafico_mappa(a), "aliquote": grafico_aliquote(a),
         "deduzione": grafico_deduzione(a), "prestazione": grafico_prestazione(a), "accumulo": grafico_accumulo(a)}
    if a.esiti:
        g["simulazione"] = grafico_simulazione(a)
    return g


def salva_grafici(a: Analisi, cartella: str | Path, scala: float = 2.0) -> list[Path]:
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    out = []
    for nome, fig in _grafici(a).items():
        p = cartella / f"{nome}.png"
        fig.write_image(str(p), width=1000, height=fig.layout.height or 420, scale=scala)
        out.append(p)
    return out


# ----------------------------------------------------------------------------- contesto
def contesto(a: Analisi) -> dict:
    lav = a.cfg.lavoratore
    p = a.inps
    t = a.tabella()
    rif, alt, fondo = a.cfg.riferimento, a.cfg.alternativa, a.cfg.fondo
    tf, ta = t.loc[fondo], t.loc[alt]
    sim = a.sintesi_simulazione()
    budget_anno = float(a.budget[0])
    lav_anno = lav.ral * a.cfg.contributo_lavoratore
    kpi = [
        ("Pensione INPS stimata", _eur(p["netta"] / 13) + " al mese",
         f"netti, su 13 mensilità: il {_pct(p['sostituzione_netta'], 0)} dell'ultimo stipendio netto"),
        ("Gap rispetto all'obiettivo", _eur(p["gap"]) + " l'anno" if p["gap"] > 0 else "nessuno",
         f"obiettivo: {_pct(lav.tasso_sostituzione_obiettivo, 0)} dell'ultimo netto"),
        (f"Capitale con «{fondo}»", _eur(tf["Capitale netto"]),
         f"netto, {_eur(tf['Rendita mensile netta'])} al mese di rendita"),
        (f"Capitale con «{alt}»", _eur(ta["Capitale netto"]),
         f"il fondo dà {_pct(tf['Capitale netto'] / ta['Capitale netto'] - 1, 0, segno=True)}"),
        ("Il tuo sforzo netto", _eur(budget_anno) + " l'anno",
         f"per versare {_eur(lav_anno)}: il resto lo rimborsa il fisco"),
    ]
    if sim is not None:
        kpi.append(("Scenari in cui il fondo batte il PAC", _pct(sim.loc[fondo, "Meglio del PAC"], 0),
                    f"su {_num(len(a.esiti[0].netto))} simulazioni"))
    strategie = []
    for e in a.attesi:
        n = e.strategia.nome
        r = t.loc[n]
        riga = {"nome": n, "descrizione": e.strategia.descrizione, "sforzo": _eur(r["Sforzo netto"]),
                "datore": _eur(r["Contributi del datore"]), "fisco": _eur(r["Risparmio d'imposta"]),
                "lordo": _eur(r["Capitale lordo"]), "costi": _eur(r["Costi"]),
                "imp_rend": _eur(r["Imposte sui rendimenti"]), "imp_uscita": _eur(r["Imposte all'uscita"]),
                "netto": _eur(r["Capitale netto"]), "rendita": _eur(r["Rendita mensile netta"]),
                "diff": _eur(r["Rispetto al TFR in azienda"]), "migliore": n == fondo, "rif": n == rif}
        strategie.append(riga)
    ctx = {
        "nome": lav.nome, "nome_breve": lav.nome.split()[0], "eta": _num(lav.eta), "ral": _eur(lav.ral),
        "eta_pensione": _num(lav.eta_pensione), "anni": lav.anni, "oggi": date.today().strftime("%d/%m/%Y"),
        "kpi": kpi, "inps": {k: (_eur(v) if isinstance(v, float) and abs(v) > 2 else v) for k, v in p.items()},
        "coeff": _pct(p["coefficiente"], 3), "sost_lorda": _pct(p["sostituzione_lorda"], 0),
        "sost_netta": _pct(p["sostituzione_netta"], 0), "anni_contributi": _num(p["anni_contributi"], 1),
        "densita": _pct(lav.densita_contributiva, 0), "pil": _pct(lav.crescita_pil_reale, 1),
        "obiettivo_pct": _pct(lav.tasso_sostituzione_obiettivo, 0), "gap": p["gap"] > 0,
        "sensibilita": {"colonne": [int(c) for c in a.sensibilita.columns],
                        "righe": [{"nome": i, "valori": [_pct(v, 0) for v in r]} for i, r in a.sensibilita.iterrows()]},
        "strategie": strategie, "rif": rif, "alt": alt, "fondo": fondo,
        "contr_lav": _pct(a.cfg.contributo_lavoratore, 1), "contr_dat": _pct(a.cfg.contributo_datore, 1),
        "budget_anno": _eur(budget_anno), "lav_anno": _eur(lav_anno),
        "marginale": _pct(nv.aliquota_marginale_effettiva(lav.ral, 1_000.0), 0),
        "limite": _eur(nv.LIMITE_DEDUCIBILITA, 2), "aliquota_uscita": _pct(a.atteso(fondo).aliquota_uscita, 1),
        "aliquota_tfr": _pct(a.atteso(rif).extra["aliquota_tfr"], 1),
        "scomp": [{"passo": i, "effetto": _eur(r["effetto"]), "netto": _eur(r["netto"])}
                  for i, r in a.scomposizione.iterrows()],
        "comparti": [{"nome": c.nome, "descrizione": c.descrizione} for c in COMPARTI.values()],
        "costi": a.cfg.costi, "pct": _pct, "eur": _eur, "num": _num,
        "fattore": _num(a.fattore_rendita, 1),
        "opzioni": [{"nome": o.nome, "descrizione": o.descrizione, **{k: v for k, v in o.sintesi().items()}}
                    for o in a.opzioni],
        "quota_rendita": _pct(1 - a.cfg.rendita.quota_capitale, 0), "mercato": a.cfg.mercato,
        "anticipazioni": [{"eta": _num(x.eta), "importo": _eur(x.importo), "tipo": x.tipo.replace("_", " ")}
                          for x in a.cfg.anticipazioni],
        "mappa_min": _pct(float(np.nanmin(a.mappa.values)), 0), "mappa_max": _pct(float(np.nanmax(a.mappa.values)), 0),
    }
    if sim is not None:
        ctx["sim"] = [{"nome": n, "mediana": _eur(r["Mediana"]), "p5": _eur(r["5° percentile"]),
                       "p95": _eur(r["95° percentile"]), "rendita": _eur(r["Rendita mensile mediana"]),
                       "vs_rif": _pct(r["Meglio del TFR in azienda"], 0), "vs_pac": _pct(r["Meglio del PAC"], 0),
                       "migliore": n == fondo} for n, r in sim.iterrows()]
        ctx["scenari"] = _num(len(a.esiti[0].netto))
    return ctx


def build_report(a: Analisi, output: str | Path, data_note: str = "", offline: bool = False) -> Path:
    env = Environment(loader=PackageLoader("previdenza_complementare", "templates"), autoescape=select_autoescape())
    g = {k: fig.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True})
         for k, fig in _grafici(a).items()}
    html = env.get_template("report.html.j2").render(
        **contesto(a), grafici=g, data_note=data_note, plotly_cdn=PLOTLY_CDN,
        plotly_inline=get_plotlyjs() if offline else None)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
