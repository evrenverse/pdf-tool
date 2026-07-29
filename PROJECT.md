---
name: pdf-tool
status: aktiv
goal: Agent-freundliche CLI zum Prüfen, Erzeugen und Bearbeiten von PDF-Dateien — kleine komponierbare Befehle, JSON-Ausgabe, vorhersagbare Exit-Codes
next_step: keiner — stabiles Werkzeug, wird nur bei Bedarf angefasst. Kein offener Schritt ist hier die richtige Antwort, kein Versäumnis
updated: 2026-07-26
team: [Evren]
check: make check
---

Öffentliche Python-CLI unter [github.com/evrenverse/pdf-tool](https://github.com/evrenverse/pdf-tool), v0.1.0.
Teil derselben Werkzeugfamilie wie `xlsx-tool` und `docx-tool`: agent-native
Kommandozeilenwerkzeuge für Dokumentformate, jeweils mit portabler Agent Skill.

| Datei | Zweck |
| --- | --- |
| [`README.md`](README.md) | Einstieg, Befehle, Beispiele |
| [`AGENTS.md`](AGENTS.md) | verbindliche Regeln für Agents |
| [`CHANGELOG.md`](CHANGELOG.md) | Release-Historie |
| `Makefile` | `make check` = ruff format --check, ruff check, typecheck |

`TODO.md` und `LEDGER.md` gibt es noch nicht — sie entstehen beim ersten Eintrag,
nicht auf Vorrat.
