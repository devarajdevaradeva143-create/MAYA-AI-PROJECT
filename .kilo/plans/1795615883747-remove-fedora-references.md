# Plan: Remove Fedora References from MAYA AI PROJECT

## Goal
Remove all Fedora-related documentation, code references, and mentions since the project will be Windows + Android only.

## Files to Update

### Documentation Files
1. **docs/REQUIREMENTS.md** - Remove Fedora app section, dual-boot references, update scope
2. **docs/ROADMAP.md** - Remove Fedora from Phase 8 & 13, update idle detection
3. **docs/API-CONTRACT.md** - Remove "Windows + Fedora share" 
4. **docs/BIOMETRICS.md** - Remove Fedora idle detection (xprintidle)
5. **docs/MOBILE-CONNECTION-MODES.md** - Remove Fedora bluetooth instructions
6. **docs/HANDOFF.md** - Remove Fedora launcher, systemd service references
7. **docs/REMOTE-CONTROL.md** - Remove Fedora adapter mention
8. **docs/VOICE.md** - Remove Windows vs Fedora voice section (if exists)

### MAYA AI Common Files
9. **MAYA AI/README.md** - Change "Windows + Fedora" to "Windows only"
10. **MAYA AI/config/settings.yaml** - Update comment
11. **MAYA AI/scripts/README.md** - Remove Fedora reference
12. **MAYA AI/scripts/maya.sh** - Delete file (Fedora-only launcher)
13. **MAYA AI/voice/README.md** - Remove Windows vs Fedora section
14. **MAYA AI/voice/english/README.md** - Remove Fedora Piper reference

### Windows Application
15. **WINDOWS APPLICATION/README.md** - Remove Fedora mentions, remove fedora folder reference
16. **WINDOWS APPLICATION/windows/PLAN.md** - Remove "Windows + Fedora" from author line

### JARVIS Engine
17. **JARVIS/UPDATE.md** - Remove Fedora update script reference
18. **JARVIS/scripts/update_openjarvis.sh** - Delete file (Fedora-only)
19. **JARVIS/custom/server/__init__.py** - Update docstring
20. **JARVIS/custom/tools/connection_manager.py** - Remove Fedora references
21. **JARVIS/custom/tools/watchdog.py** - Remove Fedora xprintidle, keep Windows only

### Mobile App
22. **MOBILE APP/PLAN.md** - Remove Windows/Fedora column
23. **MOBILE APPLICATION/PLAN.md** - Remove Windows/Fedora column
24. **MOBILE APPLICATION/app/src/main/java/com/devaraj/maya/ui/laptop/LaptopScreen.kt** - Change "Linux / Fedora" to "Linux"

## Files to Delete
- `MAYA AI/scripts/maya.sh`
- `JARVIS/scripts/update_openjarvis.sh`

## Validation
- Search for "Fedora", "fedora" - should return 0 results (except llama.cpp third-party deps)
- Search for "xprintidle" - should be removed
- Search for "systemd" - should be removed from project files
- Build and tests should still pass on Windows

## Out of Scope
- Third-party llama.cpp Fedora references (vendor code)
- Fedora-specific CI/CD if any exists