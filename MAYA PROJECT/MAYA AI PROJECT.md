# MAYA AI — Plan (Simple Thanglish)

> Ithu Maya AI project plan. Simple-ah, Thanglish-la.
> Status: Design ready — build innum illa.

---

## 1. Maya AI enna?

Maya AI = un laptop-la run aagura personal assistant.

Nee pesuva — Maya badhil sollum.
Tamil, English, Thanglish — nee pesura language-la.

---

## 2. Laptop + Model

Un laptop: **HP OmniBook 5 (Ryzen AI 5 340)**

- CPU — slow, aana always work 🐢
- GPU — Radeon 840M, fast 🚀
- NPU — Ryzen AI 50 TOPS, battery save 🔋
- NVIDIA GPU — illa (AMD dhaan)

**Model:** Qwen 3B — light + fast ✅

---

## 3. 11 Modules

| # | Module | Status |
|---|---|---|
| 1 | 💬 Chat | ✅ Design ready |
| 2 | 🎤 Voice | ✅ Design ready |
| 3 | 🖥️ PC Control | ✅ Design ready |
| 4 | 📱 Mobile Control | ✅ Android App Ready (APK built) |
| 5 | 📚 English Teacher | ✅ Design ready |
| 6 | 🔐 AI Identity & Security | ⏳ New — design |
| 7 | 📊 System Monitoring | ⏳ New — design |
| 8 | ⏰ Personal Assistant | ⏳ New — design |
| 9 | 📖 Personal Knowledge AI | ⏳ New — design |
| 10 | 🌐 Language Intelligence | ⏳ New — design |
| 11 | 🔗 Multi-device Connection | ⏳ New — design |

---

## 4. Folder structure

```
MAYA AI PROJECT\
├─ MAYA AI PROJECT.md     ← ithu plan
├─ MAYA AI\               ← rendu OS-kum common
│  ├─ Model\              ← AI brain (Qwen 3B)
│  ├─ Engine\             ← CPU / GPU / NPU
│  ├─ voice\              ← Tamil / English voice
│  ├─ persona\            ← Maya personality
│  ├─ security\           ← face / voice / PIN (local only)
│  ├─ knowledge\          ← PDF, notes, documents
│  ├─ config\             ← settings
│  ├─ memory\             ← offline + online memory
│  ├─ logs\               ← records
│  └─ scripts\            ← launchers
├─ LAPTOP\
│  ├─ windows\            ← Windows app
│  └─ fedora\             ← Fedora app
├─ DEVARAJ\               ← un details + chat history
├─ MOBILE APP\            ← appuram
└─ docs\                  ← notes
```

---

## 5. Offline AI / Online AI

**Offline AI:**
- Brain laptop-la mattum
- News, world news, AI, IT, technology — internet-la irundhu edukkalam ✅
- Nee permission sonna mattum search pannum

**Online AI:**
- **Gemini** (API key venum)
- Thani command — `maya-cloud`
- Offline-oda mix aagadhu

**Rule:**
- Online → Offline ✅ pogalam
- Offline → Online ❌ **pogave koodadhu**

---

## 6. Memory

Rendu memory — thani thani:

