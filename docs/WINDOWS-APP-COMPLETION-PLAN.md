# Windows App — Completion Plan (handoff)

> Vera AI coder ithai padichu **`WINDOWS APPLICATION\windows\`** mattum complete pannanum.
> Ithu plan mattum — code ippo maathala. Ovvoru phase-um DoD pass aana pinne
> adutha phase.
>
> Verified on: 18 Nov 2026 · `WINDOWS APPLICATION\windows` → **161 tests pass**, `dist\mayaai.exe` built.

---

## 0. Rules (break panna koodadhu)

1. `JARVIS\OpenJarvis\` **read-only** ❌ — final-la `git -C JARVIS/OpenJarvis status --porcelain` empty-a irukkanum.
2. Namma code `JARVIS\custom\` + `WINDOWS APPLICATION\windows\` mattum ✅
3. Config = `MAYA AI\config\settings.yaml` — code-la hardcode pannaadhu.
4. Secrets `.env`-la mattum; commit pannaadhu.
5. Destructive / important action → permission prompt ⚠️ (ippo irukkura ConfirmDialog break pannaadhu).
6. Personal data cloud-kku pogaadhu 🔒
7. Maya = command only — thaana ethuvum pannaadhu.

---

## 1. Environment

| Item | Path / Value |
|---|---|
| Project root | `C:\Users\devar\Desktop\MAYA AI PROJECT` |
| App | `WINDOWS APPLICATION\windows\` |
| Python venv (app) | `WINDOWS APPLICATION\windows\.venv` — **ithula dhaan** `pystray`, `PySide6`, `Pillow` irukku |
| Test command | `cd "WINDOWS APPLICATION\windows"; .\.venv\Scripts\python.exe -m pytest -q` |
| Lint | `.\\.venv\\Scripts\\ruff.exe check app tests` |
| Build | `.\\.venv\\Scripts\\python.exe -m PyInstaller mayaai.spec --noconfirm` → `dist\mayaai.exe` |
| Settings | `MAYA AI\config\settings.yaml` |
| Security store | `MAYA AI\memory\offline\security.json` (PBKDF2, salt; **plaintext illa**) |
| Logs | `MAYA AI\logs\` |

**Note:** `JARVIS\.venv`-la `pystray` **illa**. Tray-related code test panna `WINDOWS APPLICATION\windows\.venv` use pannu.

---

## 2. Current state (verified)

### Working
- Chat: streaming, Stop, Retry, persona switch, history
- Voice page: STT, TTS, 3-clap wake, "Maya Maya Maya" name wake
- PC Control: 14/15 actions + ConfirmDialog for risky ones
- Settings: YAML round-trip, timestamped backups, theme
- Single instance, theme switch, tray icon (`--tray`)
- Phone server (headless): auth, chat WS, events, pc, voice, monitor — tested

### Missing / broken
| Problem | Evidence |
|---|---|
| Monitoring tab = placeholder | `app\ui\main_window.py::_build_pages()` — `MonitorPage` import/use illa |
| English Teacher tab = placeholder | `TeacherPage` import/use illa |
| Security tab = placeholder + **broken import** | `security_page.py` imports `app.services.security_watcher` — **andha file illa** |
| PIN gate missing | App open aana udane PIN kekkadhu; `main.py`-la lock logic illa |
| PIN plaintext | `security_page.py` `security.pin` value `settings.yaml`-la padikkudhu |
| `close_to_tray` / `minimize_to_tray` / `start_minimized` | Settings-la save aagum, but `closeEvent`/`changeEvent` illa |
| Phone server GUI control illa | `ServerService` irukku, but `--headless` mattum use aagudhu |
| Tests gap | `test_ui_shell.py` navigation mattum check pannudhu; page type illa |
| Docs stale | `WINDOWS APPLICATION\windows\README.md` = "build innum start pannala" |

### Verified line-level bugs (fix pannu)
| File | Line | Bug |
|---|---|---|
| `app\ui\pages\teacher_page.py` | 130, 141, 150, 162 | `self._input.setPlaceholderType(...)` — `QLineEdit`-la `setPlaceholderType` **illa** → AttributeError |
| `app\ui\pages\teacher_page.py` | 165 | `self._input.toPlainText()` — `QLineEdit`-la `toPlainText` **illa** |
| `app\ui\pages\security_page.py` | 23 | `from app.services.security_watcher import SecurityWatcher` — missing module |
| `app\ui\pages\security_page.py` | 212-224 | `self._attempts` initialize pannala → wrong PIN-la AttributeError |
| `app\ui\pages\monitor_page.py` | 147-177 | GPU/NPU/Battery/Uptime values compute aagudhu, card update aagala |
| `app\ui\pages\monitor_page.py` | 79 | Timer constructor-la start → page hidden-la kooda 2s poll |
| `app\ui\pages\pc_page.py` | 315-318 | `Notify` → `"Not implemented in this phase"` (dead branch; `_on_run` already works) |

---

## 3. File map (enna maathanum)

### Modify
```
WINDOWS APPLICATION\windows\app\main.py
WINDOWS APPLICATION\windows\app\ui\main_window.py
WINDOWS APPLICATION\windows\app\ui\pages\monitor_page.py
WINDOWS APPLICATION\windows\app\ui\pages\teacher_page.py
WINDOWS APPLICATION\windows\app\ui\pages\security_page.py   (full rewrite)
WINDOWS APPLICATION\windows\app\ui\pages\settings_page.py   (server card)
WINDOWS APPLICATION\windows\app\ui\pages\pc_page.py         (dead branch)
```

### Create
```
WINDOWS APPLICATION\windows\app\services\security_service.py
WINDOWS APPLICATION\windows\app\ui\lock_screen.py
WINDOWS APPLICATION\windows\tests\test_pages_wired.py
WINDOWS APPLICATION\windows\tests\test_monitor_page.py
WINDOWS APPLICATION\windows\tests\test_teacher_page.py
WINDOWS APPLICATION\windows\tests\test_security_service.py
WINDOWS APPLICATION\windows\tests\test_lock_screen.py
WINDOWS APPLICATION\windows\tests\test_settings_server.py   (optional)
```

### Docs
```
WINDOWS APPLICATION\windows\README.md
WINDOWS APPLICATION\windows\PLAN.md
docs\HANDOFF.md
docs\ROADMAP.md
docs\WINDOWS-APP.md   (new)
```

---

## Phase W1 — Pages wire pannu (30 min)

**File:** `app\ui\main_window.py`

1. Imports add:
```python
from app.ui.pages.monitor_page import MonitorPage
from app.ui.pages.teacher_page import TeacherPage
from app.ui.pages.security_page import SecurityPage
from app.services.security_service import SecurityService
```

2. `MayaMainWindow.__init__` signature extend — defaults vachu (existing tests break aagadhu):
```python
def __init__(
    self,
    *,
    repository: SettingsRepository | None = None,
    theme: ThemeManager | None = None,
    chat: ChatService | None = None,
    security: SecurityService | None = None,
    tray_available: bool = False,
    parent=None,
) -> None:
```
- `self._security = security or SecurityService()`
- `self._tray_available = tray_available`

3. `_build_pages()`-la branches add (ippo `else`-ku pogudhu):
```python
elif key == "monitor":
    page = MonitorPage()
