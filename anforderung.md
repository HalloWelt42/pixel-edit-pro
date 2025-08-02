# AI Prompt: Professional Pixel Editor für macOS/Windows/Linux

## Aufgabe
Erstelle einen vollständigen Pixel-Art-Editor in Python mit PyQt6. Der Editor soll professionelle Features bieten und speziell für Pixel-Art optimiert sein.

## Technische Anforderungen

### Basis-Setup
- Python 3.8+
- PyQt6 Framework
- Virtuelle Umgebung (.venv)
- Kompatibel mit macOS M1, Windows, Linux
- Dateiname: `pixel_editor.py`

### Dependencies
```python
PyQt6
numpy
```

## Core-Funktionalitäten

### 1. Canvas-System
- **Grid-Größen**: 16x16 bis 64x64 Pixel
- **Virtueller Canvas**: 3x tatsächliche Grid-Größe für Move-Operationen
- **Zellengrö��e**: 20px pro Pixel
- **Optionales Grid-Overlay**: Ein/ausblendbar, wird über allen Ebenen gezeichnet
- **Echtzeit-Koordinatenanzeige**: Position: X, Y

### 2. Zeichenwerkzeuge (DrawMode Enum)
Implementiere folgende Werkzeuge mit Tastenkürzel:

1. **PENCIL (P)**: Freihandzeichnen
   - Bresenham-Algorithmus für 1px Linien
   - Variable Stiftbreite (1-10px)

2. **LINE (L)**: Gerade Linien
   - Pixel-perfect bei 1px Breite

3. **RECTANGLE (R)**: Rechtecke
   - Umrandet und gefüllt als separate Modi

4. **CIRCLE (C)**: Kreise/Ellipsen
   - Standard: Ellipse
   - Shift: Perfekter Kreis
   - Midpoint-Algorithmus für Pixel-perfect

5. **TRIANGLE**: Dreiecke
   - Standard: Rechtwinklig
   - Shift: Gleichseitig

6. **POLYGON**: Mehrecke
   - Punkte durch Klicks setzen
   - Shift: Abschließen
   - Alt: Regelmäßiges Polygon

7. **FILL (F)**: Flood-Fill-Algorithmus

8. **ERASER (E)**: Transparenz setzen

9. **PICKER (I)**: Farbe aufnehmen

10. **MOVE (M)**: Ebeneninhalt verschieben
    - Max. Verschiebung = Grid-Größe
    - Halbtransparente Vorschau

### 3. Ebenen-System
```python
@dataclass
class Layer:
    name: str
    pixmap: QPixmap
    visible: bool = True
    opacity: float = 1.0
    selected: bool = False  # Für Merge
```

**Features**:
- Unbegrenzte Ebenen
- Transparenz-Support
- Opacity pro Ebene (0-100%)
- Sichtbarkeit toggle (Doppelklick)
- Mehrfachauswahl (Ctrl+Klick)
- Ebenen zusammenführen (Ctrl+E)
- Nur sichtbare Ebenen editierbar

### 4. Farbmanagement
- **Primär/Sekundärfarbe**
- **Material Design Palette** (32 Farben)
- **20 Custom-Farb-Slots**:
  - Rechtsklick oder Ctrl+Klick zum Editieren
  - Persistente Speicherung
- **Transparenz-Support**:
  - T-Button für vollständige Transparenz
  - Alpha-Anzeige unter Primärfarbe
  - Schachbrettmuster für transparente Farben
  - Statusleiste zeigt Alpha-Wert

### 5. Transformationen
**Transform-Toolbar** (unten):
- **Rotation-Slider** (0-360°):
  - Live-Preview
  - Shift für 45°-Snap
  - Tickmarks alle 45°
- **Quick-Rotate**: 90°, -90°, 180°
- **Flip**: Horizontal (Ctrl+H), Vertikal (Ctrl+Shift+H)
- Alle Transformationen nur auf aktuelle Ebene

