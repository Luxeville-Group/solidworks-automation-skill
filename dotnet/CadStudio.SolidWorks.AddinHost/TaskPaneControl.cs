using System;
using System.Drawing;
using System.Windows.Forms;

namespace CadStudio.SolidWorks.AddinHost
{
    /// <summary>Display Add-in health with diagnostic/PMP shortcuts.</summary>
    internal sealed class TaskPaneControl : UserControl
    {
        private readonly Label stateLabel;

        /// <summary>Create the TaskPane control.</summary>
        internal TaskPaneControl(string revision, string diagnosticPath, Action showPropertyPage, Action refreshDiagnostics)
        {
            Dock = DockStyle.Fill;
            BackColor = Color.White;
            Padding = new Padding(12);

            var title = new Label
            {
                AutoSize = true,
                Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 12f, FontStyle.Bold),
                Text = "CAD Studio Add-in Host",
                Location = new Point(12, 14),
            };
            stateLabel = new Label
            {
                AutoSize = false,
                Size = new Size(280, 72),
                Location = new Point(12, 48),
                Text = "Durum: Bağlandı\r\nSOLIDWORKS: " + revision + "\r\nTanılama: " + diagnosticPath,
            };
            var propertyButton = new Button
            {
                Text = "PropertyManagerPage aç",
                Size = new Size(220, 32),
                Location = new Point(12, 130),
            };
            var refreshButton = new Button
            {
                Text = "Tanılama kanıtını yenile",
                Size = new Size(220, 32),
                Location = new Point(12, 170),
            };
            propertyButton.Click += delegate { showPropertyPage(); };
            refreshButton.Click += delegate
            {
                refreshDiagnostics();
                stateLabel.Text = "Durum: Tanılama yenilendi\r\nSOLIDWORKS: " + revision + "\r\nTanılama: " + diagnosticPath;
            };

            Controls.Add(title);
            Controls.Add(stateLabel);
            Controls.Add(propertyButton);
            Controls.Add(refreshButton);
        }
    }
}