- `memory\offline\` — offline AI memory
- `memory\online\` — online AI memory

Offline memory online-kku poagadhu.

---

## 7. Privacy 🔒

- Personal details (`DEVARAJ\details.md`) — laptop-la mattum
- Eppovum cloud-kku poagave koodadhu
- Offline chat history — cloud-kku poagadhu
- News / tech info mattum internet-la edukkalam
- **Face / Voice biometrics — laptop-la mattum**, cloud-kku poagadhu

---

## 8. Permission

**Maya = command only.**
Nee solluratha mattum seiyum. Thana ethuvum pannaadhu.

| Action | Enna aagum |
|---|---|
| Read | ✅ Free |
| Edit | ⚠️ Permission kekkum |
| Delete | ⚠️ Permission kekkum |
| Important | ⚠️ Permission kekkum |
| Apps / commands | ⚠️ Permission kekkum |

---

## 9. Maya personality

Maya = caring girlfriend style 💕

- Sweet, playful, supportive
- Short replies
- Tamil / English / Thanglish
- No explicit content
- Un details safe

File: `MAYA AI\persona\girlfriend.md`

---

## 10. Voice

- Tamil voice — Piper
- English voice — Windows SAPI / Piper
- Voice file rendu OS-kum same
- Voice input → chat-la text-ah varum

---

## 11. Background work

Maya background-la run aagum.
App close pannaalum velai seiyum.

| Platform | Eppadi |
|---|---|
| Windows | Startup app / Task Scheduler |
| Fedora | systemd service |
| Mobile | Background service (appuram) |

### Wake up

- 👏👏👏 **3 clap** → Maya wake up
- 🗣️ **"Maya, Maya, Maya"** (3 times) → Maya wake up

Wake aana aprm:

```
Maya: "Sollu da, enna venum?"
```

---

## 12. WhatsApp (appuram)

- Full control possible
- Message read / send / auto-reply
- Unofficial — ban risk irukku ⚠️
- Ippo venam — appuram paakalam

---

## 13. PC control

- Apps open / close
- Files read / edit / delete
- Commands
- Important action-ku permission kekkum

---

## 14. Mobile control

Phone-ah Maya control pannum — app connect aana aprm.

```
Phone app  →  WiFi  →  Laptop Maya AI
```

| Control | Possible? |
|---|---|
| Apps open / close | ✅ |
| Message send / read | ✅ permission-oda |
| Calls | ✅ permission-oda |
| Files | ✅ permission-oda |
| Screen control | ✅ Android Accessibility |

- iPhone → full control illa ❌

---

## 15. AI Identity & Security 🔐 (new)

Maya unna identify pannum — unauthorized user use panna mudiyaadhu.

**3 methods:**
- 🧑 **Face Recognition** — camera
- 🎙️ **Voice Recognition** — mic
- 🔢 **PIN / Password** — manual

**Extra:**
- Unauthorized User Detection — vera yaar use pannaalum alert

**Rules:**
- Biometrics laptop-la mattum 🔒
- Cloud-kku poagadhu
- Lock aana aprm — PIN backup

**Status:** Design only.

---

## 16. System Monitoring 📊 (new)

Maya laptop health-ah paathukkum:

- CPU / GPU / NPU usage
- RAM usage
- Temperature
- Battery / Network
- SSD health

**Eppadi:** background-la check pannum, problem-na sollum.

**Status:** Design only.

---

## 17. Personal Assistant ⏰ (new)

- ⏰ Alarm
- 📌 Reminders
- 📅 Calendar
- ✅ To-do List
- 🗓️ Daily Schedule

**Eppadi:** "Maya, 6:30-ku alarm vai" → set aagum.

**Status:** Design only.

---

## 18. Personal Knowledge AI 📖 (new)

- 📄 PDF Reading
- 📊 Document Analysis
- 📝 Personal Notes
- 🔍 Local File Search
- 🗄️ Private Knowledge Database

**Rules:**
- Ellam laptop-la mattum 🔒
- Cloud-kku poagadhu
- Nee permission sonna mattum read pannum

**Status:** Design only.

---

## 19. Language Intelligence 🌐 (new)

- Tamil ↔ English Translation
- Speech Translation
- Pronunciation Training
- English Practice

**English Teacher-oda connect aagum.**

**Status:** Design only.

---

## 20. Multi-device Connection 🔗 (new)

- 📱 Android Connection
- 💻 Laptop Synchronization
- 📡 Local Wi-Fi
- 🌍 Remote Access

**Rules:**
- Local Wi-Fi first
- Remote access — password protection
- Un details device-ku device poagadhu 🔒

**Status:** Design only.

---

## 21. Extra features (design)

Ithu bonus features — core 11 modules-ku appuram.

| Feature | Enna pannum |
|---|---|
| 📸 OCR | Image-la irukkura text-ah padikkum |
| 📰 Morning briefing | News + weather + schedule — kalaila sollum |
| 🎯 Focus mode | Distraction apps block pannum |
| 🗂️ Smart file organizer | Downloads / Desktop files auto arrange |
| 💰 Expense tracker | Daily selavu note pannum |
| 🎵 Media control | Music / video play, pause, next |
| 🧹 PC cleanup | Temp files clean pannum (permission-oda) |
| 🔔 Notification summary | Important notifications mattum sollum |
| 📋 Clipboard manager | Copy panna items history |
| 🌤️ Weather | Online permission-oda weather sollum |
| 🆘 Emergency mode | Quick contacts / alert |
| 🔐 Password manager | Local only — cloud illa 🔒 |
| 🔋 Battery saver mode | Power save tips + settings |
| 📶 Network monitor | WiFi speed, data usage |
| 💾 Disk space analyzer | Periya files kandupidikkum |
| ⌨️ Typing / shortcut helper | Windows shortcuts teach |
| ✅ Habit tracker | Daily habit check |
| 🎂 Birthday reminder | Important dates |

**Rules:**
- Ellam design only — build illa
- Important action → permission ⚠️
- Personal data cloud-kku poagadhu 🔒

---

## 22. Full plans (files)

Ithu 3 files-ah vera AI coder (Claude / Codex / Gemini / OpenCode) follow pannum:

| Enna | File |
|---|---|
| 📱 Mobile app (Android) | `MOBILE APP\PLAN.md` |
| 💻 Windows app + phone server | `LAPTOP\windows\PLAN.md` |
| 🔗 Phone ↔ laptop API | `docs\API-CONTRACT.md` |

**Rules:**
- Coding start pannum munnaadi `AGENTS.md` + indha 3 files padikkum
- API change panna → `docs\API-CONTRACT.md` update pannum
- `OpenJarvis\` read-only ❌
- Plan-la illadha feature add pannaadhu (first plan update ✅)

---

## 23. Steps

1. Folder structure ✅ ready
2. Plan ✅ ready
3. AI model download — Qwen 3B
4. Engine setup (CPU / GPU / NPU)
5. Basic chat app
6. Voice + persona
7. Online mode (Gemini)
8. English teacher
9. Security (face / voice / PIN)
10. System monitoring
11. Personal assistant
12. Knowledge AI
13. Language intelligence
14. Multi-device
15. WhatsApp (last)

---

**Next:** Model download illa Engine setup — edhu start pannalam?