elif key == "teacher":
    page = TeacherPage(voice=self._voice_adapter)
elif key == "security":
    page = SecurityPage(security=self._security)
```
`else` branch unknown key-kku mattum irukkanum.

4. `PAGE_HINTS`-la "arrive in Phase X" text remove pannu.

**DoD**
- `window.page("monitor")` → `MonitorPage`
- `window.page("teacher")` → `TeacherPage`
- `window.page("security")` → `SecurityPage`
- Placeholder text zero for these 3 tabs

---

## Phase W2 — MonitorPage fix (20 min)

**File:** `app\ui\pages\monitor_page.py`

1. `_refresh()`-la ellam card update:
```python
self._cards["GPU"].update_values("GPU", gpu_str, "—")
self._cards["NPU"].update_values("NPU", npu_str, "—")
self._cards["Battery"].update_values("Battery", bat_str, "—")
self._cards["Uptime"].update_values("Uptime", uptime_str, "—")
```

2. Hidden-la poll stop:
```python
def showEvent(self, event):
    self._timer.start(2000)
    super().showEvent(event)

def hideEvent(self, event):
    self._timer.stop()
    super().hideEvent(event)
```
Constructor-la `self._timer.start(2000)` **remove** (first refresh mattum).

3. Duplicate sparkline code (176-177) clean pannu — `_history` append + one update.

4. Public `refresh()` method add (tests-kku); `snapshot()` exception-a swallow pannadhu (currently `_update_cards_from_snapshot` `except Exception: pass` — adhu OK, but log it).

5. WMI snapshot slow-a irundha `QThread` worker-la vaikka — optional, but UI freeze avoid.

**DoD**
- 6 cards live values
- `page.hide()` → `timer.isActive() is False`
- `page.show()` → timer restart

---

## Phase W3 — TeacherPage rewrite (40 min)

**File:** `app\ui\pages\teacher_page.py`

Bugs: `setPlaceholderType` (4×), `toPlainText()`, "feedback coming later".

1. Constructor: `TeacherPage(voice=None, parent=None)` → `self._voice = voice`.

2. Lesson data:
```python
LESSONS = {
    "Vocabulary": {
        "title": "Vocabulary",
        "prompt": "What does 'serendipity' mean?\nA) Sadness  B) Chance joy  C) Anger  D) Boredom",
        "answer": "b",
        "explain": "'Serendipity' = happy accidental discovery.",
    },
    "Grammar": {
        # "Convert to Present Perfect: 'I saw that movie last year.'"
        "answer": "i have seen that movie last year",
        "explain": "have/has + past participle.",
    },
    "Pronunciation": {
        "prompt": "Word: serendipity /ˌserənˈdipədɪ/\nListen and repeat.",
        "answer": None,          # no auto-check
        "explain": "Hear the word, then record yourself.",
    },
    "Idioms": {
        "prompt": "Which sentence uses 'break the ice' correctly?\nA) ... B) ... C) He started the conversation.",
        "answer": "c",
        "explain": "'Break the ice' = start a conversation.",
    },
}
```

3. `_submit_answer()`:
- `text = self._input.text().strip()` — **not** `toPlainText`
- normalize: lowercase, strip punctuation/extra spaces
- `answer is None` → show explanation only
- correct → `✅ Correct!` + explanation (green)
- wrong → `❌ Not quite. Answer: <explain>` 
- input clear, keep focus

4. Buttons: `Back to lessons` → grid visible, lesson area hidden, input clear.

5. Pronunciation → `Hear word` button calling `self._voice.speak("serendipity")` (VoiceAdapter interface check pannu; exception-a catch panni status label-la kaattu).

6. `layout.addLayout(grid, 1)` duplicate remove; grid + lesson area rendum child widgets-a irukkanum.

**DoD**
- 4 lesson click → crash illa
- correct/wrong feedback varum
- Back button work aagum

---

## Phase W4 — Security (half day) ⚠️ biggest item

### W4.1 New: `app\services\security_service.py`

`SecurityPage` ippo `app.services.security_watcher` import pannudhu — **andha module illa**. Adhuvum PIN-ah `settings.yaml`-la plaintext-a padikkudhu — **security flaw**.

Real store wrapper:
```python
from custom.tools.security import SecurityManager

