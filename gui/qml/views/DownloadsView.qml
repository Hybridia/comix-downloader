import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: downloadsView
    
    // Theme colors (referencing root if possible, or re-defining for safety)
    readonly property color bgCard: Theme.card
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color accentPrimary: Theme.accent

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20
        
        // HEADER
        RowLayout {
            Layout.fillWidth: true
            
            ColumnLayout {
                spacing: 4
                Text {
                    text: "DOWNLOADS MANAGER"
                    font.family: "Segoe UI"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    color: textPrimary
                }
                Text {
                    text: "Monitor and manage your active download tasks"
                    font.pixelSize: 13
                    color: textSecondary
                }
            }
            
            Item { Layout.fillWidth: true }
            
            // CLEAR HISTORY BUTTON. Enabled as soon as ANY job is
            // finished so a completed download can be dismissed
            // without waiting for parallel ones to finish first.
            Button {
                text: "Clear Finished"
                onClicked: progressPanel.reset()
                enabled: progressPanel.hasFinishedJob
            }
        }
        
        // PROGRESS PANEL (Full Screen Version)
        ProgressPanel {
            id: progressPanel
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            // Make internal scrollview larger in this view
            visible: true
        }
    }
    
    // Expose internal progress panel for main.qml connections
    function getProgressPanel() { return progressPanel }
}
