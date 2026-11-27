# CI checks - local la run pannu

GitHub la `main` push / pull request vandha podhu `.github/workflows/ci.yml` run aagum. Same checks-a local la try pannalam. Repo root-irundhu commands run pannu. `uv` PATH la illama, local exe path use pannu: `C:\Users\devar\.local\bin\uv.exe`.

CI secrets illa, cloud credentials use pannaadhu - ellam local.

## 1. Ruff

```powershell
uvx --from ruff==0.11.10 ruff check --exclude JARVIS/custom/vendor JARVIS/custom "MAYA INTELLIGENCE"
```

`JARVIS/custom/vendor` vendored code, so skip pannu.

## 2. JARVIS core tests

```powershell
cd JARVIS
uv sync --frozen --extra dev --extra semantic
uv run --frozen --extra dev --extra semantic python -m pytest custom/tests -q
```

## 3. MAYA INTELLIGENCE tests

```powershell
cd ..
$env:PYTHONPATH = "$PWD\JARVIS;$PWD\MAYA INTELLIGENCE"
uv run --project JARVIS --frozen --extra dev --extra semantic python -m pytest "MAYA INTELLIGENCE/tests" -q
```

`PYTHONPATH` set pannadhuvum conftest path-ku JARVIS root theriyum.

## 4. Windows app tests

```powershell
cd "WINDOWS APPLICATION\windows"
$env:QT_QPA_PLATFORM = "offscreen"
uv sync --frozen --group dev
uv run --frozen --group dev python -m pytest tests -q
```

Qt offscreen mode illama headless run fail aagum.

## 5. Type check

```powershell
cd ..\..
python -m pip install pyright
pyright
```

Root-la irukka `pyrightconfig.json` our source mattum check pannum: `JARVIS/custom`, `MAYA INTELLIGENCE/maya_intelligence`, `WINDOWS APPLICATION/windows/app`. Vendor, OpenJarvis skip. Mode basic; missing imports / stubs report pannaadhu.

CI-la pyright step `continue-on-error: true` — baseline findings irukkum, so first green run block pannaadhu. Findings kuraikkum varai advisory-a irukkum.
