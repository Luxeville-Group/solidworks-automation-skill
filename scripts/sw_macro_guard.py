"""
SOLIDWORKS VBA macro generation guard.

Supports GPT, Kimi, Claude, and other model integrations:
- Select prompting strategy by model family.
- Validate generated VBA.
- Retry parsing failures with stronger format constraints.
- Fall back to local keyword-based templates after repeated failures.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional


DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRIES = 2


def _configure_stdio_utf8() -> None:
    """Prefer UTF-8 diagnostics on Windows systems with legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_stdio_utf8()

CORE_OBJECT_PATTERNS = (r"\bSldWorks\.SldWorks\b", r"\bSldWorks\b", r"\bswApp\b")
MODELDOC_PATTERNS = (r"\bModelDoc2\b", r"\bswModel\b")
SUB_PATTERN = r"\bSub\s+\w+\s*\("
END_SUB_PATTERN = r"\bEnd\s+Sub\b"

GPT_PROMPT = """You are a SOLIDWORKS VBA automation engineer. Output executable VBA macro source only."""

STRICT_FORMAT_PROMPT = """You are a SOLIDWORKS VBA automation engineer.
Follow these formatting requirements:
1. Output one complete VBA source listing, without Markdown or explanations.
2. Include Sub main() and End Sub.
3. Declare and initialize the SldWorks.SldWorks and ModelDoc2 core objects.
4. Use meters for all lengths; explicitly divide millimeters by 1000#.
5. Do not output JSON, natural-language explanations, pseudocode, or ellipses.
"""

RETRY_PROMPT_SUFFIX = """
The previous output failed automatic validation. Correct it strictly:
- Output VBA source only.
- Include SldWorks / ModelDoc2 / Sub main() / End Sub.
- Do not include Markdown fences, explanations, JSON, or placeholders.
"""


VBA_TEMPLATES: Dict[str, str] = {
    "cube": r'''
Option Explicit

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2

Sub main()
    Set swApp = Application.SldWorks
    Set swModel = swApp.NewPart
    If swModel Is Nothing Then
        MsgBox "Yeni parça belgesi oluşturulamadı"
        Exit Sub
    End If

    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0
    swModel.SketchManager.InsertSketch True
    swModel.SketchManager.CreateCenterRectangle 0#, 0#, 0#, 0.025, 0.025, 0#
    swModel.SketchManager.InsertSketch True
    swModel.FeatureManager.FeatureExtrusion3 True, False, True, 0, 0, 0.05, 0#, False, False, False, False, 0#, 0#, False, False, False, False, True, False, True, 0, 0#, False
    swModel.ForceRebuild3 False
End Sub
'''.strip(),
    "cylinder": r'''
Option Explicit

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2

Sub main()
    Set swApp = Application.SldWorks
    Set swModel = swApp.NewPart
    If swModel Is Nothing Then
        MsgBox "Yeni parça belgesi oluşturulamadı"
        Exit Sub
    End If

    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0
    swModel.SketchManager.InsertSketch True
    swModel.SketchManager.CreateCircleByRadius 0#, 0#, 0#, 0.025
    swModel.SketchManager.InsertSketch True
    swModel.FeatureManager.FeatureExtrusion3 True, False, True, 0, 0, 0.05, 0#, False, False, False, False, 0#, 0#, False, False, False, False, True, False, True, 0, 0#, False
    swModel.ForceRebuild3 False
End Sub
'''.strip(),
    "extrude": r'''
Option Explicit

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2

Sub main()
    Set swApp = Application.SldWorks
    Set swModel = swApp.NewPart
    If swModel Is Nothing Then
        MsgBox "Yeni parça belgesi oluşturulamadı"
        Exit Sub
    End If

    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0
    swModel.SketchManager.InsertSketch True
    swModel.SketchManager.CreateCornerRectangle -0.03, -0.02, 0#, 0.03, 0.02, 0#
    swModel.SketchManager.InsertSketch True
    swModel.FeatureManager.FeatureExtrusion3 True, False, True, 0, 0, 0.01, 0#, False, False, False, False, 0#, 0#, False, False, False, False, True, False, True, 0, 0#, False
    swModel.ForceRebuild3 False
End Sub
'''.strip(),
    "sketch": r'''
Option Explicit

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2

Sub main()
    Set swApp = Application.SldWorks
    Set swModel = swApp.NewPart
    If swModel Is Nothing Then
        MsgBox "Yeni parça belgesi oluşturulamadı"
        Exit Sub
    End If

    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0
    swModel.SketchManager.InsertSketch True
    swModel.SketchManager.CreateCenterRectangle 0#, 0#, 0#, 0.025, 0.015, 0#
    swModel.SketchManager.CreateCircleByRadius 0#, 0#, 0#, 0.006
    swModel.SketchManager.InsertSketch True
    swModel.ForceRebuild3 False
End Sub
'''.strip(),
}


