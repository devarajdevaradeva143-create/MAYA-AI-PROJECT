# OpenJarvis — Safe Update Guide (Simple Thanglish)

> OpenJarvis update pannum bothu issue varaadhu maari setup.
> Rule: **OpenJarvis files direct-ah edit panna koodadhu.**

---

## 1. Golden Rules

1. **OpenJarvis\ folder-la code edit pannaadhu** ❌
2. Namma code ellam `custom\` folder-la mattum ✅
3. OpenJarvis-la change venum-na → `patches\` folder-la `.patch` file-ah vaithukko
4. Update panna munnaadi — commit hash backup aagum ✅
5. Update panna aprm — `uv sync` run pannum ✅

---

## 2. Folder Layout

```
JARVIS/
├─ OpenJarvis/          ← official repo (edit pannaadhu)
├─ custom/              ← namma Maya code inga
├─ patches/             ← OpenJarvis changes (patch files)
├─ backups/             ← update history / config backup
├─ scripts/
│  └─ update_openjarvis.ps1    ← Windows
└─ UPDATE.md            ← ithu file
```

---

## 3. Update panna (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_openjarvis.ps1
```

Enna pannum:
1. Current commit hash backup
2. Local changes irundha → auto stash
3. `git pull --ff-only` (merge issue varaadhu)
4. `patches\*.patch` reapply
5. Stash restore
6. `uv sync` — dependencies update

---

## 5. Romba safe-ah venum-na

```powershell
# Dependencies skip panni update mattum
powershell -ExecutionPolicy Bypass -File scripts\update_openjarvis.ps1 -SkipDeps
```

---

## 6. Update fail aana (rollback)

```powershell
cd OpenJarvis
git log --oneline -5        # old commit paaru
git checkout <old-commit>   # rollback
```

Backup log: `backups\commits.log`

---

## 7. Issue varaadhu maari tips

- Update panna munnaadi `git status` clean-ah irukkanum
- `custom\` folder-la mattum code ezhudhu
- OpenJarvis-la change venum-na patch file use pannu
- Update aprm `scripts\qa_check` (namma QA) run pannu
- Major update (version jump) — `CHANGELOG.md` padichu paaru

---

**Rule simple-ah:** Namma code = `custom\`. OpenJarvis = read-only. Patch = `patches\`.