### 6. Undo/Redo
- Stack mit max. 100 Schritten
- Intelligente State-Speicherung
- Keine doppelten States
- Picker löst kein Undo aus

### 7. Blur-Modus
- Optional für alle Werkzeuge
- Semi-transparente Striche
- Antialiasing aktiviert
- 1.5x Stiftbreite

### 8. Datei-Operationen

#### Projekt-Format (.pep/JSON)
```json
{
  "grid_size": 32,
  "layers": [{
    "name": "Layer Name",
    "image_data": "base64...",
    "visible": true,
    "opacity": 1.0
  }],
  "current_layer": 0
}
```

#### Export-Formate
- **PNG**: Mit/ohne Transparenz Dialog
- **ICO**: Multi-Size (16-256px)

#### Paletten-Format (JSON)
```json
{
  "material": ["#color1", "..."],
  "user": ["#color1", "..."]
}
```

### 9. Filter
- Blur (Box-Filter)
- Sharpen
- Grayscale
- Invert
- Nur auf sichtbaren Bereich angewendet

### 10. Persistente Einstellungen
Speichere in `pixel_editor_settings.json`:
- Grid-Größe
- Show Grid
- Blur Mode
- Pen Width
- Farben
- Paletten
- Fensterposition

### 11. Macro-System
- Aufzeichnung von Aktionen
- Wiedergabe
- Macro-Manager Dialog

## UI-Layout

### Hauptfenster
```
[Menu Bar]
[Main Toolbar]
[Left Panel][Canvas Area][Right Panel]
[Transform Toolbar]
[Status Bar]
```

### Main Toolbar
- New, Open, Save
- Save/Load Project
- Undo/Redo
- Grid Size Spinner
- Show Grid Checkbox
- Blur Mode Checkbox

### Left Panel (Tools)
- 2x7 Grid von Tool-Buttons (32x32px)
- Icon-Fonts für Symbole
- Pen Width Slider

### Right Panel
- Farbauswahl (Primary/Secondary/Transparent)
- Farbpalette (10 Spalten)
- Ebenen-Liste mit Checkboxes
- Layer-Buttons (+, -, ⬇)
- Opacity Slider

### Transform Toolbar
- Rotation Slider mit Label
- Quick Rotate Buttons
- Flip H/V Buttons
- Reset Button

## Wichtige Implementation Details

### Virtual Canvas
```python
self.virtual_size = grid_size * 3
offset = self.get_virtual_offset()  # returns grid_size
```

### Pixel-Perfect Drawing
```python
painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
```

### Layer Selection UI
```
☑ 👁 Layer Name (75%)  # Selected, Visible, Opacity
☐ 🚫 Hidden Layer      # Not selected, Hidden
```

### Transparenz-Visualisierung
- QPushButton mit Icon für transparente Farben
- Schachbrettmuster-Hintergrund
- Alpha-Prozent-Label

### Rotation mit beliebigem Winkel
```python
transform = QTransform()
transform.translate(center.x(), center.y())
transform.rotate(angle)
transform.translate(-center.x(), -center.y())
```

## Spezielle macOS-Anpassungen
```python
if sys.platform == "darwin":
    app.setStyle("Fusion")
    self.setUnifiedTitleAndToolBarOnMac(True)
```

## Fehlerbehandlung
- Warnung bei Zeichnen auf versteckter Ebene
- Mindestens 2 Ebenen für Merge
- Bestätigung bei Reset All
- Graceful Handling von fehlenden Settings

## Performance-Optimierungen
- Nur sichtbarer Bereich wird gerendert
- Fast Transformation für Pixel-Art
- Delayed Preview Updates (50ms Timer)
- Effiziente State-Vergleiche

## Benutzerführung
- Tooltips mit Tastenkürzel-Hinweisen
- Statusleiste zeigt aktuellen Modus
- Visuelle Indikatoren für Auswahl/Transparenz
- Deutsche und englische UI-Elemente gemischt

Erstelle den kompletten, funktionsfähigen Code als einzelne Python-Datei mit allen beschriebenen Features.