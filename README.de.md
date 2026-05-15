# SunEnergyXT 500 Series

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

## Sprache / Language

- [Deutsch](README.md) (Standard)
- [English](README.en.md)

## Einfuehrung

SunEnergyXT 500 Series ist eine benutzerdefinierte Integration fuer Home Assistant. Sie ermoeglicht das Auffinden, Ueberwachen und Steuern von AIO-Geraeten der SunEnergyXT 500-Serie im lokalen Netzwerk.

Die vollstaendige Referenz der lokalen API, Beispiele fuer `MD`-Zaehlerverbindungsstrings und Beispiele fuer `TZ`-Zeitzonenwerte finden Sie in [API.md](API.md).

## Funktionen

- Automatische Geraeteerkennung ueber Zeroconf oder manuelles Hinzufuegen per IP-Adresse
- Ueberwachung von PV-Eingang, Netzanschlussleistung, Lastanschlussleistung, Batteriestand, Firmware-Versionen und weiteren Echtzeitdaten
- Anpassung haeufig genutzter Einstellungen wie `GS`, `IS`, `SI`, `SA`, `SO` und `PT`
- Konfiguration von lokalem Modus, `MM` Lokaler Eigenverbrauch, `MD` lokale Smart-Meter-Verbindung und dem Zeitzonenfeld `TZ`
- **Automatische Eigenverbrauchsregelung ueber beliebigen Home Assistant Sensor** – kein dedizierter Smart Meter am Geraet erforderlich
- Neustart des Geraets direkt aus Home Assistant

## Installation

### Installation ueber HACS (empfohlen)

1. Oeffnen Sie HACS in Home Assistant
2. Klicken Sie oben rechts auf die drei Punkte und waehlen Sie "Custom repositories"
3. Geben Sie die Repository-Adresse ein: https://github.com/SunEnergyXT/SunEnergyXT-500-Series
4. Waehlen Sie als Kategorie "Integration"
5. Klicken Sie auf "Add"
6. Suchen Sie nach "SunEnergyXT 500 Series"
7. Klicken Sie auf "Download"
8. Starten Sie Home Assistant neu

### Manuelle Installation

