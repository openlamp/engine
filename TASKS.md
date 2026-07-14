# TASKS — openlamp-engine

- ☐ **Packager le moteur en appli desktop no-install** (`.app` macOS + `.exe` Windows ; barre de menu/tray ; **signée + notarisée** ; **headless** — statut + config des lampes uniquement, **pas d'UI de contrôle riche**) → enlève la seule vraie barrière du chemin universel (« lancer un process Python »), donc n'importe quel frontend (Ableton Mode A, CLI, contrôleur MIDI matériel) marche sans terminal. **Tier 1 accessibilité — à construire AVANT la couche Tier 2 Max for Live** (principe « accessible à tous d'abord », cf. [openlamp/live DESIGN.md](https://github.com/openlamp/live/blob/main/docs/DESIGN.md)). Scope **headless-only** pour ne pas cannibaliser la surface de contrôle payante LumiDeck.

## See also

- Les tâches runtime de `midi.py` (test end-to-end sur vraies lampes, rate-limit du beat pulse via UDP realtime, test MPE, Link refinement, MIDI 2.0) sont suivies dans [openlamp/wled-midi TASKS.md](https://github.com/openlamp/wled-midi/blob/main/TASKS.md) — le moteur est l'implémentation de référence de cette convention.
