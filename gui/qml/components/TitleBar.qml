import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    
    // Theme colors (inline)
    readonly property color bgDeep: Theme.bg
    readonly property color bgSurface: Theme.surface
    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color error: Theme.error
    
    color: bgDeep
    
    signal minimizeClicked()
    signal maximizeClicked()
    signal closeClicked()
    signal dragStarted(point pos)
    signal dragMoved(point pos)
    
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 8
        spacing: 16
        
        // LOGO / TITLE
        Text {
            text: "COMIX DOWNLOADER"
            font.family: "Segoe UI"
            font.pixelSize: 22
            font.weight: Font.Bold
            color: textPrimary
            
            // Amber underline accent
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.bottomMargin: -2
                anchors.left: parent.left
                width: parent.width * 0.4
                height: 2
                color: accentPrimary
                radius: 1
            }
        }
        
        // DRAG AREA
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            MouseArea {
                anchors.fill: parent
                onPressed: (mouse) => root.dragStarted(Qt.point(mouse.x, mouse.y))
                onPositionChanged: (mouse) => root.dragMoved(Qt.point(mouse.x, mouse.y))
            }
        }
        
        // WINDOW CONTROLS
        RowLayout {
            spacing: 2
            
            // Minimize
            Rectangle {
                width: 36; height: 28; radius: 6
                color: minArea.containsMouse ? bgElevated : "transparent"
                Text { anchors.centerIn: parent; text: "─"; font.pixelSize: 14; font.weight: Font.Bold; color: textSecondary }
                MouseArea { id: minArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.minimizeClicked() }
            }
            
            // Maximize
            Rectangle {
                width: 36; height: 28; radius: 6
                color: maxArea.containsMouse ? bgElevated : "transparent"
                Text { anchors.centerIn: parent; text: "□"; font.pixelSize: 14; font.weight: Font.Bold; color: textSecondary }
                MouseArea { id: maxArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.maximizeClicked() }
            }
            
            // Close
            Rectangle {
                width: 36; height: 28; radius: 6
                color: closeArea.containsMouse ? error : "transparent"
                Text { anchors.centerIn: parent; text: "×"; font.pixelSize: 14; font.weight: Font.Bold; color: closeArea.containsMouse ? textPrimary : textSecondary }
                MouseArea { id: closeArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.closeClicked() }
            }
        }
    }
}
