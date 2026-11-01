"""Der Schmerztagebuch-Bericht als PDF - und als CSV.

Gedacht zum Ausdrucken und Mitnehmen. Darum steht alles auf wenigen Seiten,
die Zahlen stehen neben den Balken, und jede Auswertung sagt dazu, auf wie
vielen Messungen sie beruht.

Was hier bewusst nicht steht: eine Bewertung. Keine Tageshöchstmengen, keine
Hinweise, ob ein Mittel „wirkt". Der Bericht beschreibt Aufzeichnungen -
beurteilen kann das nur jemand, der die Person kennt.
"""

from __future__ import annotations

import colorsys
import csv
import datetime as dt
import io

from . import painstats as ps
from .pdfwriter import NORMAL, SEITE_BREITE, Dokument, Seite, textbreite  # noqa: F401

RAND = 45.0
BREITE = SEITE_BREITE - 2 * RAND
FUSS = 800.0            # ab hier wird umgebrochen

GRAU_LINIE = 0.82
GRAU_TEXT = 0.42


def vas_farbe(wert: float) -> tuple[float, float, float]:
    """Dieselbe Skala wie in der App: Grün bei 0, Rot bei 10."""
    stufe = max(0.0, min(10.0, float(wert)))
    ton = (130 - stufe * 13) / 360.0
    return colorsys.hls_to_rgb(ton, 0.42, 0.68)


def _zahl(wert, nachkomma: int = 1) -> str:
    """Deutsch geschrieben, mit Komma. None wird zum Gedankenstrich."""
    if wert is None:
        return "–"
    if isinstance(wert, float) and nachkomma:
        return f"{wert:.{nachkomma}f}".replace(".", ",")
    return str(int(wert)) if float(wert).is_integer() else str(wert).replace(".", ",")


def _datum(zeit: dt.datetime | None) -> str:
    return zeit.strftime("%d.%m.%Y") if zeit else "–"