class SecurityService:
    def __init__(self, manager: SecurityManager | None = None) -> None:
        self._m = manager or SecurityManager()

    # PIN
    def pin_is_set(self) -> bool: return self._m.is_locked()
    def session_locked(self) -> bool: return self._m.is_session_locked()
    def set_pin(self, pin: str, old_pin: str | None = None) -> str: ...
    def verify_pin(self, pin: str) -> str: ...
    def lock(self) -> str: ...
    def unlock(self, method: str = "pin") -> str: ...
    def status(self) -> dict: ...
    def alerts(self) -> list[dict]: ...
```

Existing `custom.tools.security.SecurityManager` API (use pannu, reinvent pannaadhu):

| Method | Meaning |
|---|---|
| `is_locked()` | PIN set aagirukka |
| `is_session_locked()` | unlock wait pannudhu |
| `set_pin(pin, old_pin=None) -> str` | 4+ digits; PIN already set-na `old_pin` venum |
| `verify_pin(pin) -> str` | success = `"Unlocked..."`; 5 fails → 5 min lockout |
| `lock() -> str` | session lock |
| `unlock(method="pin") -> str` | verified factor-ku pinne mattum |
| `status() -> dict` | public status (no hash) |
| `get_unauthorized_alerts() -> list[dict]` | last 50 |

Delete old `security.pin` usage. `settings.yaml`-la PIN **never** store.

Optional biometrics wrappers (fail-soft try/except):
```python
from custom.tools import biometrics
biometrics.face_status(force=False)   # {"available": bool, ...}
biometrics.face_verify()              # {"ok": bool, ...} — Hello prompt
biometrics.open_face_settings()
biometrics.voice_status()             # {"enrolled": bool, ...}
biometrics.voice_reset()
```

### W4.2 Rewrite: `app\ui\pages\security_page.py`

- Constructor: `SecurityPage(security: SecurityService | None = None, parent=None)`
- Import `SecurityService` (not watcher)

Sections:
1. **PIN card**
   - status: `PIN set` / `PIN not set`
   - `Set PIN` → `QInputDialog.getText(self, "Set PIN", "New PIN (4+ digits)", QLineEdit.EchoMode.Password)`
   - `Change PIN` → old PIN + new PIN
   - `Lock now` → `service.lock()`
   - result message label (set_pin return string as-is)
2. **Windows Hello card**
   - `Check availability` → `face_status()` in background (`QThread`/`QTimer.singleShot`; subprocess ~2s)
   - `Verify now` → `face_verify()`; ok → `service.unlock("face")`
   - `Open sign-in settings` → `open_face_settings()`
3. **Voice card**
   - `voice_status()` → Enrolled / Not enrolled
   - `Reset voiceprint` (confirm) → `voice_reset()`
   - `Enroll via CLI` → new console:
     ```python
     subprocess.Popen(
         [sys.executable, "-m", "custom.cli", "biometrics", "voice-enroll"],
         cwd=str(ROOT / "JARVIS"),
         creationflags=subprocess.CREATE_NEW_CONSOLE,
     )
     ```
4. **Audit log** — `service.alerts()` last 20: `timestamp — detail`

Bug: `self._attempts` initialize pannu (ippo illa).

### W4.3 New: `app\ui\lock_screen.py`

```python
class LockScreen(QDialog):
    def __init__(self, security: SecurityService, parent=None): ...
