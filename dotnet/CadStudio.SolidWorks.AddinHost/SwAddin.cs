using System;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
using SolidWorks.Interop.swpublished;

namespace CadStudio.SolidWorks.AddinHost
{
    /// <summary>General SOLIDWORKS in-process Add-in host for CAD Studio.</summary>
    [ComVisible(true)]
    [Guid(AddinGuid)]
    [ProgId("CadStudio.SolidWorks.AddinHost")]
    public sealed class SwAddin : ISwAddin
    {
        public const string AddinGuid = "8EE76E8D-9B47-4DE0-AFA2-B2E36621A134";
        private const int CommandGroupId = 55001;
        private const int PropertyPageLabelId = 100;
        private const int PropertyPageTextId = 101;
        private const int PropertyPageButtonId = 102;

        private readonly HostDiagnostics diagnostics = new HostDiagnostics();
        private ISldWorks swApp;
        private SldWorks applicationEvents;
        private ICommandManager commandManager;
        private ICommandGroup commandGroup;
        private ITaskpaneView taskPane;
        private TaskPaneControl taskPaneControl;
        private IPropertyManagerPage2 propertyPage;
        private PropertyPageHandler propertyPageHandler;
        private int addinCookie;
        private bool commandGroupReady;
        private bool taskPaneReady;
        private bool propertyManagerPageReady;

        /// <summary>Initialize the host and record actual COM class instantiation.</summary>
        public SwAddin()
        {
            diagnostics.RecordEvent("constructed");
        }