class Layout:
    """Hält die Schreibmarke und bricht um, wenn die Seite voll ist."""

    def __init__(self, dok: Dokument, kopf: str, person: str) -> None:
        self.dok = dok
        self.kopf = kopf
        self.person = person
        self.nummer = 0
        self.seite: Seite | None = None
        self.y = 0.0
        self.neue_seite()

    def neue_seite(self) -> None:
        self.nummer += 1
        self.seite = self.dok.neue_seite()
        self.seite.text(RAND, 32, self.kopf, 8, grau=0.55)
        self.seite.text_rechts(RAND + BREITE, 32, self.person, 8, grau=0.55)
        self.seite.linie(RAND, 38, RAND + BREITE, 38, grau=0.88)
        self.seite.text_rechts(RAND + BREITE, 822, f"Seite {self.nummer}", 8, grau=0.6)
        self.y = 62.0

    def platz(self, hoehe: float) -> None:
        if self.y + hoehe > FUSS:
            self.neue_seite()

    def abstand(self, hoehe: float) -> None:
        self.y += hoehe

    # --- Bausteine ---
    #
    # Eine Regel für alle: Die Schreibmarke steht auf der Oberkante dessen,
    # was als Nächstes kommt, und jeder Baustein schiebt sie hinter das
    # Geschriebene. Vorher zeichnete Text über der Marke und ein Balken
    # darunter - dadurch landete jede Überschrift nach einem Balkenblock
    # mitten in der letzten Zeile.
    def titel(self, text: str, groesse: float = 16) -> None:
        self.platz(groesse + 14)
        self.y += groesse
        self.seite.text(RAND, self.y, text, groesse, fett=True)
        self.y += 6

    def abschnitt(self, text: str) -> None:
        self.platz(52)
        self.y += 16                      # Luft vor einer neuen Überschrift
        self.y += 11.5
        self.seite.text(RAND, self.y, text, 11.5, fett=True)
        self.y += 5
        self.seite.linie(RAND, self.y, RAND + BREITE, self.y, grau=GRAU_LINIE)
        self.y += 11

    def unterpunkt(self, text: str) -> None:
        """Kleine Überschrift innerhalb eines Abschnitts."""
        self.platz(28)
        self.y += 10
        self.y += 9.5
        self.seite.text(RAND, self.y, text, 9.5, grau=0.2)
        self.y += 6

    def zeile(self, text: str, groesse: float = 9.5, grau: float | None = None,
              einzug: float = 0.0) -> None:
        self.platz(groesse + 5)
        self.y += groesse
        self.seite.text(RAND + einzug, self.y, text, groesse, grau=grau)
        self.y += 4

    def absatz(self, text: str, groesse: float = 8.5, grau: float = GRAU_TEXT) -> None:
        """Umbricht an Wortgrenzen auf die Textbreite."""
        worte, zeile = str(text).split(), ""
        for wort in worte:
            versuch = f"{zeile} {wort}".strip()
            if textbreite(versuch, groesse) > BREITE:
                self.zeile(zeile, groesse, grau)
                zeile = wort
            else:
                zeile = versuch
        if zeile:
            self.zeile(zeile, groesse, grau)

    def kennzahlen(self, paare: list[tuple[str, str]], spalten: int = 4) -> None:
        """Ein Raster aus Beschriftung und Wert."""
        breite = BREITE / spalten
        reihen = (len(paare) + spalten - 1) // spalten
        self.platz(reihen * 34 + 10)
        self.y += 8
        for i, (name, wert) in enumerate(paare):
            x = RAND + (i % spalten) * breite
            y = self.y + (i // spalten) * 34
            self.seite.text(x, y + 7, name.upper(), 6.8, grau=0.55)
            self.seite.text(x, y + 22, wert, 13, fett=True)
        self.y += reihen * 34 + 8

    def balken(self, zeilen: list[dict], beschriftung_breite: float = 72.0,
               hoechst: float = 10.0) -> None:
        """Waagerechte Balken: Beschriftung, Balken, Wert, Anzahl.

        Waagerecht, weil die Beschriftungen Wörter sind („Donnerstag") -
        senkrecht müsste man sie kippen oder kürzen.
        """
        spur_x = RAND + beschriftung_breite
        spur_breite = BREITE - beschriftung_breite - 86
        for zeile in zeilen:
            self.platz(17)
            y = self.y
            self.seite.text(RAND, y + 8.5, str(zeile["label"]), 8.5, grau=0.25)
            self.seite.rechteck(spur_x, y + 1, spur_breite, 9, (0.94, 0.94, 0.93))
            if zeile.get("n"):
                anteil = min(1.0, float(zeile["mittel"]) / hoechst)
                self.seite.rechteck(spur_x, y + 1, max(1.5, spur_breite * anteil), 9,
                                    vas_farbe(zeile["mittel"]))
                self.seite.text(spur_x + spur_breite + 7, y + 8.5,
                                _zahl(zeile["mittel"]), 8.5, fett=True)
                self.seite.text(spur_x + spur_breite + 34, y + 8.5,
                                f"n={zeile['n']}", 7.5, grau=0.55)
            else:
                self.seite.text(spur_x + spur_breite + 7, y + 8.5, "keine Messung",
                                7.5, grau=0.6)
            self.y += 15
        self.y += 2

    def tabelle(self, kopf: list[str], zeilen: list[list[str]],
                breiten: list[float], rechts: set[int] | None = None) -> None:
        rechts = rechts or set()
        gesamt = sum(breiten)
        breiten = [b / gesamt * BREITE for b in breiten]

        def kopfzeile() -> None:
            self.y += 7.5
            x = RAND
            for i, name in enumerate(kopf):
                if i in rechts:
                    self.seite.text_rechts(x + breiten[i] - 6, self.y, name, 7.5, grau=0.5)
                else:
                    self.seite.text(x, self.y, name, 7.5, grau=0.5)
                x += breiten[i]
            self.y += 4
            self.seite.linie(RAND, self.y, RAND + BREITE, self.y, grau=GRAU_LINIE)
            self.y += 4

        self.platz(44)
        self.y += 8                       # Luft vor der Tabelle
        kopfzeile()
        for zeile in zeilen:
            if self.y + 17 > FUSS:
                self.neue_seite()
                kopfzeile()
            self.y += 8.5
            x = RAND
            for i, wert in enumerate(zeile):
                if i in rechts:
                    self.seite.text_rechts(x + breiten[i] - 6, self.y, str(wert), 8.5)
                else:
                    self.seite.text(x, self.y, str(wert), 8.5)
                x += breiten[i]
            self.y += 4
            self.seite.linie(RAND, self.y, RAND + BREITE, self.y, grau=0.93)
            self.y += 4
        self.y += 2


# --- Der Bericht --------------------------------------------------------

def pdf(messungen: list[dict], mittel: list[dict], cycle: list[dict],
        person: dict | None = None) -> bytes:
    name = (person or {}).get("name") or "ganze Familie"
    daten = ps.bericht(messungen, mittel, cycle, person)
    u = daten["uebersicht"]

    dok = Dokument(f"Schmerztagebuch {name}", "Familie ToDos")
    L = Layout(dok, "Schmerztagebuch", name)

    # --- Kopf ---
    L.titel("Schmerztagebuch")
    L.zeile(name, 12, grau=0.2)
    zeitraum = (f"{_datum(u['von'])} bis {_datum(u['bis'])} · {u['tage']} Tage"
                if u["von"] else "noch keine Einträge")
    L.zeile(zeitraum, 9, grau=GRAU_TEXT)
    L.zeile(f"Erstellt am {dt.datetime.now():%d.%m.%Y um %H:%M} Uhr", 8, grau=0.58)
    L.abstand(8)

    L.kennzahlen([
        ("Messungen", str(u["messungen"])),
        ("Mittelwert", f"{_zahl(u['mittelwert'])} / 10"),
        ("Median", _zahl(u["median"])),
        ("Spanne", f"{_zahl(u['min'], 0)}–{_zahl(u['max'], 0)}"),
        ("Einnahmen", str(u["einnahmen"])),
        ("Schmerzfrei (0)", f"{u['schmerzfrei']}x"),
        ("Nachgetragen", str(u["nachgetragen"])),
        ("Zeitraum", f"{u['tage']} Tage"),
    ])

    L.absatz(
        "Dieser Bericht beschreibt eigene Aufzeichnungen. Die Messzeitpunkte hat die "
        "Person selbst gewählt, es gibt keine Vergleichsgruppe, und nachgetragene "
        "Werte stammen aus der Erinnerung. Die Zahlen sind damit ein Gesprächsanlass, "
        "kein Befund.")

    # --- Über den Tag ---
    L.abschnitt("Schmerz über den Tag")
    L.absatz("Mittlerer Wert je Dreistundenblock. n ist die Zahl der Messungen in "
             "diesem Block - bei kleinem n sagt der Mittelwert wenig.")
    L.abstand(4)
    L.balken(daten["tag"])

    # --- Über die Woche ---
    L.abschnitt("Schmerz über die Woche")
    L.balken([{**z, "label": z["label"]} for z in daten["woche"]])

    # --- Körperstellen ---
    if daten["stellen"]:
        L.abschnitt("Nach Körperstelle")
        L.tabelle(
            ["Stelle", "Messungen", "Mittelwert", "Höchster Wert"],
            [[z["label"], str(z["n"]), _zahl(z["mittel"]), _zahl(z["max"], 0)]
             for z in daten["stellen"]],
            [3, 1, 1, 1], rechts={1, 2, 3})

    # --- Einnahmen ---
    L.abschnitt("Schmerzmittel")
    if daten["mittel"]:
        L.tabelle(
            ["Mittel", "Einnahmen", "Menge gesamt", "ø je Einnahme"],
            [[z["label"], str(z["n"]), f"{_zahl(z['summe'], 0)} {z['einheit']}",
              f"{_zahl(z['schnitt'], 0)} {z['einheit']}"] for z in daten["mittel"]],
            [3, 1, 1.3, 1.3], rechts={1, 2, 3})
    else:
        L.zeile("Keine Einnahmen im Zeitraum.", 9, grau=GRAU_TEXT)

    # --- Wirkung ---
    w = daten["wirkung"]
    L.abschnitt("Schmerz vor und nach einer Einnahme")
    L.absatz(
        f"Verglichen wird die letzte Messung bis {ps.VORHER_MINUTEN} Minuten vor einer "
        f"Einnahme mit dem Mittel aller Messungen zwischen {ps.NACHHER_VON_MINUTEN} "
        f"Minuten und {ps.NACHHER_BIS_MINUTEN // 60} Stunden danach. "
        f"Von {len(mittel)} Einnahmen ließen sich {w['paare']} so auswerten; bei "
        f"{w['ohne_paar']} fehlt eine Messung davor oder danach.")
    L.abstand(4)

    if w["paare"]:
        L.tabelle(
            ["Mittel", "Paare", "vorher", "nachher", "Differenz",
             "besser", "gleich", "schlechter"],
            [[z["label"], str(z["n"]), _zahl(z["vorher"]), _zahl(z["nachher"]),
              ("+" if z["differenz"] > 0 else "") + _zahl(z["differenz"]),
              str(z["besser"]), str(z["gleich"]), str(z["schlechter"])]
             for z in w["je_mittel"]]
            + [["Alle zusammen", str(w["paare"]), _zahl(w["vorher"]),
                _zahl(w["nachher"]),
                ("+" if (w["differenz"] or 0) > 0 else "") + _zahl(w["differenz"]),
                "", "", ""]],
            [2.4, 0.8, 0.9, 0.9, 1.0, 0.9, 0.9, 1.1], rechts={1, 2, 3, 4, 5, 6, 7})
        L.abstand(2)
        L.absatz(
            "Das ist eine Beobachtung, kein Wirksamkeitsnachweis. Niemand hat zum "
            "Vergleich nichts eingenommen, und Schmerz lässt häufig auch von allein "
            "nach. Bei wenigen Paaren ist ein Unterschied von einem Punkt nicht von "
            "Zufall zu unterscheiden. „besser“, „gleich“ und „schlechter“ "
            "zählen Veränderungen von mehr als einem halben Punkt.")
    else:
        L.zeile("Zu wenige Messungen rund um die Einnahmen für einen Vergleich.",
                9, grau=GRAU_TEXT)
        L.absatz("Damit hier etwas steht, hilft je eine Messung kurz vor der Einnahme "
                 "und eine ein bis zwei Stunden danach.")

    # --- Zyklus ---
    z = daten["zyklus"]
    if z and z["zyklen"]:
        L.abschnitt("Schmerz im Zyklus")
        L.absatz(
            f"{len(z['zyklen'])} Zyklen eingetragen, mittlere Länge "
            f"{_zahl(z['laenge_mittel'])} Tage. {z['zugeordnet']} von "
            f"{len(messungen)} Messungen ließen sich einem Zyklus zuordnen; "
            f"{z['ohne']} liegen vor dem ersten Eintrag.")
        L.abstand(4)
        if z["phasen"]:
            L.unterpunkt("Nach Phase")
            L.balken(z["phasen"], beschriftung_breite=104)
        if z["tage"]:
            L.unterpunkt("Nach Zyklustag")
            L.balken(z["tage"], beschriftung_breite=104)
        L.tabelle(
            ["Zyklus beginnt", "Periode bis", "Eisprung", "Länge"],
            [[_datum(zy["start"]), _datum(zy["periode_ende"]),
              _datum(zy["eisprung"]),
              f"{zy['laenge']} Tage" if zy["laenge"] else "läuft noch"]
             for zy in z["zyklen"]],
            [1, 1, 1, 1], rechts={3})
        L.absatz("Die Phase ergibt sich aus den eingetragenen Marken. Ohne "
                 "eingetragenen Eisprung wird der Zyklus nur in erste und zweite "
                 "Hälfte geteilt.")

    # --- Alle Einträge ---
    L.abschnitt("Alle Einträge")
    alles = []
    for e in messungen:
        zeit = ps.parse_zeit(e.get("recordedAt"))
        if zeit:
            alles.append((zeit, "Schmerz", f"{int(e['value'])} / 10",
                          e.get("place") or "", e.get("note") or "", e.get("retro")))
    for e in mittel:
        zeit = ps.parse_zeit(e.get("recordedAt"))
        if zeit:
            menge = f"{_zahl(e.get('dose'), 0)} {e.get('unit') or 'mg'}"
            alles.append((zeit, "Mittel", menge, e.get("drug") or "",
                          e.get("note") or "", e.get("retro")))
    for e in cycle or []:
        zeit = ps.parse_zeit(e.get("recordedAt"))
        if zeit:
            alles.append((zeit, "Zyklus", "",
                          ps_kind_label(e.get("kind")), e.get("note") or "", e.get("retro")))
    alles.sort(key=lambda p: p[0], reverse=True)

    L.tabelle(
        ["Datum", "Zeit", "Art", "Wert", "Stelle / Mittel", "Notiz", ""],
        [[f"{zeit:%d.%m.%y}", f"{zeit:%H:%M}", art, wert, wo,
          (notiz[:34] + "…") if len(notiz) > 35 else notiz,
          "nachgetragen" if retro else ""]
         for zeit, art, wert, wo, notiz, retro in alles],
        [1.0, 0.7, 0.9, 0.9, 1.7, 2.4, 1.2])

    return dok.bytes()


def ps_kind_label(kind: str) -> str:
    from . import db
    return db.CYCLE_KINDS.get(kind or "", kind or "")


# --- CSV ----------------------------------------------------------------

def csv_bytes(messungen: list[dict], mittel: list[dict],
              cycle: list[dict]) -> bytes:
    """Eine Zeile je Eintrag, chronologisch.

    Semikolon als Trenner und eine BOM davor: So öffnet Excel die Datei in
    deutscher Einstellung auf Anhieb richtig, statt alles in eine Spalte zu
    legen. Zahlen mit Komma, aus demselben Grund.
    """
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", quoting=csv.QUOTE_MINIMAL,
                           lineterminator="\r\n")
    schreiber.writerow([
        "Datum", "Uhrzeit", "Art", "Wert", "Einheit", "Stelle/Mittel",
        "Notiz", "Nachgetragen", "Eingetragen am",
    ])

    zeilen = []
    for e in messungen:
        zeit = ps.parse_zeit(e.get("recordedAt"))
        if zeit:
            zeilen.append((zeit, ["Schmerz", str(int(e.get("value") or 0)), "von 10",
                                  e.get("place") or "", e.get("note") or ""], e))
    for e in mittel:
        zeit = ps.parse_zeit(e.get("recordedAt"))
        if zeit:
            menge = _zahl(e.get("dose"), 0)
            zeilen.append((zeit, ["Mittel", menge, e.get("unit") or "mg",
                                  e.get("drug") or "", e.get("note") or ""], e))
    for e in cycle or []:
        zeit = ps.parse_zeit(e.get("recordedAt"))
        if zeit:
            zeilen.append((zeit, ["Zyklus", "", "", ps_kind_label(e.get("kind")),
                                  e.get("note") or ""], e))
    zeilen.sort(key=lambda p: p[0])

    for zeit, felder, eintrag in zeilen:
        notiert = ps.parse_zeit(eintrag.get("loggedAt"))
        schreiber.writerow([
            f"{zeit:%d.%m.%Y}", f"{zeit:%H:%M}", *felder,
            "ja" if eintrag.get("retro") else "nein",
            f"{notiert:%d.%m.%Y %H:%M}" if notiert else "",
        ])

    # Byte Order Mark: ohne sie zeigt Excel Umlaute als Buchstabensalat.
    return "﻿".encode("utf-8") + puffer.getvalue().encode("utf-8")