```
- PIN `QLineEdit` (`EchoMode.Password`, max 8), Enter key → verify
- `verify_pin()` → success: `self.accept()`; fail: red label (message as-is, lockout text include)
- Optional `Windows Hello` button → `face_verify()` ok → `security.unlock("face")` → accept
- Close (X) → `reject()` → app exit
- No PIN set → never shown (caller check)

### W4.4 `app\main.py` lock gate

`run_gui()`-la, window create panna **munnaadi**:
```python
security = SecurityService()
if security.session_locked():
    from app.ui.lock_screen import LockScreen
    if LockScreen(security).exec() != QDialog.DialogCode.Accepted:
        return 0
```
`MayaMainWindow(..., security=security)` pass pannu.

**DoD**
- PIN set → app restart → lock screen
- Wrong PIN → error + attempts
- 5 wrong → 5 min lockout (manager handles)
- Right PIN → app open
- `settings.yaml`-la PIN plaintext illa
- Tests use `SecurityManager(path=tmp_path/...)` — real store touch pannaadhu

---

## Phase W5 — Tray settings work aaga (30 min)

**File:** `app\ui\main_window.py`

```python
def closeEvent(self, event):
    if self._tray_available and bool(self._repository.get("ui.close_to_tray", True)):
        event.ignore()
        self.hide()
        return
    event.accept()

