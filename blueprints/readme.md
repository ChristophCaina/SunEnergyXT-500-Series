# SunEnergyXT – Grid-Beneficial Charging & Discharging
 
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.6%2B-blue?logo=homeassistant)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/Version-1.4.4-green)]()
[![Integration](https://img.shields.io/badge/Integration-SunEnergyXT%20500%20Series-orange)]()
 
Ein Home Assistant Blueprint zur netzdienlichen Steuerung des **SunEnergyXT 500 Series** Batteriespeichers. Der Blueprint lädt den Speicher anhand einer Glockenkurve – abgestimmt auf PV-Überschuss, Forecast, SOC und Wetterbedingungen – und klappt die Einspeisespitze zur Mittagszeit gezielt.
 
---
 
## 🎯 Ziel
 
Statt den Speicher morgens unkontrolliert voll zu laden, verteilt der Blueprint die Ladung über den Tag:
 
- **Morgens:** PV-Überschuss fließt primär ins Netz (Netz braucht die Energie)
- **Mittags:** Speicher lädt mit steigender Leistung und kappt die Einspeisespitze
- **Abends:** PID-Modus entlädt den Speicher bedarfsgerecht
- **Nachts:** PID-Modus versorgt das Haus, entlädt so viel wie nötig
---
 
## ⚙️ Betriebsmodi
 
### Aktives Laden `MM=0, GS negativ`
Greift sobald PV produziert und die Glockenkurve eine Zielleistung > Mindest-Überschuss ergibt.  
Die Ladeleistung ist **immer auf den tatsächlichen PV-Überschuss begrenzt** – kein Laden aus dem Netz.
 
### PID-Modus `MM=1, GS=0`
In allen anderen Situationen: Nacht, früh morgens (PV noch zu schwach für die Kurve), nach der Ladezeit, Speicher voll, oder nach HA-Neustart.  
Der interne PID des Geräts regelt automatisch auf Nulleinspeisung.
 
---
 
## 📋 Voraussetzungen
 
### Pflicht
| Entity | API-Feld | Beschreibung |
|--------|----------|--------------|
| Sensor (battery) | `SC` | Aktueller SOC in % |
| Number (power) | `GS` | Grid Setpoint (Lade-/Entladeleistung) |
| Number (power) | `IS` | Max. Inverterleistung |
| Switch | `MM` | Self-Consumption Modus |
| Sensor (power) | – | Aktuelle PV-Leistung |
| Sensor (power) | – | Netzanschluss-Leistung |
 
### Optional
| Entity | Beschreibung |
|--------|--------------|
| Number `SA` | Max. Lade-SOC vom Gerät |
| Number `SI` | Min. Entlade-SOC vom Gerät |
| Sensor `BN` | Anzahl Batteriemodule (für kap. Berechnung) |
| Forecast Sensor 1–3 | PV-Prognose heute in kWh |
| Sonnenscheindauer Sensor | Stündliche Prognose (device_class: duration) |
| Wetter Entity | Für Bewölkungsgrad-Schätzung |
| Bewölkung Sensor | Direkter Sensor 0–100% |
| Wallbox / EV 1–2 | Ladeleistung + SOC für EV-Priorisierung |
 
---
 
## 🔧 Konfigurierbare Parameter
 
### Speicher
- Max. Lade-SOC (`SA`), Min. Entlade-SOC (`SI`)
- Nacht-Reserve SOC (PID darf nicht tiefer entladen)
### PV & Netz
- Grundlast Haus (W)
- Mindest-Überschuss zum aktiven Laden (W)
- Grid-Trigger Schwellwert (W) für sofortige Reaktion
### Ladekurve
- Ladekurven-Peak (Stunde, z.B. 13 Uhr)
- Aktives Laden Ende (Stunde, z.B. 17 Uhr)
- Kurven-Aggressivität (1–5)
- SOC-Drosselungsschwelle (%)
### Solar-Prognose
- Bis zu 3 externe Forecast-Sensoren
- Sonnenscheindauer-Sensor + Anlagenleistung (kWp) + Wirkungsgrad (%)
- Schwellwert "gute Prognose" (kWh)
### E-Auto & Wallbox
- Bis zu 2 Fahrzeuge mit Ladeleistung + SOC
- EV Ziel-SOC (ab wann Speicher wieder Priorität hat)
---
 
## 📈 Ladekurve
 
Die Kurve folgt einer konvexen Potenzfunktion `t^a`:
 
```
Kurven-Aggressivität a=3 (Standard):
  Kurvenstart:  ~0%   Ladeleistung
  11:00 Uhr:   ~22%  Ladeleistung  
  12:00 Uhr:   ~51%  Ladeleistung
  13:00 Uhr:  100%   Ladeleistung (Peak)
  Nach Peak:  100%   bis charge_end_hour
```
 
Die Aggressivität bestimmt wie schnell die Kurve zum Peak ansteigt:
- `a=1`: Linearer Anstieg – früh mehr laden
- `a=3`: Standard – netzdienlich, sanfter Anstieg
- `a=5`: Sehr flach bis kurz vor dem Peak
---
 
## 🔄 Trigger
 
Der Blueprint reagiert auf:
- **Alle 2 Minuten** (Fallback-Timer)
- **PV-Start** (`pv_power_sensor above: 0`) – sofortige Reaktion
- **Grid-Änderungen** (über/unter `grid_trigger_threshold`)
- **Stündlich** (Kurvenberechnung)
- **Sonnenauf-/-untergang** (Phasenübergänge)
- **HA-Start** (sicherer Initialzustand)
---
 
## 📊 Log-Ausgaben
 
Alle Aktionen werden unter `custom_components.sunenergyxt.blueprint` geloggt:
 
```
[SunEnergyXT] AKTIVES LADEN | 12:34 | SOC: 72.5% / max: 100.0% |
Kapazität: 10.0kWh (2×5kWh) | Noch zu laden: 320W Ø nötig |
PV: 4250.0W | Grid: 2100.0W | EV: 0W (Prio: False) |
Prognose: 42.5kWh | Bewölkung: 20.0% (Faktor: 0.85) |
Kurve: 0.782 | SOC-Faktor: 1.0 |
Überschuss: 2100.0W | PV-Cap: 3950W → GS: -1641W
```
 
---
 
## ❌ Bewusste Einschränkungen (v1)
 
| Feature | Status |
|---------|--------|
| Laden aus dem Netz | ❌ Nicht in v1 – kein Netzladen |
| Dynamische Strompreise (EPEX/Tibber) | ❌ Nicht in v1 → v2 |
| Wärmepumpen-Integration | ❌ Nicht in v1 → v3 |
| Mehrere Speicher | ❌ Nicht unterstützt |
 
---
 
## 🗺️ Roadmap
 
### v1.x (aktuell)
- ✅ Netzdienliche Glockenkurve
- ✅ PV-Surplus Cap (kein Netzladen)
- ✅ EV/Wallbox Priorität
- ✅ Solar Forecast + Sonnenscheindauer
- ✅ Dynamischer Ladestart (ab PV > 0W)
### v2.0 (in Entwicklung)
- 🔄 Dynamische Strompreise (EPEX Spot, Tibber, aWATTar)
- 🔄 Intelligentes Netzladen bei günstigen Preisen (optional)
- 🔄 Max. Netzladeleistung konfigurierbar
- 🔄 Kombinierter Modus (Preis + Netzdienlich)
### v3.0 (geplant)
- 📋 Wärmepumpen-Integration
- 📋 Thermodynamische Lastoptimierung
---
 
## 🐛 Bekannte Einschränkungen
 
- **Früh morgens (PV < Kurven-Schwelle):** Der PID-Modus lädt mit vollem verfügbarem Überschuss – die Kurve greift erst wenn `target_charge_power > min_surplus_to_charge`. Parameter `min_surplus_to_charge` kann hierfür angepasst werden.
- **Simulator-Geräte:** Der TBsimulator lädt im PID-Modus aggressiver als echte Hardware – das Verhalten auf echten Geräten kann abweichen.
---
 
## 📦 Installation
 
1. Blueprint-Datei in `/config/blueprints/automation/` kopieren
2. In Home Assistant: **Einstellungen → Automationen → Blueprint importieren**
3. Neue Automation auf Basis des Blueprints erstellen
4. Pflichtfelder konfigurieren, optionale Felder nach Bedarf
---
 
## 🤝 Beitragen
 
Issues und Pull Requests sind willkommen!  
Bitte beim Melden von Bugs die Log-Ausgaben aus `custom_components.sunenergyxt.blueprint` beifügen.
 
---
 
## 📄 Lizenz
 
MIT License – siehe [LICENSE](LICENSE)
 
---
 
## Changelog
 
### v1.4.4
- Sonnenscheindauer-Sensor: Heute-Filter eingebaut (240 Einträge → nur heutige 24h)
### v1.4.3
- `charge_window_hours` nutzt `current_hour` statt entferntem `_start_good`
### v1.4.2
- **Dynamischer Ladestart:** Kein fixer `charge_start_hour` mehr – Blueprint startet sobald `pv_now > 0`
- Standby-Modus entfernt
- `charge_start_hour_good` und `charge_start_hour_poor` entfernt
- PV-Start Trigger `above: 0`
### v1.4.1
- `logger: custom_components.sunenergyxt.blueprint` in allen Log-Blöcken
### v1.4.0
- **STANDBY:** `MM=0, GS=0` → `MM=1, GS=0` – kein unkontrolliertes Netzladen mehr
- **PV-Surplus Cap:** Ladeleistung auf tatsächlichen PV-Überschuss begrenzt
- Kein Laden aus dem Netz im aktiven Lademodus
### v1.3.1
- Initiale stabile Version mit Glockenkurve, Forecast, EV, Wetter
