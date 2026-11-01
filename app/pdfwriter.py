"""Ein kleiner PDF-Erzeuger - genug für einen Bericht mit Tabellen und Balken.

Warum selbst geschrieben: Diese App läuft zuhause ohne jede Installation und
online mit vier Paketen. `reportlab` wäre das fünfte, nur für diese eine
Seite. Ein PDF ist aber ein Textformat mit einer Tabelle am Ende - Text,
Linien und gefüllte Rechtecke sind in rund zweihundert Zeilen machbar, und
mehr braucht ein Bericht nicht.

Benutzt werden die beiden Standardschriften, die jeder PDF-Betrachter
mitbringt (Helvetica, Helvetica-Bold). Damit sind keine Schriftdateien
einzubetten. Als Kodierung dient WinAnsi - darin stehen die deutschen
Umlaute und das ß.
"""

from __future__ import annotations

# A4 in Punkt (1/72 Zoll).
SEITE_BREITE, SEITE_HOEHE = 595.28, 841.89

NORMAL, FETT = "F1", "F2"


def _text_kodieren(text: str) -> bytes:
    """In WinAnsi, und die drei Zeichen schützen, die im PDF etwas bedeuten."""
    roh = str(text)
    for alt, neu in (("\\", r"\\"), ("(", r"\("), (")", r"\)")):
        roh = roh.replace(alt, neu)
    # Was WinAnsi nicht kennt (etwa Emoji), wird zu einem Fragezeichen -
    # besser als ein Abbruch mitten im Bericht.
    return roh.encode("cp1252", "replace")


# Zeichenbreiten der Helvetica, in 1/1000 em. Nur die Zeichen, die in
# deutschem Text vorkommen - alles andere wird mit 556 geschätzt. Damit
# lässt sich Text zentrieren und rechts ausrichten, ohne eine Schriftdatei
# auszulesen.
_BREITEN = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556, "6": 556,
    "7": 556, "8": 556, "9": 556,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "ä": 556, "ö": 556, "ü": 556, "Ä": 667, "Ö": 778, "Ü": 722, "ß": 556,
    "–": 556, "—": 1000, "·": 278, "⌀": 556, "±": 584, "→": 1000,
}


def textbreite(text: str, groesse: float, fett: bool = False) -> float:
    summe = sum(_BREITEN.get(z, 556) for z in str(text))
    # Die fette Schnitt ist etwas breiter; 1,06 trifft es für Fließtext gut
    # genug, um Spalten nicht überlaufen zu lassen.
    return summe / 1000.0 * groesse * (1.06 if fett else 1.0)


class Seite:
    """Sammelt die Zeichenbefehle einer Seite."""

    def __init__(self) -> None:
        self.teile: list[bytes] = []

    # --- Text ---
    def text(self, x: float, y: float, inhalt: str, groesse: float = 10,
             fett: bool = False, grau: float | None = None,
             farbe: tuple[float, float, float] | None = None) -> None:
        """y zählt von oben. Links ausgerichtet."""
        schrift = FETT if fett else NORMAL
        self.teile.append(b"BT")
        if farbe:
            self.teile.append(f"{farbe[0]:.3f} {farbe[1]:.3f} {farbe[2]:.3f} rg".encode())
        elif grau is not None:
            self.teile.append(f"{grau:.3f} g".encode())
        else:
            self.teile.append(b"0 g")
        self.teile.append(f"/{schrift} {groesse:.2f} Tf".encode())
        self.teile.append(f"1 0 0 1 {x:.2f} {SEITE_HOEHE - y:.2f} Tm".encode())
        self.teile.append(b"(" + _text_kodieren(inhalt) + b") Tj")
        self.teile.append(b"ET")

    def text_rechts(self, x: float, y: float, inhalt: str, groesse: float = 10,
                    fett: bool = False, grau: float | None = None) -> None:
        self.text(x - textbreite(inhalt, groesse, fett), y, inhalt, groesse, fett, grau)

    def text_mitte(self, x: float, y: float, inhalt: str, groesse: float = 10,
                   fett: bool = False, grau: float | None = None) -> None:
        self.text(x - textbreite(inhalt, groesse, fett) / 2, y, inhalt,
                  groesse, fett, grau)

    # --- Flächen und Linien ---
    def rechteck(self, x: float, y: float, breite: float, hoehe: float,
                 farbe: tuple[float, float, float]) -> None:
        self.teile.append(
            f"{farbe[0]:.3f} {farbe[1]:.3f} {farbe[2]:.3f} rg "
            f"{x:.2f} {SEITE_HOEHE - y - hoehe:.2f} {breite:.2f} {hoehe:.2f} re f".encode())

    def linie(self, x1: float, y1: float, x2: float, y2: float,
              grau: float = 0.8, dicke: float = 0.5) -> None:
        self.teile.append(
            f"{grau:.3f} G {dicke:.2f} w {x1:.2f} {SEITE_HOEHE - y1:.2f} m "
            f"{x2:.2f} {SEITE_HOEHE - y2:.2f} l S".encode())

    def inhalt(self) -> bytes:
        return b"\n".join(self.teile)