        /// <summary>Register the COM class and SOLIDWORKS Add-ins metadata.</summary>
        [ComRegisterFunction]
        public static void Register(Type type)
        {
            string guid = "{" + AddinGuid + "}";
            using (RegistryKey addin = Registry.LocalMachine.CreateSubKey(@"SOFTWARE\SOLIDWORKS\Addins\" + guid))
            {
                addin.SetValue(null, 0, RegistryValueKind.DWord);
                addin.SetValue("Title", "CAD Studio Add-in Host", RegistryValueKind.String);
                addin.SetValue("Description", "Events, PropertyManagerPage, TaskPane ve tanılama Host", RegistryValueKind.String);
            }
            using (RegistryKey startup = Registry.CurrentUser.CreateSubKey(@"Software\SOLIDWORKS\AddInsStartup\" + guid))
            {
                startup.SetValue(null, 1, RegistryValueKind.DWord);
            }
        }

        /// <summary>Remove Add-in registration entries.</summary>
        [ComUnregisterFunction]
        public static void Unregister(Type type)
        {
            string guid = "{" + AddinGuid + "}";
            Registry.LocalMachine.DeleteSubKeyTree(@"SOFTWARE\SOLIDWORKS\Addins\" + guid, false);
            Registry.CurrentUser.DeleteSubKeyTree(@"Software\SOLIDWORKS\AddInsStartup\" + guid, false);
        }

        /// <summary>Called by SOLIDWORKS to create callbacks, menus, TaskPane, and event subscriptions.</summary>
        public bool ConnectToSW(object thisSw, int cookie)
        {
            try
            {
                swApp = (ISldWorks)thisSw;
                addinCookie = cookie;
                bool callbackReady = swApp.SetAddinCallbackInfo2(0, this, addinCookie);
                diagnostics.MarkConnection(swApp.RevisionNumber(), callbackReady);
                if (!callbackReady)
                {
                    throw new InvalidOperationException("SetAddinCallbackInfo2 geçerli callback kaydetmedi.");
                }
                diagnostics.RecordEvent("callback_ready");
                AttachApplicationEvents();
                diagnostics.RecordEvent("application_events_ready");
                commandGroupReady = CreateCommandGroup();
                if (!commandGroupReady)
                {
                    throw new InvalidOperationException("CommandGroup etkinleştirilemedi.");
                }
                diagnostics.RecordEvent("command_group_ready");
                taskPaneReady = CreateTaskPane();
                if (!taskPaneReady)
                {
                    throw new InvalidOperationException("TaskPane oluşturulamadı veya gösterilemedi.");
                }
                diagnostics.RecordEvent("task_pane_ready");
                propertyManagerPageReady = CreatePropertyManagerPage();
                diagnostics.MarkUi(commandGroupReady, taskPaneReady, propertyManagerPageReady);
                return callbackReady && commandGroupReady && taskPaneReady;
            }
            catch (Exception exception)
            {
                ReleaseHostResources();
                diagnostics.MarkDisconnected();
                diagnostics.RecordError("connect", exception);
                return false;
            }
        }

        /// <summary>Called by SOLIDWORKS to unsubscribe and release all host resources.</summary>
        public bool DisconnectFromSW()
        {
            bool released = ReleaseHostResources();
            diagnostics.MarkDisconnected();
            GC.Collect();
            GC.WaitForPendingFinalizers();
            return released;
        }

        /// <summary>CommandManager callback: display PropertyManagerPage.</summary>
        public void ShowPropertyPage()
        {
            try
            {
                if (propertyPage == null && !CreatePropertyManagerPage())
                {
                    throw new InvalidOperationException("PropertyManagerPage oluşturulamadı.");
                }
                propertyManagerPageReady = true;
                diagnostics.MarkUi(commandGroupReady, taskPaneReady, propertyManagerPageReady);
                propertyPage.Show2(0);
                diagnostics.RecordEvent("property_page_show");
            }
            catch (Exception exception)
            {
                diagnostics.RecordError("property_page_show", exception);
            }
        }

        /// <summary>CommandManager callback: display TaskPane.</summary>
        public void ShowTaskPane()
        {
            try
            {
                taskPane?.ShowView();
                diagnostics.RecordEvent("task_pane_show");
            }
            catch (Exception exception)
            {
                diagnostics.RecordError("task_pane_show", exception);
            }
        }

        /// <summary>CommandManager callback: refresh diagnostic evidence.</summary>
        public void RefreshDiagnostics()
        {
            diagnostics.Flush();
        }

        /// <summary>CommandManager enable callback.</summary>
        public int EnableCommand()
        {
            return swApp == null ? 0 : 1;
        }

        /// <summary>Create and activate the menu/toolbar command group.</summary>
        private bool CreateCommandGroup()
        {
            commandManager = swApp.GetCommandManager(addinCookie);
            int errors = 0;
            commandGroup = commandManager.CreateCommandGroup2(
                CommandGroupId,
                "CAD Studio",
                "CAD Studio Add-in Host",
                "CAD Studio",
                -1,
                true,
                ref errors);
            if (commandGroup == null || errors != (int)swCreateCommandGroupErrors.swCreateCommandGroup_Success)
            {
                throw new InvalidOperationException("CreateCommandGroup2 başarısız; hata kodu: " + errors);
            }

            commandGroup.MainIconList = CreateMainIcons();
            commandGroup.IconList = CreateCommandIconStrips();
            commandGroup.HasMenu = true;
            commandGroup.HasToolbar = true;
            int itemType = (int)swCommandItemType_e.swMenuItem | (int)swCommandItemType_e.swToolbarItem;
            commandGroup.AddCommandItem2("Parametre sayfasını aç", -1, "Genel PropertyManagerPage göster", "Parametre sayfasını aç", 0, nameof(ShowPropertyPage), nameof(EnableCommand), 1, itemType);
            commandGroup.AddCommandItem2("TaskPane göster", -1, "CAD Studio TaskPane göster", "TaskPane göster", 1, nameof(ShowTaskPane), nameof(EnableCommand), 2, itemType);
            commandGroup.AddCommandItem2("Tanılamayı yenile", -1, "Add-in tanılama kanıtını yenile", "Tanılamayı yenile", 2, nameof(RefreshDiagnostics), nameof(EnableCommand), 3, itemType);
            return commandGroup.Activate();
        }

        /// <summary>Create command icon lists supporting high DPI.</summary>
        private string[] CreateMainIcons()
        {
            int[] sizes = { 20, 32, 40, 64, 96, 128 };
            string[] paths = new string[sizes.Length];
            for (int index = 0; index < sizes.Length; index++)
            {
                paths[index] = CreateIconFile("main-" + sizes[index] + ".png", sizes[index], 1);
            }
            return paths;
        }

        /// <summary>Create a horizontal three-command icon strip for each DPI size.</summary>
        private string[] CreateCommandIconStrips()
        {
            int[] sizes = { 20, 32, 40, 64, 96, 128 };
            string[] paths = new string[sizes.Length];
            for (int index = 0; index < sizes.Length; index++)
            {
                paths[index] = CreateIconFile("commands-" + sizes[index] + ".png", sizes[index], 3);
            }
            return paths;
        }

        /// <summary>Create TaskPane and host the WinForms control handle.</summary>
        private bool CreateTaskPane()
        {
            string icon = CreateIconFile("taskpane.bmp", 20, 1);
            taskPane = swApp.CreateTaskpaneView2(icon, "CAD Studio");
            if (taskPane == null)
            {
                return false;
            }
            taskPaneControl = new TaskPaneControl(swApp.RevisionNumber(), diagnostics.DiagnosticPath, ShowPropertyPage, RefreshDiagnostics);
            taskPaneControl.CreateControl();
            bool displayed = taskPane.DisplayWindowFromHandlex64(taskPaneControl.Handle.ToInt64());
            return displayed && taskPane.ShowView();
        }

        /// <summary>Create a general PropertyManagerPage with label, text box, and button.</summary>
        private bool CreatePropertyManagerPage()
        {
            propertyPageHandler = new PropertyPageHandler(diagnostics.RecordEvent);
            int options = (int)swPropertyManagerPageOptions_e.swPropertyManagerOptions_OkayButton
                | (int)swPropertyManagerPageOptions_e.swPropertyManagerOptions_CancelButton
                | (int)swPropertyManagerPageOptions_e.swPropertyManagerOptions_PushpinButton;
            int errors = 0;
            propertyPage = swApp.ICreatePropertyManagerPage("CAD Studio Add-in Host", options, propertyPageHandler, ref errors);
            if (propertyPage == null || errors != 0)
            {
                return false;
            }
            int controlOptions = (int)swAddControlOptions_e.swControlOptions_Visible
                | (int)swAddControlOptions_e.swControlOptions_Enabled;
            var label = (IPropertyManagerPageLabel)propertyPage.AddControl2(
                PropertyPageLabelId,
                (short)swPropertyManagerPageControlType_e.swControlType_Label,
                "Host durumu",
                (short)swPropertyManagerPageControlLeftAlign_e.swControlAlign_LeftEdge,
                controlOptions,
                "Mevcut Add-in bağlantı durumunu göster");
            label.Caption = "Bağlandı; Events, TaskPane ve tanılama kaydedici kullanılabilir.";
            var textbox = (IPropertyManagerPageTextbox)propertyPage.AddControl2(
                PropertyPageTextId,
                (short)swPropertyManagerPageControlType_e.swControlType_Textbox,
                "Extension payload",
                (short)swPropertyManagerPageControlLeftAlign_e.swControlAlign_LeftEdge,
                controlOptions,
                "Sonraki denetimli extension için kısa metin parametresi");
            textbox.Text = "ready";
            var button = (IPropertyManagerPageButton)propertyPage.AddControl2(
                PropertyPageButtonId,
                (short)swPropertyManagerPageControlType_e.swControlType_Button,
                "Tanılama olayını kaydet",
                (short)swPropertyManagerPageControlLeftAlign_e.swControlAlign_LeftEdge,
                controlOptions,
                "PMP callback zincirini doğrula");
            button.Caption = "Tanılama olayını kaydet";
            return true;
        }

        /// <summary>Subscribe to necessary low-frequency SOLIDWORKS application events.</summary>
        private void AttachApplicationEvents()
        {
            applicationEvents = (SldWorks)swApp;
            applicationEvents.ActiveModelDocChangeNotify += OnActiveModelDocChange;
            applicationEvents.FileOpenPostNotify += OnFileOpenPost;
            applicationEvents.FileNewNotify2 += OnFileNew;
            applicationEvents.FileCloseNotify += OnFileClose;
        }

        /// <summary>Unsubscribe from application events.</summary>
        private void DetachApplicationEvents()
        {
            if (applicationEvents == null)
            {
                return;
            }
            applicationEvents.ActiveModelDocChangeNotify -= OnActiveModelDocChange;
            applicationEvents.FileOpenPostNotify -= OnFileOpenPost;
            applicationEvents.FileNewNotify2 -= OnFileNew;
            applicationEvents.FileCloseNotify -= OnFileClose;
            applicationEvents = null;
        }

        /// <summary>Release resources individually; continue cleanup after an individual failure.</summary>
        private bool ReleaseHostResources()
        {
            bool success = true;
            success &= TryRelease("detach_events", DetachApplicationEvents);
            success &= TryRelease("close_property_page", delegate
            {
                if (propertyPage != null) { propertyPage.Close(true); }
            });
            success &= TryRelease("delete_task_pane", delegate
            {
                if (taskPane != null) { taskPane.DeleteView(); }
            });
            success &= TryRelease("dispose_task_pane_control", delegate
            {
                if (taskPaneControl != null) { taskPaneControl.Dispose(); }
            });
            success &= TryRelease("remove_command_group", delegate
            {
                if (commandManager != null) { commandManager.RemoveCommandGroup2(CommandGroupId, true); }
            });
            propertyPage = null;
            propertyPageHandler = null;
            taskPane = null;
            taskPaneControl = null;
            commandGroup = null;
            commandManager = null;
            swApp = null;
            commandGroupReady = false;
            taskPaneReady = false;
            propertyManagerPageReady = false;
            return success;
        }

        /// <summary>Perform one release action and record exceptions.</summary>
        private bool TryRelease(string area, Action release)
        {
            try
            {
                release();
                return true;
            }
            catch (Exception exception)
            {
                diagnostics.RecordError(area, exception);
                return false;
            }
        }

        private int OnActiveModelDocChange() { diagnostics.RecordEvent("active_model_doc_change"); return 0; }
        private int OnFileOpenPost(string fileName) { diagnostics.RecordEvent("file_open_post"); return 0; }
        private int OnFileNew(object newDocument, int documentType, string templateName)
        {
            diagnostics.RecordEvent("file_new");
            if (propertyPage == null)
            {
                propertyManagerPageReady = CreatePropertyManagerPage();
                diagnostics.MarkUi(commandGroupReady, taskPaneReady, propertyManagerPageReady);
            }
            return 0;
        }
        private int OnFileClose(string fileName, int reason) { diagnostics.RecordEvent("file_close"); return 0; }

        /// <summary>Create runtime icons by name to avoid extra deployed binary resources.</summary>
        private string CreateIconFile(string fileName, int size, int glyphCount)
        {
            string path = Path.Combine(diagnostics.DiagnosticDirectory, fileName);
            Directory.CreateDirectory(diagnostics.DiagnosticDirectory);
            if (File.Exists(path))
            {
                return path;
            }
            using (var bitmap = new Bitmap(size * glyphCount, size))
            using (Graphics graphics = Graphics.FromImage(bitmap))
            using (var brush = new SolidBrush(Color.FromArgb(27, 89, 163)))
            using (var textBrush = new SolidBrush(Color.White))
            using (var font = new Font(FontFamily.GenericSansSerif, Math.Max(7f, size * 0.36f), FontStyle.Bold, GraphicsUnit.Pixel))
            {
                graphics.Clear(Color.Transparent);
                string[] glyphs = { "P", "T", "D" };
                for (int index = 0; index < glyphCount; index++)
                {
                    graphics.FillRectangle(brush, index * size, 0, size, size);
                    graphics.DrawString(glyphs[index], font, textBrush, new PointF(index * size + size * 0.16f, size * 0.1f));
                }
                if (Path.GetExtension(path).Equals(".bmp", StringComparison.OrdinalIgnoreCase))
                {
                    bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Bmp);
                }
                else
                {
                    bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png);
                }
            }
            return path;
        }
    }
}
