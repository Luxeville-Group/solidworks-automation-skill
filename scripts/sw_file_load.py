"""@brief File-load diagnostics using SW2026 official enums; interpret errors and warnings separately."""

SW_FILE_LOAD_ERRORS = {1: 'swGenericError', 2: 'swFileNotFoundError', 4: 'swIdMatchError', 8: 'swReadOnlyWarn', 16: 'swSharingViolationWarn', 32: 'swDrawingANSIUpdateWarn', 64: 'swSheetScaleUpdateWarn', 128: 'swNeedsRegenWarn', 256: 'swBasePartNotLoadedWarn', 512: 'swFileAlreadyOpenWarn', 1024: 'swInvalidFileTypeError', 2048: 'swDrawingsOnlyRapidDraftWarn', 4096: 'swViewOnlyRestrictions', 8192: 'swFutureVersion', 16384: 'swViewMissingReferencedConfig', 32768: 'swDrawingSFSymbolConvertWarn', 65536: 'swFileWithSameTitleAlreadyOpen', 131072: 'swLiquidMachineDoc', 262144: 'swLowResourcesError', 524288: 'swNoDisplayData', 1048576: 'swAddinInteruptError', 2097152: 'swFileRequiresRepairError', 4194304: 'swFileCriticalDataRepairError', 8388608: 'swApplicationBusy', 16777216: 'swConnectedIsOffline'}
SW_FILE_LOAD_WARNINGS = {1: 'swFileLoadWarning_IdMismatch', 2: 'swFileLoadWarning_ReadOnly', 4: 'swFileLoadWarning_SharingViolation', 8: 'swFileLoadWarning_DrawingANSIUpdate', 16: 'swFileLoadWarning_SheetScaleUpdate', 32: 'swFileLoadWarning_NeedsRegen', 64: 'swFileLoadWarning_BasePartNotLoaded', 128: 'swFileLoadWarning_AlreadyOpen', 256: 'swFileLoadWarning_DrawingsOnlyRapidDraft', 512: 'swFileLoadWarning_ViewOnlyRestrictions', 1024: 'swFileLoadWarning_ViewMissingReferencedConfig', 2048: 'swFileLoadWarning_DrawingSFSymbolConvert', 4096: 'swFileLoadWarning_RevolveDimTolerance', 8192: 'swFileLoadWarning_ModelOutOfDate', 16384: 'swFileLoadWarning_DimensionsReferencedIncorrectlyToModels', 32768: 'swFileLoadWarning_ComponentMissingReferencedConfig', 65536: 'swFileLoadWarning_InvisibleDoc_LinkedDesignTableUpdateFail', 131072: 'swFileLoadWarning_MissingDesignTable', 262144: 'swFileLoadWarning_AutomaticRepair', 524288: 'swFileLoadWarning_CriticalDataRepair', 1048576: 'swFileLoadWarning_MissingExternalReferences'}

def _describe(code, names):
    """@brief Preserve unknown bit flags; never interpret warning bits with the error enum."""
    value = int(code or 0)
    if value < 0:
        return f"Bilinmeyen değer({value})"
    remaining = value
    parts = []
    for bit, name in sorted(names.items()):
        if value & bit:
            parts.append(name)
            remaining &= ~bit
    if remaining:
        parts.append(f"Bilinmeyen bit(0x{remaining:X})")
    return " | ".join(parts) if parts else "Yok"

def classify_sw_file_load_errors(code):
    """@brief Interpret errors using swFileLoadError_e."""
    return _describe(code, SW_FILE_LOAD_ERRORS)

def classify_sw_file_load_warnings(code):
    """@brief Interpret warnings using swFileLoadWarning_e."""
    return _describe(code, SW_FILE_LOAD_WARNINGS)

class SolidWorksDocumentOpenError(RuntimeError):
    """@brief Preserve raw flags and provide stable machine error codes to Core/MCP."""
    def __init__(self, message, error_code=0, warnings=0):
        self.error_code = int(error_code or 0)
        self.warnings = int(warnings or 0)
        bits = self.error_code
        self.code = "SW_FILE_LOAD_FAILED"
        for mask, name in ((2, "SW_FILE_NOT_FOUND"), (2097152 | 4194304, "SW_FILE_REQUIRES_REPAIR"), (8192, "SW_FILE_FUTURE_VERSION"), (262144, "SW_LOW_RESOURCES"), (8388608, "SW_FILE_APPLICATION_BUSY")):
            if bits & mask:
                self.code = name
                break
        super().__init__(message)
