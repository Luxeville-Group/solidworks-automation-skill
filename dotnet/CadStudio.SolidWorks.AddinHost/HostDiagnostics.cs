using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;

namespace CadStudio.SolidWorks.AddinHost
{
    /// <summary>Maintain machine-readable Add-in lifecycle, UI, and event diagnostics.</summary>
    internal sealed class HostDiagnostics
    {
        private readonly object syncRoot = new object();
        private readonly JavaScriptSerializer serializer = new JavaScriptSerializer();
        private readonly Dictionary<string, int> eventCounts = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly List<string> errors = new List<string>();
        private DateTime connectedAtUtc;
        private string solidWorksRevision = string.Empty;
        private bool connected;
        private bool callbackRegistered;
        private bool commandGroupReady;
        private bool taskPaneReady;
        private bool propertyManagerPageReady;

        /// <summary>Initialize the diagnostic file location.</summary>
        internal HostDiagnostics()
        {
            string root = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            DiagnosticDirectory = Path.Combine(root, "CAD Studio", "SolidWorksAddin");
            DiagnosticPath = Path.Combine(DiagnosticDirectory, "host-status.json");
        }

        /// <summary>Diagnostic directory.</summary>
        internal string DiagnosticDirectory { get; }

        /// <summary>Diagnostic JSON path.</summary>
        internal string DiagnosticPath { get; }

        /// <summary>Record successful connection and host version.</summary>
        internal void MarkConnection(string revision, bool callbackReady)
        {
            lock (syncRoot)
            {
                connectedAtUtc = DateTime.UtcNow;
                solidWorksRevision = revision ?? string.Empty;
                connected = callbackReady;
                callbackRegistered = callbackReady;
                WriteUnsafe();
            }
        }

        /// <summary>Record UI subsystem state.</summary>
        internal void MarkUi(bool commandReady, bool taskPane, bool propertyPage)
        {
            lock (syncRoot)
            {
                commandGroupReady = commandReady;
                taskPaneReady = taskPane;
                propertyManagerPageReady = propertyPage;
                WriteUnsafe();
            }
        }

        /// <summary>Increment the specified application event count.</summary>
        internal void RecordEvent(string name)
        {
            lock (syncRoot)
            {
                int current;
                eventCounts.TryGetValue(name, out current);
                eventCounts[name] = current + 1;
                WriteUnsafe();
            }
        }

        /// <summary>Record nonfatal errors with bounded history.</summary>
        internal void RecordError(string area, Exception exception)
        {
            lock (syncRoot)
            {
                errors.Add(string.Format("{0:o} [{1}] {2}", DateTime.UtcNow, area, exception));
                if (errors.Count > 20)
                {
                    errors.RemoveAt(0);
                }
                WriteUnsafe();
            }
        }

        /// <summary>Refresh the current evidence file.</summary>
        internal void Flush()
        {
            lock (syncRoot)
            {
                WriteUnsafe();
            }
        }

        /// <summary>Record unload state.</summary>
        internal void MarkDisconnected()
        {
            lock (syncRoot)
            {
                connected = false;
                callbackRegistered = false;
                commandGroupReady = false;
                taskPaneReady = false;
                propertyManagerPageReady = false;
                WriteUnsafe();
            }
        }

        /// <summary>Atomically replace diagnostic JSON while holding the lock.</summary>
        private void WriteUnsafe()
        {
            Directory.CreateDirectory(DiagnosticDirectory);
            var payload = new Dictionary<string, object>
            {
                ["schemaVersion"] = "1.0",
                ["addinGuid"] = SwAddin.AddinGuid,
                ["status"] = connected ? "connected" : "disconnected",
                ["connectedAtUtc"] = connectedAtUtc == default(DateTime) ? null : connectedAtUtc.ToString("o"),
                ["lastUpdatedUtc"] = DateTime.UtcNow.ToString("o"),
                ["solidWorksRevision"] = solidWorksRevision,
                ["hostProcessId"] = Process.GetCurrentProcess().Id,
                ["hostProcessName"] = Process.GetCurrentProcess().ProcessName,
                ["callbackRegistered"] = callbackRegistered,
                ["commandGroupReady"] = commandGroupReady,
                ["taskPaneReady"] = taskPaneReady,
                ["propertyManagerPageReady"] = propertyManagerPageReady,
                ["eventCounts"] = new Dictionary<string, int>(eventCounts),
                ["errors"] = errors.ToArray(),
            };
            string json = serializer.Serialize(payload);
            string temporary = DiagnosticPath + ".tmp";
            File.WriteAllText(temporary, json, new UTF8Encoding(false));
            File.Copy(temporary, DiagnosticPath, true);
            File.Delete(temporary);
        }
    }
}