1. Laden Sie das aktuelle [Release-Paket](https://github.com/SunEnergyXT/SunEnergyXT-500-Series/releases) herunter
2. Entpacken Sie es in `config/custom_components/`
3. Stellen Sie sicher, dass das Zielverzeichnis `config/custom_components/sunenergyxt/` ist
4. Starten Sie Home Assistant neu

#### Beispiel fuer die endgueltige Verzeichnisstruktur

```text
custom_components
    ├── sunenergyxt
        ├── __init__.py
        ├── button.py
        ├── config_flow.py
        ├── const.py
        ├── coordinator.py
        ├── manifest.json
        ├── number.py
        ├── sensor.py
        ├── switch.py
        ├── text.py
        └── translations
            ├── de.json
            ├── en.json
```

## Konfiguration

1. Gehen Sie in Home Assistant zu "Einstellungen" > "Geraete und Dienste"
2. Klicken Sie auf "Integration hinzufuegen"
3. Suchen Sie nach `SunEnergyXT 500 Series`
4. Folgen Sie dem Einrichtungsdialog
   - Wenn das Geraet automatisch gefunden wird, bestaetigen Sie einfach den Fund
   - Wenn das Geraet nicht automatisch gefunden wird, geben Sie die IP-Adresse manuell ein
5. Die Integration liest SN und Modell automatisch aus. Eine manuelle Eingabe der SN ist nicht noetig
6. **Optional:** Waehlen Sie einen Home Assistant Sensor als Netzfluss-Quelle (siehe naechsten Abschnitt)

Hinweise zur Nutzung:

- Home Assistant und das Geraet muessen sich im selben lokalen Netzwerk befinden
- Wenn Sie die automatische Erkennung nutzen moechten, muss das Netzwerk mDNS / Zeroconf zulassen
- Nach dem Aendern eines Steuerwerts sollte der finale Zustand durch die naechste Aktualisierung oder ein erneutes Auslesen bestaetigt werden

## Automatische Eigenverbrauchsregelung ueber HA-Sensor

Die Integration unterstuetzt eine optionale, herstellerunabhaengige Eigenverbrauchsregelung ueber einen beliebigen Home Assistant Leistungssensor.

### Wie funktioniert das?

Standardmaessig unterstuetzt der lokale Eigenverbrauchsmodus (`MM`) des Geraets nur bestimmte Smart Meter direkt (Shelly Pro 3EM, EcoTracker, Tasmota/BitShake). Wer einen anderen Energiezaehler verwendet – etwa ueber **SolarEdge Modbus**, **Tibber Pulse**, **Volkszaehler** oder eine andere Integration – kann den Netzfluss-Sensor aus Home Assistant direkt verwenden.

Die Integration registriert dazu automatisch einen **lokalen HTTP-Endpunkt** in Home Assistant, der die Sensordaten im Shelly-kompatiblen Format bereitstellt. Das Geraet fragt diesen Endpunkt direkt ab und nutzt seinen **internen PID-Regler** fuer die Regelung – schnell, stabil und ohne Schwingen. Kein zusaetzliches Messgeraet am Speicher noetig.

```
HA Sensor (z.B. SolarEdge Meter)
        ↓
HA lokaler HTTP-Proxy
  GET /api/sunenergyxt_proxy/{id}/status
  → {"total_power": <Watt>}
        ↓
Geraet (MM=1, MD=Proxy-URL)
  interner PID-Regler
        ↓
Automatische Lade-/Entladeregelung
```

### Einrichtung

Im letzten Schritt des Setup-Dialogs erscheint ein optionaler Entity-Selector:

> **Netzfluss-Sensor (optional)**
> Waehle einen Home Assistant Sensor, der die aktuelle Netzleistung in Watt liefert.

Waehlen Sie hier den Sensor, der den aktuellen Netzfluss an Ihrem Hausanschluss misst. Das Feld kann leer gelassen werden – in diesem Fall aendert sich nichts am bisherigen Verhalten.

Nach der Konfiguration schreibt die Integration automatisch die `MD`-Verbindungszeichenkette und aktiviert `MM=1` auf dem Geraet. Beim Entfernen der Integration wird `MM` automatisch deaktiviert.

### Vorzeichenkonvention

Die Vorzeichenkonvention des gewaehlten Sensors muss mit der Geraete-API uebereinstimmen:

| Wert | Bedeutung |
|------|-----------|
| **Positiv** | Einspeisung ins Netz (Ueberschuss) |
| **Negativ** | Bezug aus dem Netz |

> **Hinweis:** Pruefen Sie das Vorzeichen Ihres Sensors vor der Konfiguration. Viele Integrationen (z. B. SolarEdge Modbus Multi) liefern den Netzfluss bereits in dieser Konvention.

### Beispiele fuer kompatible Sensoren

| Quelle | Typische Entity-ID |
|--------|--------------------|
| SolarEdge Modbus Multi (HACS) | `sensor.solaredge_i1_m1_ac_power` |
| Shelly Pro 3EM | `sensor.shelly_pro3em_total_active_power` |
| Tibber Pulse | `sensor.tibber_power` |
| Volkszaehler / SML | abhaengig von der Integration |
| ESPHome (IR-Lesekopf) | abhaengig von der Konfiguration |

## Entitaetsbeschreibung

Hinweise:

- Die tatsaechlich sichtbaren Entitaeten koennen je nach Modell, Firmware-Version und Anzahl der Erweiterungsspeicher leicht variieren
- Energiezaehler werden vom Geraet in der Regel als rohe `Wh` geliefert; die Integration zeigt sie als `kWh` an
- `TZ` muss als POSIX-Zeitzonenstring angegeben werden, nicht als Land, Stadt oder Kurzform wie `CEST`

### Sensor

| Entitaets-ID | Name | Einheit | Beschreibung |
|--------------|------|---------|--------------|
| `WS` | WLAN-SSID | - | Diagnoseinformationen zur WLAN-Verbindung |
| `WR` | WLAN-Signalstaerke | dB | Aktuelle WLAN-Signalstaerke |
| `ST` | Systemstatus | - | Betriebsstatus des Geraets. Hauefige Werte: `0 = Abgeschaltet`, `1 = Standby`, `2 = In Betrieb`, `3 = Upgrade` |
| `IW` | Gesamteingangsleistung des Systems | W | Aktuelle gesamte Eingangsleistung des Systems |
| `OP` | Gesamtausgangsleistung des Systems | W | Aktuelle gesamte Ausgangsleistung des Systems |
| `PV` | PV-Gesamteingangsleistung | W | Gesamte PV-Eingangsleistung aller MPPT-Kanaele |
| `PV1` | PV 1 Eingangsleistung | W | PV-Eingangsleistung von MPPT-Kanal 1 |
| `PV2` | PV 2 Eingangsleistung | W | PV-Eingangsleistung von MPPT-Kanal 2 |
| `PV3` | PV 3 Eingangsleistung | W | PV-Eingangsleistung von MPPT-Kanal 3 |
| `PV4` | PV 4 Eingangsleistung | W | PV-Eingangsleistung von MPPT-Kanal 4 |
| `II1` | PV 1 Eingangsstrom | A | Eingangsstrom von MPPT-Kanal 1 |
| `II2` | PV 2 Eingangsstrom | A | Eingangsstrom von MPPT-Kanal 2 |
| `II3` | PV 3 Eingangsstrom | A | Eingangsstrom von MPPT-Kanal 3 |
| `II4` | PV 4 Eingangsstrom | A | Eingangsstrom von MPPT-Kanal 4 |
| `VP1` | PV 1 Eingangsspannung | V | Eingangsspannung von MPPT-Kanal 1 |
| `VP2` | PV 2 Eingangsspannung | V | Eingangsspannung von MPPT-Kanal 2 |
| `VP3` | PV 3 Eingangsspannung | V | Eingangsspannung von MPPT-Kanal 3 |
| `VP4` | PV 4 Eingangsspannung | V | Eingangsspannung von MPPT-Kanal 4 |
| `GP` | Systemleistung am Netzanschluss | W | Leistung am Netzanschluss. Positive Werte bedeuten in der Regel Einspeisung, negative Werte in der Regel Netzbezug oder Netzladen |
| `LP` | Systemleistung am Lastanschluss | W | Aktuelle Leistung am Lastanschluss |
| `GD1` | Heutige Netzladung | kWh | Energie, die heute aus dem Netz in das System geladen wurde |
| `GD2` | Heutige Netzeinspeisung | kWh | Energie, die heute ueber den Netzanschluss ins Netz eingespeist wurde |
| `LD` | Heutige Off-Grid-Ausgabe | kWh | Heute abgegebene Off-Grid-Ausgangsenergie |
| `SC` | System-Speicherlevel | % | Gesamter SOC des Systems |
| `SC0` | Kopfspeicher | % | SOC des Kopfspeichers |
| `SC1` | Erweiterungsspeicher 1 | % | SOC des Erweiterungsspeichers 1 |
| `SC2` | Erweiterungsspeicher 2 | % | SOC des Erweiterungsspeichers 2 |
| `SC3` | Erweiterungsspeicher 3 | % | SOC des Erweiterungsspeichers 3 |
| `SC4` | Erweiterungsspeicher 4 | % | SOC des Erweiterungsspeichers 4 |
| `SC5` | Erweiterungsspeicher 5 | % | SOC des Erweiterungsspeichers 5 |
| `ON` | Anzahl der Online-Batteriepacks | - | Anzahl der aktuell online gemeldeten Batteriepacks |
| `ES` | Firmware-Version (Wi-Fi) | - | System-Wi-Fi- bzw. EMS-Firmware-Version |
| `AS` | Firmware-Version (AC-Einheit) | - | Firmware-Version der AC-Einheit |
| `DS` | Firmware-Version (DC-Einheit) | - | Firmware-Version der DC-Einheit |
| `BS0` | Firmware-Version (BMS 0) | - | BMS-Firmware-Version des Kopfspeichers |
| `BS1` | Firmware-Version (BMS 1) | - | BMS-Firmware-Version des Erweiterungsspeichers 1 |
| `BS2` | Firmware-Version (BMS 2) | - | BMS-Firmware-Version des Erweiterungsspeichers 2 |
| `BS3` | Firmware-Version (BMS 3) | - | BMS-Firmware-Version des Erweiterungsspeichers 3 |
| `BS4` | Firmware-Version (BMS 4) | - | BMS-Firmware-Version des Erweiterungsspeichers 4 |
| `BS5` | Firmware-Version (BMS 5) | - | BMS-Firmware-Version des Erweiterungsspeichers 5 |
| `SN` | SN des Systemhosts | - | Seriennummer des Geraets |
| `MS` | Zaehlerstatus | - | Verbindungsstatus des lokalen Smart Meters. Hauefige Werte: `0 = Nicht gebunden`, `1 = Online`, `2 = Offline`; bei manchen Firmware-Versionen auch `3 = IP wird angefordert` |

### Number

| Entitaets-ID | Name | Einheit | Bereich | Schritt | Beschreibung |
|--------------|------|---------|---------|---------|--------------|
| `GS` | Sollwert Leistung Netzanschluss | W | `-2400` bis `2400` | `10` | Sollwert fuer die Leistung am Netzanschluss. Bei konfiguriertem Netzfluss-Sensor wird dieser Wert vom Geraet intern geregelt. |
| `IS` | Sollwert max. Wechselrichterleistung | W | `1` bis `2400` | `10` | Maximale Wechselrichter-Ausgangsleistung. Die Obergrenze liegt bei `800W` fuer SunEnergyXT 500 und `2400W` fuer SunEnergyXT 500 Pro |
| `SI` | System Entladegrenze | % | `1` bis `30` | `1` | Minimaler SOC fuer Entladung im On-Grid-Betrieb |
| `SA` | System Ladegrenze | % | `70` bis `100` | `1` | Maximaler SOC fuer Ladung im On-Grid-Betrieb |
| `SO` | Systemlastanschluss-Entladegrenze | % | `1` bis `30` | `1` | Minimaler SOC fuer Entladung im Off-Grid- bzw. Lastanschluss-Betrieb |
| `PT` | Einstellung der automatischen Abschaltzeit | min | `30` bis `1440` | `1` | Zeit fuer die automatische Abschaltung |

### Switch

| Entitaets-ID | Name | Beschreibung |
|--------------|------|--------------|
| `LM` | Lokaler Modus | Schalter fuer den lokalen Modus. Wenn aktiv, priorisiert das Geraet die lokale Konfiguration |
| `MM` | Lokaler Eigenverbrauch | Schalter fuer den Modus "Lokaler Eigenverbrauch". Wird bei konfiguriertem Netzfluss-Sensor automatisch aktiviert. |
| `PM` | Parallelschaltmodus des Systems | Schalter fuer den Parallelbetrieb. Nur verwenden, wenn Geraetetopologie und Firmware dies unterstuetzen |

### Text

| Entitaets-ID | Name | Beschreibung |
|--------------|------|--------------|
| `MD` | Lokale Smart-Meter-Verbindung | JSON-Zeichenkette fuer die lokale Smart-Meter-Verbindung. Wird bei konfiguriertem Netzfluss-Sensor automatisch gesetzt. |
| `TZ` | Systemzeitzone | POSIX-Zeitzonenstring. Fuer China kann z. B. `CST-8` verwendet werden; fuer Deutschland mit Sommerzeit z. B. `CET-1CEST,M3.5.0,M10.5.0/3`. |

### Button

| Entitaets-ID | Name | Beschreibung |
|--------------|------|--------------|
| `RT` | Systemneustart | Sendet einen Neustartbefehl an das Geraet |

## Fehlerbehebung

### Geraet nicht gefunden

- Stellen Sie sicher, dass das Geraet eingeschaltet und mit dem lokalen Netzwerk verbunden ist
- Stellen Sie sicher, dass Home Assistant und das Geraet sich im selben Netzwerksegment befinden
- Falls die automatische Erkennung fehlschlaegt, geben Sie die IP-Adresse manuell ein
- Wenn das Netzwerk mDNS / Zeroconf blockiert, funktioniert die automatische Erkennung moeglicherweise nicht

### Probleme bei der Datenaktualisierung

- Pruefen Sie, ob die Netzwerkverbindung des Geraets stabil ist
- Pruefen Sie, ob `http://geraete-ip/read` direkt erreichbar ist
- Bestaetigen Sie nach einer Aenderung den finalen Zustand stets durch erneutes Auslesen

### Eigenverbrauchsregelung funktioniert nicht (MS = Nicht gebunden)

- Pruefen Sie ob der konfigurierte Sensor einen gueltigen numerischen Wert in Watt liefert
- Pruefen Sie ob Home Assistant vom Geraet aus erreichbar ist: `curl http://ha-ip:8123/api/sunenergyxt_proxy/{entry_id}/status`
- Stellen Sie sicher dass `LM` (Lokaler Modus) aktiviert ist
- Pruefen Sie in den HA-Logs ob Fehlermeldungen vorliegen (`Logger: custom_components.sunenergyxt`)

### Lokaler Eigenverbrauch funktioniert nicht (ohne HA-Sensor)

- Stellen Sie sicher, dass `MD` exakt dem Zaehlerbeispiel in [API.md](API.md) entspricht
- Stellen Sie sicher, dass `MM` aktiviert ist
- Pruefen Sie, ob `MS` einen online gemeldeten Zaehler zeigt und ob echte Zaehlerdaten aktualisiert werden
- Verlassen Sie sich nach dem Schreiben nicht auf `MD` als garantiertes Echo

### Zeitzone ist falsch eingestellt

- `TZ` muss als POSIX-Zeitzonenstring gesetzt werden
- Verwenden Sie nicht `Europe/Berlin`, `UTC+1`, `CET` oder `CEST` als finalen `TZ`-Wert
- Fuer Deutschland sollte ein POSIX-String mit Sommerzeitregel verwendet werden, z. B. `CET-1CEST,M3.5.0,M10.5.0/3`
- Bestaetigen Sie nach dem Schreiben die resultierende Zeitzonenwirkung, statt ein exaktes Echo des geschriebenen `TZ`-Werts zu erwarten

## Beitrag

Beitraege sind willkommen. Bitte reichen Sie Issues oder Pull Requests auf [GitHub](https://github.com/SunEnergyXT/SunEnergyXT-500-Series) ein.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Details finden Sie in der Datei [LICENSE](LICENSE).

[releases-shield]: https://img.shields.io/github/release/SunEnergyXT/SunEnergyXT-500-Series.svg
[releases]: https://github.com/SunEnergyXT/SunEnergyXT-500-Series/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/SunEnergyXT/SunEnergyXT-500-Series.svg
[commits]: https://github.com/SunEnergyXT/SunEnergyXT-500-Series/commits/main
[license-shield]: https://img.shields.io/github/license/SunEnergyXT/SunEnergyXT-500-Series.svg