def changeEvent(self, event):
    if (
        event.type() == QEvent.Type.WindowStateChange
        and self.isMinimized()
        and self._tray_available
        and bool(self._repository.get("ui.minimize_to_tray", True))
    ):
        event.ignore()
        self.hide()
    super().changeEvent(event)
```

**File:** `app\main.py`
- `start_minimized = bool(repository.get("ui.start_minimized", False))`
- `run_gui(start_hidden=HAS_PYSTRAY and start_minimized)`
- `MayaMainWindow(..., tray_available=HAS_PYSTRAY)`

**Note:** `pystray` `WINDOWS APPLICATION\windows\.venv`-la dhaan. `pyproject.toml`-la `pystray==0.19.5` already irukku.

**DoD**
- `close_to_tray=True` → close = hide, app running
- `close_to_tray=False` → close = quit
- `minimize_to_tray=True` → minimize = hide
- `start_minimized=True` + tray available → hidden start

---

## Phase W6 — Phone server UI (1 hour)

**File:** `app\ui\pages\settings_page.py` — new card `_build_server()`

UI:
- Status label: `Stopped` / `Running on 0.0.0.0:8420`
- Buttons: `Start server`, `Stop server`, `New pairing PIN`
- PIN label (large) + expiry minutes
- Checkbox: `Start phone server with Maya` → `server.auto_start` (settings.yaml)

Implementation:
```python
from app.services.server_service import ServerService

self._server: ServerService | None = None

def _server_instance(self) -> ServerService:
    if self._server is None:
        self._server = ServerService()
    return self._server