class Dokument:
    def __init__(self, titel: str = "", autor: str = "") -> None:
        self.seiten: list[Seite] = []
        self.titel = titel
        self.autor = autor

    def neue_seite(self) -> Seite:
        seite = Seite()
        self.seiten.append(seite)
        return seite

    def bytes(self) -> bytes:
        """Das fertige PDF.

        Aufbau: Katalog, Seitenbaum, je Seite ein Seitenobjekt und ein
        Inhaltsstrom, dazu die beiden Schriften und die Angaben zum
        Dokument. Am Ende die Querverweistabelle mit den Byte-Positionen
        aller Objekte - deshalb wird mitgezählt, während geschrieben wird.
        """
        objekte: list[bytes] = []

        def hinzu(inhalt: bytes) -> int:
            objekte.append(inhalt)
            return len(objekte)          # Objektnummern beginnen bei 1

        katalog_nr = hinzu(b"")          # Platzhalter, wird unten gefüllt
        seiten_nr = hinzu(b"")
        schrift_normal = hinzu(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>")
        schrift_fett = hinzu(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>")

        seiten_nummern = []
        for seite in self.seiten:
            strom = seite.inhalt()
            strom_nr = hinzu(b"<< /Length " + str(len(strom)).encode() + b" >>\nstream\n"
                             + strom + b"\nendstream")
            seite_nr = hinzu(
                b"<< /Type /Page /Parent " + str(seiten_nr).encode() + b" 0 R "
                b"/MediaBox [0 0 " + f"{SEITE_BREITE:.2f} {SEITE_HOEHE:.2f}".encode() + b"] "
                b"/Resources << /Font << /F1 " + str(schrift_normal).encode() + b" 0 R "
                b"/F2 " + str(schrift_fett).encode() + b" 0 R >> >> "
                b"/Contents " + str(strom_nr).encode() + b" 0 R >>")
            seiten_nummern.append(seite_nr)

        kinder = b" ".join(str(n).encode() + b" 0 R" for n in seiten_nummern)
        objekte[seiten_nr - 1] = (b"<< /Type /Pages /Kids [" + kinder + b"] /Count "
                                  + str(len(seiten_nummern)).encode() + b" >>")
        objekte[katalog_nr - 1] = (b"<< /Type /Catalog /Pages "
                                   + str(seiten_nr).encode() + b" 0 R >>")

        info_nr = hinzu(b"<< /Title (" + _text_kodieren(self.titel) + b") "
                        b"/Author (" + _text_kodieren(self.autor) + b") "
                        b"/Producer (Familie ToDos) >>")

        ausgabe = bytearray(b"%PDF-1.4\n")
        # Ein Kommentar mit hohen Bytes sagt Werkzeugen, dass die Datei
        # Binärdaten enthalten darf.
        ausgabe += b"%\xe2\xe3\xcf\xd3\n"
        stellen = []
        for nummer, inhalt in enumerate(objekte, start=1):
            stellen.append(len(ausgabe))
            ausgabe += str(nummer).encode() + b" 0 obj\n" + inhalt + b"\nendobj\n"

        xref_stelle = len(ausgabe)
        ausgabe += b"xref\n0 " + str(len(objekte) + 1).encode() + b"\n"
        ausgabe += b"0000000000 65535 f \n"
        for stelle in stellen:
            ausgabe += f"{stelle:010d} 00000 n \n".encode()
        ausgabe += (b"trailer\n<< /Size " + str(len(objekte) + 1).encode()
                    + b" /Root " + str(katalog_nr).encode() + b" 0 R"
                    + b" /Info " + str(info_nr).encode() + b" 0 R >>\n"
                    + b"startxref\n" + str(xref_stelle).encode() + b"\n%%EOF\n")
        return bytes(ausgabe)
