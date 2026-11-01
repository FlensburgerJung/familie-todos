"""Auswertung des Schmerztagebuchs.

Reine Rechnerei, kein Ausgabeformat: Dieselben Zahlen gehen in den
PDF-Bericht und könnten morgen in eine Ansicht in der App.

Zum Anspruch: Was hier herauskommt, ist eine Beschreibung der eigenen
Aufzeichnungen - Mittelwerte, Verteilungen, Veränderungen. Es ist keine
Studie. Es gibt keine Kontrollgruppe, die Messzeitpunkte wählt der Mensch
selbst, und Schmerz lässt mit der Zeit oft von allein nach. Der Bericht
sagt das an jeder Stelle, an der es sonst nach Beweis aussehen könnte.
"""

from __future__ import annotations

import datetime as dt

# --- Zeit ---------------------------------------------------------------

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
              "Samstag", "Sonntag"]
WOCHENTAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Dreistundenblöcke statt einzelner Stunden: Bei ein paar Dutzend Einträgen
# sind 24 Fächer fast alle leer, und aus einem einzigen Wert je Stunde liest
# man ein Muster heraus, das keines ist.
TAGESBLOECKE = [(0, 3), (3, 6), (6, 9), (9, 12),
                (12, 15), (15, 18), (18, 21), (21, 24)]

# In diesem Fenster vor der Einnahme gilt eine Messung als "davor".
VORHER_MINUTEN = 150
# Und in diesem Fenster danach als "danach". Unter einer halben Stunde
# wirkt noch nichts, nach vier Stunden ist der Zusammenhang zu lose.
NACHHER_VON_MINUTEN = 30
NACHHER_BIS_MINUTEN = 240


def parse_zeit(wert: str) -> dt.datetime | None:
    if not wert:
        return None
    try:
        return dt.datetime.fromisoformat(str(wert)[:19])
    except ValueError:
        return None


def _mittel(werte: list[float]) -> float | None:
    return round(sum(werte) / len(werte), 1) if werte else None


def _median(werte: list[float]) -> float | None:
    if not werte:
        return None
    s = sorted(werte)
    mitte = len(s) // 2
    if len(s) % 2:
        return round(float(s[mitte]), 1)
    return round((s[mitte - 1] + s[mitte]) / 2, 1)


# --- Vorbereiten --------------------------------------------------------

def fuer_person(eintraege: list[dict], person_id: str) -> list[dict]:
    """Was dieser Person gehört. Ohne Person gilt alles.

    Einträge ohne Personenangabe stammen aus der Zeit, in der am Gerät
    niemand gewählt war - die gehören zu jedem Bericht, sonst verschwinden
    sie lautlos.
    """
    if not person_id:
        return list(eintraege)
    return [e for e in eintraege
            if not e.get("personId") or e.get("personId") == person_id]


def _mit_zeit(eintraege: list[dict]) -> list[tuple[dt.datetime, dict]]:
    paare = [(parse_zeit(e.get("recordedAt")), e) for e in eintraege]
    return sorted([(z, e) for z, e in paare if z], key=lambda p: p[0])


# --- Die einzelnen Auswertungen ----------------------------------------

def uebersicht(messungen: list[dict], mittel: list[dict]) -> dict:
    werte = [float(e["value"]) for e in messungen if e.get("value") is not None]
    zeiten = [z for z, _ in _mit_zeit(messungen + mittel)]
    return {
        "messungen": len(messungen),
        "einnahmen": len(mittel),
        "nachgetragen": sum(1 for e in messungen + mittel if e.get("retro")),
        "mittelwert": _mittel(werte),
        "median": _median(werte),
        "min": int(min(werte)) if werte else None,
        "max": int(max(werte)) if werte else None,
        "schmerzfrei": sum(1 for w in werte if w == 0),
        "von": zeiten[0] if zeiten else None,
        "bis": zeiten[-1] if zeiten else None,
        "tage": (zeiten[-1].date() - zeiten[0].date()).days + 1 if zeiten else 0,
    }


def ueber_den_tag(messungen: list[dict]) -> list[dict]:
    """Mittlerer Schmerz je Dreistundenblock."""
    faecher = {grenze: [] for grenze in TAGESBLOECKE}
    for zeit, eintrag in _mit_zeit(messungen):
        for von, bis in TAGESBLOECKE:
            if von <= zeit.hour < bis:
                faecher[(von, bis)].append(float(eintrag["value"]))
                break
    return [{"label": f"{von:02d}–{bis:02d}", "von": von, "bis": bis,
             "n": len(werte), "mittel": _mittel(werte), "max": max(werte) if werte else None}
            for (von, bis), werte in faecher.items()]


def ueber_die_woche(messungen: list[dict]) -> list[dict]:
    faecher = {tag: [] for tag in range(7)}
    for zeit, eintrag in _mit_zeit(messungen):
        faecher[zeit.weekday()].append(float(eintrag["value"]))
    return [{"label": WOCHENTAGE[tag], "kurz": WOCHENTAGE_KURZ[tag],
             "n": len(werte), "mittel": _mittel(werte), "max": max(werte) if werte else None}
            for tag, werte in faecher.items()]


