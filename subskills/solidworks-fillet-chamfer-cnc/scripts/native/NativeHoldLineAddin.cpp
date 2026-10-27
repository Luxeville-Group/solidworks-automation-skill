/**
 * @file NativeHoldLineAddin.cpp
 * @brief SolidWorks in-process unmanaged C++ hold-line write bridge.
 *
 * @details Official ISetHoldLines supports only in-process unmanaged C++. SWBasic prepares
 * face sets and hold lines on the main thread. This DLL retains objects until the next UI message loop, calls
 * ISetHoldLines once and writes structured evidence. SWBasic creates, names and rebuilds the feature.
 */

#include <Windows.h>
#include <OleAuto.h>

#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>

#import "sldworks.tlb" raw_interfaces_only, raw_native_types, named_guids, \
    rename_namespace("SldWorksNative"), rename("GetOpenFileName", "SWGetOpenFileName")

namespace
{
SldWorksNative::ISimpleFilletFeatureData2* g_prepared_data = nullptr;
IDispatch* g_prepared_hold_line = nullptr;
long g_job_scheduled = 0;

/** @brief Throw a narrow-character exception with HRESULT on failure. */
void Check(HRESULT result, const char* operation)
{
    if (SUCCEEDED(result)) return;
    std::ostringstream message;
    message << operation << " failed: 0x" << std::hex << std::uppercase
            << static_cast<unsigned long>(result);
    throw std::runtime_error(message.str());
}

/** @brief Convert UTF-8 text to UTF-16. */
std::wstring Wide(const std::string& value)
{
    if (value.empty()) return std::wstring();
    const int length = MultiByteToWideChar(
        CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), nullptr, 0);
    if (length <= 0) throw std::runtime_error("UTF-8 path conversion failed");
    std::wstring result(static_cast<size_t>(length), L'\0');
    MultiByteToWideChar(
        CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()),
        &result[0], length);
    return result;
}

/** @brief Return the one-shot job path shared by the orchestrator and SolidWorks process. */
std::wstring JobFilePath()
{
    wchar_t temporary[MAX_PATH] = {};
    const DWORD length = GetTempPathW(MAX_PATH, temporary);
    if (length == 0 || length >= MAX_PATH)
        throw std::runtime_error("temporary path unavailable");
    return std::wstring(temporary) + L"cad-studio-hold-line-job.txt";
}

/** @brief Read the result path from a UTF-8 job file. */
std::wstring ReadResultPath()
{
    const std::wstring path = JobFilePath();
    HANDLE file = CreateFileW(
        path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE)
        throw std::runtime_error("hold-line job file unavailable");
    LARGE_INTEGER size = {};
    if (!GetFileSizeEx(file, &size) || size.QuadPart <= 0 || size.QuadPart > 65536)
    {
        CloseHandle(file);
        throw std::runtime_error("hold-line job file size invalid");
    }
    std::string content(static_cast<size_t>(size.QuadPart), '\0');
    DWORD read = 0;
    const BOOL read_ok = ReadFile(
        file, &content[0], static_cast<DWORD>(content.size()), &read, nullptr);
    CloseHandle(file);
    if (!read_ok || read != content.size())
        throw std::runtime_error("hold-line job file read failed");
    const size_t newline = content.find_first_of("\r\n");
    const std::string result_path = content.substr(0, newline);
    if (result_path.empty())
        throw std::runtime_error("hold-line result path missing");
    return Wide(result_path);
}

/** @brief Safely escape control characters and quotes in JSON strings. */
std::string JsonString(const std::string& value)
{
    std::ostringstream escaped;
    escaped << '"';
    for (const unsigned char character : value)
    {
        switch (character)
        {
        case '\\': escaped << "\\\\"; break;
        case '"': escaped << "\\\""; break;
        case '\n': escaped << "\\n"; break;
        case '\r': escaped << "\\r"; break;
        case '\t': escaped << "\\t"; break;
        default:
            if (character < 0x20)
            {
                escaped << "\\u" << std::hex << std::setw(4)
                        << std::setfill('0') << static_cast<int>(character);
            }
            else
            {
                escaped << static_cast<char>(character);
            }
        }
    }
    escaped << '"';
    return escaped.str();
}

