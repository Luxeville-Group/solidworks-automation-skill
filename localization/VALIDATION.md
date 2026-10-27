# Localization validation — 2026-10-27

This change localizes upstream commit `f9d6efbecf297bcdfffc451de81ba3a7bdea6a0d` for Turkish and English. It does not expand native CAD capability claims.

## Scope

- Turkish desktop UI and guided interactions, retaining English CAD/API terminology.
- English technical documentation, skill instructions and source comments; Turkish onboarding and terminology guides.
- Turkish/English prompt recognition and Unicode text handling.
- Fork installation/release links and packaged language resources.
- Legacy localized CAD identifiers retained as escaped compatibility data; historical upstream media retained without active guide embeds.
- Capability keys, status/version fields, arrays and engineering limits preserved.

## Executed checks

| Check | Result |
|---|---|
| `python -m pytest tests apps/desktop/tests -q` | 879 passed, 15 skipped |
| Node installer/startup regressions | 6 passed |
| Frontend TypeScript/Vite build | Passed |
| Frontend Vitest | 9 passed |
| Browser delivery-gate scenarios | Desktop, compact and incomplete cases passed |
| Browser preview scenarios | Desktop, compact/mobile, DXF, seven demos and WebGL-to-PNG fallback passed |
| `scripts/validate_skill.py` | 245 Python files and 9 JSON schemas valid |
| `scripts/validate_mcp.py` | 66 tools discoverable |
| Skill metadata validation | Root and all five subskills passed |
| Bundled skill / release checks | 247 files; 29 capability entries; passed |
| Tracked/new text scan | No literal Han characters remaining |
| Root guide links / Git whitespace check | Passed |

New regressions cover Turkish uppercase routing, Turkish/English feature selection, Unicode retrieval, localized CAD aliases, non-default VibeCAD dimensions, fork-only installer updates, and Turkish PDF title extraction with unchanged vector geometry.

## Boundaries

Native SolidWorks/AutoCAD modeling was not run on this machine. Rust/Cargo was unavailable, so native Tauri compilation and live packaged-app acceptance remain unverified locally. Browser checks exercised the frontend. Optional environment-dependent Python cases were skipped.

Automatic desktop updates are disabled until the fork has its own trusted signing and release configuration; signature verification remains intact. No localized installer binary is published by this change. The existing npm installer now refuses to update an installation from another repository and retains files on a failed update.

Dependency versions remain unchanged. The frontend dependency install reported three existing audit advisories (two moderate, one high); this localization does not resolve them.

Türkçe: Bu kontroller yazılım ve dil uyarlamasını doğrular. Gerçek CAD modeli, teknik resim ve üretim uygunluğu hedef bilgisayarda makine mühendisi tarafından ayrıca kontrol edilmelidir.