def je_stelle(messungen: list[dict]) -> list[dict]:
    """Welche Körperstelle wie oft und wie stark."""
    faecher: dict[str, list[float]] = {}
    for eintrag in messungen:
        name = (eintrag.get("place") or "ohne Angabe").strip() or "ohne Angabe"
        faecher.setdefault(name, []).append(float(eintrag["value"]))
    zeilen = [{"label": name, "n": len(werte), "mittel": _mittel(werte),
               "max": max(werte)} for name, werte in faecher.items()]
    return sorted(zeilen, key=lambda z: (-z["n"], z["label"]))


def einnahmen_je_mittel(mittel: list[dict]) -> list[dict]:
    """Wie oft und wie viel - je Mittel und Einheit getrennt."""
    faecher: dict[tuple[str, str], dict] = {}
    for eintrag in mittel:
        schluessel = (eintrag.get("drug") or "?", eintrag.get("unit") or "mg")
        posten = faecher.setdefault(schluessel, {"n": 0, "summe": 0.0})
        posten["n"] += 1
        posten["summe"] += float(eintrag.get("dose") or 0)
    zeilen = [{"label": name, "einheit": einheit, "n": p["n"], "summe": p["summe"],
               "schnitt": round(p["summe"] / p["n"], 1) if p["n"] else 0}
              for (name, einheit), p in faecher.items()]
    return sorted(zeilen, key=lambda z: (-z["n"], z["label"]))


def wirkung(messungen: list[dict], mittel: list[dict]) -> dict:
    """Schmerz vor und nach einer Einnahme - je Mittel.

    Vorgehen: Zu jeder Einnahme die letzte Messung in den 150 Minuten davor
    und der Mittelwert aller Messungen zwischen 30 Minuten und 4 Stunden
    danach. Nur Einnahmen, für die beides vorliegt, gehen ein - darum steht
    überall dabei, auf wie vielen Paaren eine Zahl beruht.

    Was das nicht ist: ein Nachweis der Wirkung. Niemand hat zum Vergleich
    nichts genommen, und Schmerz lässt oft auch von allein nach. Bei einer
    Handvoll Paaren ist eine Differenz von einem Punkt nichts als Rauschen.
    """
    mess = _mit_zeit(messungen)
    paare: list[dict] = []

    for zeit, eintrag in _mit_zeit(mittel):
        davor = [w for z, w in mess
                 if dt.timedelta(0) <= zeit - z <= dt.timedelta(minutes=VORHER_MINUTEN)]
        danach = [w for z, w in mess
                  if dt.timedelta(minutes=NACHHER_VON_MINUTEN)
                  <= z - zeit <= dt.timedelta(minutes=NACHHER_BIS_MINUTEN)]
        if not davor or not danach:
            continue
        vor_wert = float(davor[-1]["value"])          # die letzte vor der Einnahme
        nach_werte = [float(w["value"]) for w in danach]
        paare.append({
            "drug": eintrag.get("drug") or "?",
            "dose": float(eintrag.get("dose") or 0),
            "unit": eintrag.get("unit") or "mg",
            "zeit": zeit,
            "vorher": vor_wert,
            "nachher": sum(nach_werte) / len(nach_werte),
            "n_danach": len(nach_werte),
        })

    je_mittel: dict[str, list[dict]] = {}
    for paar in paare:
        je_mittel.setdefault(paar["drug"], []).append(paar)

    zeilen = []
    for name, liste in je_mittel.items():
        vorher = [p["vorher"] for p in liste]
        nachher = [p["nachher"] for p in liste]
        zeilen.append({
            "label": name,
            "n": len(liste),
            "vorher": _mittel(vorher),
            "nachher": _mittel(nachher),
            "differenz": round(sum(n - v for v, n in zip(vorher, nachher)) / len(liste), 1),
            "besser": sum(1 for v, n in zip(vorher, nachher) if n < v - 0.5),
            "gleich": sum(1 for v, n in zip(vorher, nachher) if abs(n - v) <= 0.5),
            "schlechter": sum(1 for v, n in zip(vorher, nachher) if n > v + 0.5),
        })
    zeilen.sort(key=lambda z: (-z["n"], z["label"]))

    alle_vorher = [p["vorher"] for p in paare]
    alle_nachher = [p["nachher"] for p in paare]
    return {
        "paare": len(paare),
        "ohne_paar": len(mittel) - len(paare),
        "je_mittel": zeilen,
        "vorher": _mittel(alle_vorher),
        "nachher": _mittel(alle_nachher),
        "differenz": (round(sum(n - v for v, n in zip(alle_vorher, alle_nachher))
                            / len(paare), 1) if paare else None),
    }


# --- Zyklus -------------------------------------------------------------

# Wie lange eine Periode gilt, wenn kein Ende eingetragen ist. Nur fuer die
# Phasenzuordnung; am Zyklustag aendert es nichts.
PERIODE_TAGE_STANDARD = 5


