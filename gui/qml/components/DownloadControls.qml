import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    
    property var scanlators: ["Any"]
    property string scanlatorPreference: "Any"
    property string scanlatorFilter: "Any"

    signal downloadClicked()
    signal filterChanged(string filter)
    
    // Theme colors
    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color accentGradientEnd: Theme.accent2
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color bgDeep: Theme.bg
    
    color: bgCard
    radius: 12
    
    RowLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 16

        // SCANLATOR PREFERENCE (for download priority)
        ColumnLayout {
            spacing: 4
            Text { text: "Scanlator Preference"; font.pixelSize: 11; color: textTertiary }
            ComboBox {
                id: preferenceCombo
                model: root.scanlators
                implicitWidth: 150; implicitHeight: 36
                onCurrentTextChanged: root.scanlatorPreference = currentText
                
                background: Rectangle { color: bgElevated; radius: 6; border.color: textTertiary; border.width: 1 }
                contentItem: Text { 
                    text: preferenceCombo.currentText
                    font.pixelSize: 13
                    color: textPrimary
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 10
                    elide: Text.ElideRight 
                }
            }
        }
        
        // SCANLATOR FILTER (for filtering chapter list)
        ColumnLayout {
            spacing: 4
            Text { text: "Scanlator Filter"; font.pixelSize: 11; color: textTertiary }
            ComboBox {
                id: filterCombo
                model: root.scanlators
                implicitWidth: 150; implicitHeight: 36
                onCurrentTextChanged: {
                    root.scanlatorFilter = currentText
                    root.filterChanged(currentText)
                }
                
                background: Rectangle { color: bgElevated; radius: 6; border.color: accentPrimary; border.width: 1 }
                contentItem: Text { 
                    text: filterCombo.currentText
                    font.pixelSize: 13
                    color: accentPrimary
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 10
                    elide: Text.ElideRight 
                }
            }
        }
        
        Item { Layout.fillWidth: true }
        
        // DOWNLOAD BUTTON
        Rectangle {
            Layout.preferredWidth: 200
            Layout.preferredHeight: 48
            radius: 12
            
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: accentPrimary }
                GradientStop { position: 1.0; color: accentGradientEnd }
            }
            
            scale: downloadArea.pressed ? 0.97 : (downloadArea.containsMouse ? 1.02 : 1.0)
            Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
            
            RowLayout {
                anchors.centerIn: parent
                spacing: 8
                Text { text: "▶"; font.pixelSize: 14; color: bgDeep }
                Text { text: "DOWNLOAD"; font.family: "Segoe UI"; font.pixelSize: 13; font.weight: Font.Bold; color: bgDeep; font.letterSpacing: 1 }
            }
            
            MouseArea {
                id: downloadArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.downloadClicked()
            }
        }
    }
}