/** @brief Write the UTF-8 JSON result by replacement. */
void WriteResult(const std::wstring& path, const std::string& json)
{
    HANDLE file = CreateFileW(
        path.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    WriteFile(file, json.data(), static_cast<DWORD>(json.size()), &written, nullptr);
    FlushFileBuffers(file);
    CloseHandle(file);
}

/** @brief Release deferred-call COM references and reset the single-task gate. */
void ReleasePreparedObjects()
{
    if (g_prepared_hold_line != nullptr)
    {
        g_prepared_hold_line->Release();
        g_prepared_hold_line = nullptr;
    }
    if (g_prepared_data != nullptr)
    {
        g_prepared_data->Release();
        g_prepared_data = nullptr;
    }
    InterlockedExchange(&g_job_scheduled, 0);
}

/** @brief Execute one native ISetHoldLines call in the SolidWorks UI message loop. */
VOID CALLBACK PreparedHoldLineTimerProc(HWND, UINT, UINT_PTR timer_id, DWORD)
{
    KillTimer(nullptr, timer_id);
    std::wstring result_path;
    try
    {
        result_path = ReadResultPath();
        if (g_prepared_data == nullptr || g_prepared_hold_line == nullptr)
            throw std::runtime_error("prepared COM objects missing");
        IDispatch* hold_lines[1] = {g_prepared_hold_line};
        Check(
            g_prepared_data->ISetHoldLines(1, hold_lines),
            "ISimpleFilletFeatureData2::ISetHoldLines");
        long hold_line_count = 0;
        Check(
            g_prepared_data->GetHoldLineCount(&hold_line_count),
            "ISimpleFilletFeatureData2::GetHoldLineCount");
        if (hold_line_count != 1)
            throw std::runtime_error("hold-line count did not persist as one");
        WriteResult(
            result_path,
            "{\"status\":\"stage\",\"stage\":\"hold-lines-set\","
            "\"backend\":\"native-cpp-swb\",\"holdLineCount\":1}");
    }
    catch (const std::exception& exception)
    {
        if (!result_path.empty())
        {
            WriteResult(
                result_path,
                "{\"status\":\"blocked\",\"backend\":\"native-cpp-swb\","
                "\"error\":" + JsonString(exception.what()) + "}");
        }
    }
    ReleasePreparedObjects();
}
}  // namespace

/**
 * @brief Schedule an in-process ISetHoldLines call.
 * @param application_unknown Current SolidWorks application object for validating caller context.
 * @param feature_data_unknown FeatureData with Initialize(2) and two populated face sets.
 * @param hold_line_unknown Hold-line edge corresponding to selection mark 8.
 * @return 0 means scheduled; the callback writes the actual result to JSON.
 */
extern "C" __declspec(dllexport) int __stdcall RunPreparedHoldLine(
    IUnknown* application_unknown,
    IUnknown* feature_data_unknown,
    IUnknown* hold_line_unknown)
{
    std::wstring result_path;
    try
    {
        result_path = ReadResultPath();
        if (application_unknown == nullptr || feature_data_unknown == nullptr
            || hold_line_unknown == nullptr)
            throw std::runtime_error("SWBasic did not supply complete COM pointers");
        if (InterlockedCompareExchange(&g_job_scheduled, 1, 0) != 0)
            throw std::runtime_error("another hold-line probe is still scheduled");

        Check(
            feature_data_unknown->QueryInterface(
                __uuidof(SldWorksNative::ISimpleFilletFeatureData2),
                reinterpret_cast<void**>(&g_prepared_data)),
            "QueryInterface(ISimpleFilletFeatureData2)");
        Check(
            hold_line_unknown->QueryInterface(
                IID_IDispatch,
                reinterpret_cast<void**>(&g_prepared_hold_line)),
            "QueryInterface(hold line IDispatch)");
        if (SetTimer(nullptr, 0, 1, PreparedHoldLineTimerProc) == 0)
            throw std::runtime_error("unable to schedule SolidWorks UI callback");
        return 0;
    }
    catch (const std::exception& exception)
    {
        ReleasePreparedObjects();
        if (!result_path.empty())
        {
            WriteResult(
                result_path,
                "{\"status\":\"blocked\",\"backend\":\"native-cpp-swb\","
                "\"error\":" + JsonString(exception.what()) + "}");
        }
        return 1;
    }
}
