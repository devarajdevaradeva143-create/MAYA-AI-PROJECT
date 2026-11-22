# AGENTS.md — Maya AI Project Guide (for AI coders)

> Ithu project-oda **AI instruction file**.
> Vera AI (Claude / Codex / Gemini) code ezhudhum bothu ithai first padikkum.
> Simple Thanglish-la ezhuthirukken — puriya easy-ah.

---

## 1. Project enna?

**Maya AI** — local-first personal AI assistant for Windows.

- Laptop: HP OmniBook 5 (Ryzen AI 5 340)
- Model: **Qwen 3B**
- Framework: **OpenJarvis** (clone pannirukkom)
- Online AI: **Gemini** (separate command)

---

## 2. Golden Rules (break panna koodadhu)

1. **`JARVIS\OpenJarvis\` la code edit pannaadhu** ❌
   - Adhu official repo. Update issue aagum.
2. Namma code ellam **`JARVIS\custom\`** la mattum ✅
3. OpenJarvis-la change venum-na → **`JARVIS\patches\`** la `.patch` file ✅
4. Personal details (`DEVARAJ\details.md`) — **cloud-kku anuppaadhu** 🔒
5. Offline → Online data **pogaadhu** ❌
6. Important action (edit / delete / command) → **user permission kekkanum** ⚠️
7. **Maya = command only** — thana ethuvum pannaadhu

---

## 3. Folder Map — enna enga poganum

### A. Design / Docs (no code)

```
MAYA AI PROJECT\
├─ MAYA AI PROJECT.md        ← plan (design)
├─ AGENTS.md                 ← ithu file (AI guide)
├─ docs\                     ← notes, guides
└─ DEVARAJ\                  ← user details + chat history (private)
```

| Folder | Enna pannanum | Enna pannakoodadhu |
|---|---|---|
| `MAYA AI PROJECT.md` | Plan update | Code ezhutha koodadhu |
| `docs\` | Notes / guides | Secrets / personal data |
| `DEVARAJ\` | User details | Cloud upload ❌ |

### B. Common Design (Windows)

```
MAYA AI PROJECT\MAYA AI\
├─ Model\        ← Qwen 3B model files
├─ Engine\       ← CPU / GPU / NPU backends
├─ voice\        ← Tamil / English TTS
├─ persona\      ← Maya + English teacher prompts
├─ security\     ← face / voice / PIN design
├─ knowledge\    ← PDF / notes knowledge base
├─ config\       ← settings.yaml (source of truth)
├─ memory\       ← offline / online memory (separate)
├─ logs\         ← runtime logs
└─ scripts\      ← common launchers
```

| Folder | Enna pannanum |
|---|---|
| `Model\` | Model download + model config |
| `Engine\` | Backend code (cpu / gpu / npu) |
| `voice\` | TTS voice files (.onnx) |
| `persona\` | Prompt files only (.md) |
| `security\` | Biometric auth design/code |
| `knowledge\` | Document indexing |
| `config\` | Settings — code-la hardcode pannaadhu |
| `memory\` | Offline / online memory — **mix pannaadhu** |
| `logs\` | Runtime logs mattum |
| `scripts\` | Common launchers |

### C. Code (actual implementation)

```
JARVIS\
├─ OpenJarvis\        ← READ-ONLY ❌
├─ custom\            ← namma code ELLAM inga ✅
│  ├─ persona\        ← persona loader
│  ├─ tools\          ← custom tools (monitoring, reminders)
│  ├─ plugins\        ← OpenJarvis plugins
│  └─ README.md
├─ patches\           ← OpenJarvis changes (.patch)
├─ backups\           ← update commit history
├─ scripts\           ← update scripts
└─ UPDATE.md          ← safe update guide
```

| Folder | Enna pannanum |
|---|---|
| `custom\` | **Ellam namma code inga dhaan** ✅ |
| `custom\persona\` | Maya / English teacher load logic |
| `custom\tools\` | Monitoring, reminders, knowledge tools |
| `custom\plugins\` | OpenJarvis plugins |
| `patches\` | OpenJarvis-la change venum-na |
| `scripts\` | Update / setup scripts |

### D. OS-specific

```
MAYA AI PROJECT\LAPTOP\
└─ windows\app\      ← Windows app code
```

| Folder | Enna pannanum |
|---|---|
| `windows\app\` | Windows-only code (Task Scheduler, tray) |

---

## 4. 11 Modules — enga implement pannanum

| Module | Code location |
|---|---|
| Chat | `custom\` + OpenJarvis chat |
| Voice | `custom\tools\` + `MAYA AI\voice\` |
| PC Control | `custom\tools\pc_control.py` |
| Mobile Control | `MOBILE APP\` (future) |
| English Teacher | `custom\persona\` + `MAYA AI\persona\` |
| Identity & Security | `MAYA AI\security\` + `custom\tools\` |
| System Monitoring | `custom\tools\monitor.py` |
| Personal Assistant | `custom\tools\assistant.py` |
| Knowledge AI | `custom\tools\knowledge.py` + `MAYA AI\knowledge\` |
| Language Intelligence | `custom\tools\language.py` |
| Multi-device | `custom\tools\devices.py` (future) |

---

## 5. Code Rules

- Language: **Python** (OpenJarvis stack)
- Package manager: **uv** (`uv sync`, `uv run`)
- Config: `MAYA AI\config\settings.yaml` — code-la hardcode pannaadhu
- Secrets (API keys): `.env` file — git-la commit pannaadhu
- Tests: `JARVIS\custom\tests\` (create when needed)
- Logs: `MAYA AI\logs\` — personal data log pannaadhu

---

## 6. Privacy Rules (hard)

- Personal details → laptop-la mattum 🔒
- Offline memory → online-kku pogaadhu ❌
- Web search → user permission sonna mattum ✅
- Biometrics (face / voice) → local only 🔒
- Cloud = Gemini, separate command (`maya-cloud`) mattum

---

## 7. Update procedure

```powershell
powershell -ExecutionPolicy Bypass -File JARVIS\scripts\update_openjarvis.ps1
```

Details: `JARVIS\UPDATE.md`

---

## 8. AI coder checklist (finish panna munnaadi)

- [ ] OpenJarvis file edit pannala? ❌ (check `git -C OpenJarvis status`)
- [ ] Namma code `custom\` la dhaan-a? ✅
- [ ] Config `settings.yaml` use panniya? ✅
- [ ] Personal data cloud-kku anuppalaya? 🔒
- [ ] Permission prompt add panniya? ⚠️
- [ ] Update script test panniya? ✅

---

**Summary:** `OpenJarvis` = engine (read-only). `custom\` = namma code. `patches\` = engine changes. `MAYA AI\` = design/config/persona.