KEYWORD_TEMPLATE_MAP = {
    "cube": ("küp", "kup", "blok", "cube", "box"),
    "cylinder": ("silindir", "silindirik", "cylinder"),
    "extrude": ("ekstrüzyon", "ekstruzyon", "çıkıntı", "cikinti", "extrude", "boss"),
    "sketch": ("eskiz", "çizim", "cizim", "sketch"),
}


@dataclass
class MacroValidationResult:
    """VBA macro validation result."""

    ok: bool
    issues: List[str]


@dataclass
class MacroGenerationResult:
    """Macro generation result."""

    code: str
    source: str
    attempts: int
    validation: MacroValidationResult


def normalize_model_family(model_name: Optional[str]) -> str:
    """Normalize a model name to gpt / kimi / claude / generic."""
    name = (model_name or "").strip().lower()
    if not name:
        return "generic"
    if any(token in name for token in ("gpt", "openai", "o3", "o4", "o1")):
        return "gpt"
    if "kimi" in name or "moonshot" in name:
        return "kimi"
    if "claude" in name or "anthropic" in name:
        return "claude"
    return "generic"


def build_prompt(user_request: str, model_name: Optional[str] = None, strict: Optional[bool] = None) -> str:
    """Build a prompt for the model family."""
    family = normalize_model_family(model_name)
    use_strict = strict if strict is not None else family in {"kimi", "claude", "generic"}
    system_prompt = STRICT_FORMAT_PROMPT if use_strict else GPT_PROMPT
    return f"{system_prompt}\n\nUser request:\n{user_request.strip()}\n"