```
- `start()` 1-2s block aagum → button disable + `QTimer.singleShot(0, ...)` or `QThread`; finish-la re-enable
- PIN: `service.pairing.generate_pin()` → `(pin, expires_at)`
- Stop: `service.stop()`
- App exit: `main.py` `finally` / `app.aboutToQuit` → `service.stop()`

`ServerService` reference:
```python
ServerService(services=None)   # default build_services()
.start(timeout=START_TIMEOUT_S)   # raises RuntimeError
.stop(timeout=5.0)
.running -> bool
.bound_port -> int | None
.pairing.generate_pin() -> (pin, expires_at)
.host / .port / .last_error
```

**DoD**
- Start → port listen; status correct
- New PIN → phone pair aagum
- Stop → port free
- App quit → server stopped (no zombie)

---

## Phase W7 — Tests (1 hour)

### New test files

| File | Tests |
|---|---|
| `tests\test_pages_wired.py` | `window.page(key)` correct type for monitor/teacher/security; not `PlaceholderPage` |
| `tests\test_monitor_page.py` | fake `MonitorAdapter.snapshot()` → card text; `hide()` → timer stopped; `show()` → timer on |
| `tests\test_teacher_page.py` | each lesson selection no crash; correct answer → `Correct`; wrong → answer shown; input clear |
| `tests\test_security_service.py` | tmp `SecurityManager(path=...)`: set PIN → verify ok; wrong → message; 5 fails → lockout; `status()` no hash |
| `tests\test_lock_screen.py` | fake service: wrong PIN → error label, dialog open; right PIN → `Accepted` |
| `tests\test_settings_server.py` (optional) | fake ServerService: Start/Stop button state, PIN label text |

### Existing tests
- `test_ui_shell.py` fixture: `MayaMainWindow(..., tray_available=False)` default already OK
- Add page-type assertions

**Verify**
```powershell
cd "WINDOWS APPLICATION\windows"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests
```
Expected: **161 + new all pass**, ruff clean.

---

## Phase W8 — Docs (30 min)

| File | Change |
|---|---|
| `WINDOWS APPLICATION\windows\README.md` | "build innum start pannala" remove; real status, pages, run commands, tray/server notes |
| `WINDOWS APPLICATION\windows\PLAN.md` | Phase 6/7/8/10 status honest-a; remove "All 13 phases" overclaim |
| `docs\HANDOFF.md` | "Mobile app — not started" remove; Windows app pending list update |
| `docs\ROADMAP.md` | Mobile + Windows app section add |
| `docs\WINDOWS-APP.md` (new) | Features, security model (PIN hashed, no plaintext), server setup, tray, troubleshooting |

---

## Phase W9 — Build + smoke test (20 min)

```powershell
cd "WINDOWS APPLICATION\windows"
.\.venv\Scripts\python.exe -m PyInstaller mayaai.spec --noconfirm
# → dist\mayaai.exe
```

### Smoke checklist

| # | Check |
|---|---|
| 1 | Launch → 7 pages open, placeholder text zero |
| 2 | Monitor → CPU/RAM/GPU/NPU/Battery values update |
| 3 | Teacher → 4 lessons + answer feedback |
| 4 | Security → set PIN → close → reopen → lock screen → unlock |
| 5 | Tray → close hides; tray Open shows |
| 6 | Settings → Start server → phone pair (PIN) |
| 7 | `mayaai.exe --headless` still works |
| 8 | Chat streaming / Stop / Retry still works |
| 9 | PC Control confirm dialog still works |

---

## 4. Known pitfalls (vera AI-ku)

1. **`security_page.py` broken** — `app.services.security_watcher` module illa. Import remove; `SecurityService` use pannu.
2. **PIN plaintext** — `settings.yaml`-la `security.pin` **never** store. `SecurityManager` PBKDF2 store.
3. **QLineEdit API** — `setPlaceholderText()`, `.text()`. `setPlaceholderType()` / `toPlainText()` **illa**.
4. **`self._attempts`** — SecurityPage-la initialize pannala; `__init__`-la `self._attempts = 0`.
5. **Notify** — `pc_page._on_run()` already params collect + execute pannudhu. `_execute_after_confirm()`-la irukkura "Not implemented" branch dead code → delete pannu (or route params).
6. **pystray** — `WINDOWS APPLICATION\windows\.venv`-la mattum; `JARVIS\.venv`-la illa.
7. **Tests isolation** — `MAYA_SECURITY_STORE` env temp path-ku set pannu. Real `MAYA AI\memory\offline\security.json` touch pannaadhu.
8. **Monitor WMI** — `snapshot()` UI thread-la slow aagalam; QThread use pannu (optional).
9. **OpenJarvis** — final check `git -C JARVIS/OpenJarvis status --porcelain` empty.
10. **Permission prompts** — shutdown/delete/sleep confirm dialog break pannaadhu.
11. **Server bind** — `0.0.0.0:8420` LAN; firewall prompt varum. Error-a `last_error`-la kaattu, crash pannaadhu.
12. **Headless mode** — `--headless` separate path; GUI server code adha break pannaadhu.

---

## 5. Acceptance (final)

| Item | Pass condition |
|---|---|
| Pages | 7/7 real, placeholder zero |
| Monitor | 6 cards live, hidden-la poll illa |
| Teacher | 4 lessons, answer feedback, no crash |
| Security | PIN set/change/lock, restart lock screen, lockout, no plaintext |
| Tray | close / minimize / start-minimized settings work |
| Server | Start / Stop / PIN from UI |
| Tests | 161 + new green, ruff clean |
| Build | new `dist\mayaai.exe`, smoke pass |
| Rules | OpenJarvis clean, config-driven, permissions intact |

**Estimate:** ~1 day (W4 half day).

---

## 6. Handoff checklist (first action for the AI)

1. Read `AGENTS.md`, `JARVIS\AGENTS.md`, this file.
2. Run:
   ```powershell
   cd "WINDOWS APPLICATION\windows"
   .\.venv\Scripts\python.exe -m pytest -q
   ```
   Expected: 161 passed.
3. Start with **W1** (pages wire) — smallest, unblocks visual check.
4. After each phase: pytest + (UI-la) manual check.
5. Final: W8 docs + W9 build + smoke.
6. Report honestly: enna mudinjadhu, enna pending, enna fake/stub.
