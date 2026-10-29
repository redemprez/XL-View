# Development and builds

## Environment

The current MIDI backend is Windows-only. Use Windows x64 and Python 3.11. Runtime requirements are in `requirements.txt`; the release build pins PySide6 6.11.0 and PyInstaller 6.19.0 in `installer/requirements-build.txt`.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe main.py --offline
$env:QT_QPA_PLATFORM = 'offscreen'
.venv\Scripts\python.exe -m pytest -q
```

Tests use fake MIDI transports and protocol fixtures. They deliberately forbid opening physical MIDI ports. The two D50 fixture files contain only controller assignments and protocol records, not instrument patches, audio or credentials.

## Build the installer

Install Inno Setup 6 in its standard Windows location, then:

```powershell
.venv\Scripts\python.exe -m pip install -r installer/requirements-build.txt
.venv\Scripts\python.exe installer/build_installer.py
```

Outputs include the installer EXE, matching source ZIP and SHA256SUMS in `release/`. The staging payload is `release/payload/XL View`. Keep `_internal` with the application EXE; it is not a standalone single-file application. See [BUILD.txt](../installer/BUILD.txt) for details.

The existing build script's source archive contains runtime and packaging sources. The repository additionally supplies tests, English documentation and CI. The 0.7.0 binary predates these publication files; use the attached source ZIP for its original packaged sources. The repository MIT License also applies to the original XL View sources in that ZIP. Third-party licensing is unchanged.

For an offline packaged-app check:

```powershell
& '.\release\payload\XL View\XL View.exe' --check-install "$env:TEMP\xl-view-check.json"
```

This check opens no MIDI ports. Do not run `installer/test_installer.py` casually: it installs and uninstalls a temporary copy and is intended only for an isolated installer test environment.

## Code map

| Location | Responsibility |
| --- | --- |
| `main.py` | Application entry point and offline installation check |
| `lcxl/ui.py`, `widgets.py`, `editor.py` | Main window, controller drawing and editor |
| `lcxl/label_style.py`, `settings_dialog.py` | Label appearance and preferences |
| `lcxl/protocol.py` | Custom Mode parsing/encoding and MIDI value interpretation |
| `lcxl/device.py`, `transport.py` | Serialized device work and WinMM access |
| `lcxl/library.py`, `preset_library.py` | Local versioned library and its dialog |
| `lcxl/workflows.py`, `workspace_tools.py` | Draft edits, selection and application workflows |
| `installer/`, `XL View.spec` | Windows packaging and dependency notices |
| `tests/` | Offline regression suite |

The original SVG icon is in `lcxl/assets`. Regeneration with `build_icon.py` additionally needs Pillow. The checked-in PNG and ICO already support normal builds.

Do not include personal `presets/`, screenshots from private sessions, diagnostic dumps, generated binaries or credentials in source commits. Release binaries belong in GitHub Releases.