def extract_vba_code(text: str) -> str:
    """Extract VBA source from model output."""
    if not text:
        return ""
    fence = re.search(r"```(?:vb|vba|visualbasic)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text.strip()


def _contains_any_pattern(code: str, patterns: Iterable[str]) -> bool:
    """Check whether source matches any regular expression."""
    return any(re.search(pattern, code, re.IGNORECASE) for pattern in patterns)


def validate_vba_macro(code: str) -> MacroValidationResult:
    """Check the minimum VBA validity requirements before SOLIDWORKS execution."""
    issues: List[str] = []
    normalized = code.strip()
    if not normalized:
        issues.append("Kod boş")
    if not _contains_any_pattern(normalized, CORE_OBJECT_PATTERNS):
        issues.append("SOLIDWORKS temel nesnesi SldWorks eksik")
    if not _contains_any_pattern(normalized, MODELDOC_PATTERNS):
        issues.append("ModelDoc2 belge nesnesi eksik")
    if not re.search(SUB_PATTERN, normalized, re.IGNORECASE):
        issues.append("Sub giriş noktası eksik")
    if not re.search(END_SUB_PATTERN, normalized, re.IGNORECASE):
        issues.append("End Sub eksik")
    if "..." in normalized or "TODO" in normalized.upper():
        issues.append("Placeholder veya tamamlanmamış kod içeriyor")
    return MacroValidationResult(ok=not issues, issues=issues)


def select_template_key(user_request: str) -> Optional[str]:
    """Select a local VBA template using user-request keywords."""
    text = user_request.lower()
    for key, keywords in KEYWORD_TEMPLATE_MAP.items():
        if any(keyword.lower() in text for keyword in keywords):
            return key
    return None


def fallback_macro_for_request(user_request: str) -> Optional[str]:
    """Return a local fallback VBA template for the request."""
    key = select_template_key(user_request)
    if key is None:
        return None
    return VBA_TEMPLATES[key]


def generate_macro_with_guard(
    user_request: str,
    model_call: Callable[[str, int], str],
    model_name: Optional[str] = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> MacroGenerationResult:
    """
    Generate a SOLIDWORKS VBA macro with validation, retries, and template fallback.

    The integration supplies model_call(prompt, timeout_seconds).
    """
    last_validation = MacroValidationResult(ok=False, issues=["Model henüz çağrılmadı"])
    prompt = build_prompt(user_request, model_name=model_name)
    attempts = 0

    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        try:
            raw_output = model_call(prompt, timeout_seconds)
        except TimeoutError:
            raw_output = ""
            last_validation = MacroValidationResult(ok=False, issues=["Model isteği zaman aşımına uğradı"])
        else:
            code = extract_vba_code(raw_output)
            validation = validate_vba_macro(code)
            last_validation = validation
            if validation.ok:
                return MacroGenerationResult(
                    code=code,
                    source="model",
                    attempts=attempts,
                    validation=validation,
                )

        prompt = build_prompt(user_request, model_name=model_name, strict=True) + RETRY_PROMPT_SUFFIX
        if last_validation.issues:
            prompt += "\nMevcut doğrulama sorunları:\n" + "\n".join(f"- {issue}" for issue in last_validation.issues)

    fallback = fallback_macro_for_request(user_request)
    if fallback:
        validation = validate_vba_macro(fallback)
        return MacroGenerationResult(
            code=fallback,
            source="local_template",
            attempts=attempts,
            validation=validation,
        )

    raise ValueError("Model çıktısı doğrulamadan geçemedi ve yerel VBA fallback şablonu eşleşmedi: " + "; ".join(last_validation.issues))


def write_macro_file(code: str, output_path: str) -> str:
    """Write VBA source locally for an agent or user to copy into the SOLIDWORKS macro environment."""
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    return str(path)


def _parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="SOLIDWORKS VBA macro prompt, doğrulama ve yerel şablon aracı.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prompt_parser = subparsers.add_parser("prompt", help="Model ailesine göre prompt üret.")
    prompt_parser.add_argument("--model", default="", help="Model adı; örneğin gpt-4.1, kimi veya claude.")
    prompt_parser.add_argument("request", help="Kullanıcının modelleme isteği.")

    validate_parser = subparsers.add_parser("validate", help="VBA dosyasını doğrula.")
    validate_parser.add_argument("file", help="VBA dosya yolu.")

    template_parser = subparsers.add_parser("template", help="Anahtar sözcüklerle yerel şablon seç.")
    template_parser.add_argument("request", help="Kullanıcının modelleme isteği.")
    template_parser.add_argument("--output", help="Çıktı dosyasını yaz.")
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = _parse_args()
    if args.command == "prompt":
        print(build_prompt(args.request, model_name=args.model))
        return 0

    if args.command == "validate":
        code = Path(args.file).read_text(encoding="utf-8")
        result = validate_vba_macro(code)
        print(json.dumps({"ok": result.ok, "issues": result.issues}, ensure_ascii=False, indent=2))
        return 0 if result.ok else 1

    if args.command == "template":
        code = fallback_macro_for_request(args.request)
        if not code:
            print("Yerel şablon eşleşmedi.")
            return 1
        if args.output:
            path = write_macro_file(code, args.output)
            print(path)
        else:
            print(code)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
