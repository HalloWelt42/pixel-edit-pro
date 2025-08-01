# Pixel Editor

Ein professioneller Pixel-Art-Editor entwickelt mit PyQt6 für macOS, Windows und Linux.


![Bildschirmfoto 2025-08-02 um 01.46.50.png](media/Bildschirmfoto%202025-08-02%20um%2001.46.50.png)


## Funktionen

### Zeichenwerkzeuge
- **Stift** - Freihandzeichnen mit variabler Stiftbreite
- **Linie** - Gerade Linien mit Bresenham-Algorithmus für pixelgenaue Ergebnisse
- **Rechteck** - Umrandete und gefüllte Rechtecke
- **Kreis/Ellipse** - Ellipsen oder perfekte Kreise (Shift gedrückt halten)
- **Dreieck** - Rechtwinklige oder gleichseitige Dreiecke (Shift gedrückt halten)
- **Polygon** - Eigene Polygone erstellen, regelmäßige Polygone mit Alt-Taste
- **Füllen** - Flächen mit Farbe füllen
- **Radierer** - Pixel mit Transparenz entfernen
- **Pipette** - Farben vom Canvas aufnehmen
- **Verschieben** - Ebeneninhalt neu positionieren

### Ebenensystem
- Mehrere Ebenen mit Transparenzunterstützung
- Einstellbare Ebenendeckkraft (0-100%)
- Ebenen ein-/ausblenden
- Ebenenreihenfolge ändern
- Nur sichtbare Ebenen können bearbeitet werden

### Farbverwaltung
- Material Design Farbpalette
- 20 benutzerdefinierte Farbfelder (Rechtsklick oder Strg+Klick zum Bearbeiten)
- Primär- und Sekundärfarbe
- Volle Transparenzunterstützung
- Paletten als JSON importieren/exportieren

### Canvas
- Rastergrößen von 4x4 bis 256x256 Pixel
- Optionales Gitteroverlay
- Echtzeit-Koordinatenanzeige
- Virtueller Canvas für Verschiebungen über Grenzen hinaus
- Intelligenter Bildimport mit Seitenverhältniserhaltung

### Projektverwaltung
- Komplette Projekte als JSON speichern/laden (.pep-Dateien)
- Export nach PNG mit benutzerdefinierten Größen
- Export ins ICO-Format
- Persistente App-Einstellungen

### Erweiterte Funktionen
- Rückgängig/Wiederholen (bis zu 100 Schritte)
- Blur-Modus für weiche Kanten
- Basis-Filter (Weichzeichner, Schärfen, Graustufen, Invertieren)
- Makro-Aufzeichnung und -Wiedergabe
- Tastenkürzel für alle Werkzeuge

## Installation

### Voraussetzungen
- Python 3.8+
- PyQt6

### Einrichtung
```bash
# Virtuelle Umgebung erstellen
python3 -m venv .venv

# Virtuelle Umgebung aktivieren
# Auf macOS/Linux:
source .venv/bin/activate
# Auf Windows:
.venv\Scripts\activate

# Abhängigkeiten installieren
pip install PyQt6 numpy

# Editor starten
python pixel_editor.py
```

## Bedienung

### Grundlegende Steuerung
- **Linksklick** - Mit ausgewähltem Werkzeug zeichnen
- **Rechtsklick** - Kontextaktionen (z.B. benutzerdefinierte Farben bearbeiten)
- **Mausrad** - Zoom (wenn implementiert)

### Tastenkürzel
- **P** - Stift-Werkzeug
- **L** - Linien-Werkzeug
- **R** - Rechteck-Werkzeug
- **C** - Kreis-Werkzeug
- **F** - Füllwerkzeug
- **E** - Radierer
- **I** - Pipette
- **M** - Verschieben
- **Cmd/Strg+Z** - Rückgängig
- **Cmd/Strg+Shift+Z** - Wiederholen
- **Cmd/Strg+N** - Neue Datei
- **Cmd/Strg+O** - Datei öffnen
- **Cmd/Strg+S** - Datei speichern

### Werkzeug-Modifikatoren
- **Shift** - Proportionen einschränken (perfekte Kreise, gleichseitige Dreiecke)
- **Alt** - Spezialmodi (regelmäßige Polygone)
- **Strg/Cmd** - Alternative Aktionen

### Ebenenverwaltung
- Einfachklick auf Ebene zum Auswählen
- Doppelklick auf Ebene zum Ein-/Ausblenden
- Mit + und - Buttons Ebenen hinzufügen/entfernen
- Deckkraft mit Schieberegler anpassen (betrifft nur aktuelle Ebene)

### Farbpalette
- Klick auf beliebige Farbe zum Auswählen
- Rechtsklick auf benutzerdefinierte Farben zum Bearbeiten
- Paletten zur Wiederverwendung speichern/laden
- Transparenz wird als Schachbrettmuster angezeigt

## Dateiformate

### Projektdateien (.pep)
Kompletter Projektzustand inklusive:
- Alle Ebenen mit Transparenz
- Ebeneneinstellungen (Sichtbarkeit, Deckkraft)
- Canvas-Größe
- Aktuelle Werkzeugauswahl

### Exporte
- **PNG** - Mit Transparenz, auf beliebige Größe skalierbar
- **ICO** - Windows-Icon-Format
- **Palette (.json)** - Farbpalettendaten

## Tipps

- Nutzen Sie Ebenen für komplexe Kompositionen
- Halten Sie Shift für geometrische Einschränkungen
- Aktivieren Sie den Blur-Modus für geglättetes Zeichnen
- Das Gitter hilft bei präziser Pixelplatzierung
- Speichern Sie Projekte regelmäßig, um Ebeneninformationen zu erhalten

## Lizenz

Dieses Projekt ist Open Source unter MIT