def zyklen(cycle: list[dict]) -> list[dict]:
    """Die Zyklen aus den Marken rekonstruieren.

    Ein Zyklus beginnt mit "Periode beginnt" und endet am Tag vor dem
    nächsten Beginn. Der letzte bleibt offen.
    """
    marken = _mit_zeit(cycle)
    starts = [z for z, e in marken if e["kind"] == "periode"]
    enden = [z for z, e in marken if e["kind"] == "periode_ende"]
    eispruenge = [z for z, e in marken if e["kind"] == "eisprung"]

    ergebnis = []
    for nummer, start in enumerate(starts):
        naechster = starts[nummer + 1] if nummer + 1 < len(starts) else None
        ende = next((z for z in enden if z >= start
                     and (naechster is None or z < naechster)), None)
        eisprung = next((z for z in eispruenge if z >= start
                         and (naechster is None or z < naechster)), None)
        ergebnis.append({
            "start": start,
            "periode_ende": ende,
            "eisprung": eisprung,
            "naechster_start": naechster,
            "laenge": (naechster.date() - start.date()).days if naechster else None,
            "periode_laenge": ((ende.date() - start.date()).days + 1) if ende else None,
        })
    return ergebnis


def _phase(zeit: dt.datetime, zyklus: dict) -> tuple[int, str]:
    """Zyklustag (1 = erster Tag der Periode) und Phase."""
    tag = (zeit.date() - zyklus["start"].date()).days + 1

    periode_bis = (zyklus["periode_ende"].date() if zyklus["periode_ende"]
                   else zyklus["start"].date() + dt.timedelta(days=PERIODE_TAGE_STANDARD - 1))
    if zeit.date() <= periode_bis:
        return tag, "Periode"

    if zyklus["eisprung"]:
        abstand = (zeit.date() - zyklus["eisprung"].date()).days
        if abs(abstand) <= 1:
            return tag, "Eisprung"
        return tag, "vor dem Eisprung" if abstand < 0 else "nach dem Eisprung"

    # Ohne eingetragenen Eisprung nur grob nach Zyklustag teilen.
    return tag, "erste Hälfte" if tag <= 14 else "zweite Hälfte"


PHASEN_ORDNUNG = ["Periode", "vor dem Eisprung", "Eisprung", "nach dem Eisprung",
                  "erste Hälfte", "zweite Hälfte"]


def nach_zyklus(messungen: list[dict], cycle: list[dict]) -> dict:
    """Schmerz je Zyklusphase und je Zyklustag-Block."""
    liste = zyklen(cycle)
    if not liste:
        return {"zyklen": [], "phasen": [], "tage": [], "zugeordnet": 0,
                "ohne": len(messungen)}

    phasen: dict[str, list[float]] = {}
    bloecke: dict[str, list[float]] = {}
    zugeordnet = 0

    for zeit, eintrag in _mit_zeit(messungen):
        passend = None
        for zyklus in liste:
            if zeit < zyklus["start"]:
                continue
            if zyklus["naechster_start"] and zeit >= zyklus["naechster_start"]:
                continue
            passend = zyklus
            break
        if not passend:
            continue
        tag, phase = _phase(zeit, passend)
        if tag < 1 or tag > 60:          # unplausibel, lieber weglassen
            continue
        zugeordnet += 1
        phasen.setdefault(phase, []).append(float(eintrag["value"]))
        grenze = min((tag - 1) // 5 * 5 + 1, 26)
        label = f"Tag {grenze}–{grenze + 4}" if grenze < 26 else "Tag 26+"
        bloecke.setdefault(label, []).append(float(eintrag["value"]))

    phasen_zeilen = [{"label": name, "n": len(werte), "mittel": _mittel(werte),
                      "max": max(werte)}
                     for name, werte in phasen.items()]
    phasen_zeilen.sort(key=lambda z: PHASEN_ORDNUNG.index(z["label"])
                       if z["label"] in PHASEN_ORDNUNG else 99)

    def block_rang(label: str) -> int:
        return 99 if label.endswith("+") else int(label.split()[1].split("–")[0])

    tage_zeilen = [{"label": name, "n": len(werte), "mittel": _mittel(werte),
                    "max": max(werte)} for name, werte in bloecke.items()]
    tage_zeilen.sort(key=lambda z: block_rang(z["label"]))

    laengen = [z["laenge"] for z in liste if z["laenge"]]
    return {
        "zyklen": liste,
        "phasen": phasen_zeilen,
        "tage": tage_zeilen,
        "zugeordnet": zugeordnet,
        "ohne": len(messungen) - zugeordnet,
        "laenge_mittel": _mittel([float(x) for x in laengen]),
    }


# --- Alles zusammen ----------------------------------------------------

def bericht(messungen: list[dict], mittel: list[dict], cycle: list[dict],
            person: dict | None = None) -> dict:
    return {
        "person": person or {},
        "uebersicht": uebersicht(messungen, mittel),
        "tag": ueber_den_tag(messungen),
        "woche": ueber_die_woche(messungen),
        "stellen": je_stelle(messungen),
        "mittel": einnahmen_je_mittel(mittel),
        "wirkung": wirkung(messungen, mittel),
        "zyklus": nach_zyklus(messungen, cycle) if cycle else None,
    }
