import QtQuick
import Style
import QtQuick.Layouts
import QtQuick.Controls

Rectangle {
    id: root
    
    signal browseClicked()
    signal downloadsClicked()
    signal libraryClicked()
    signal updatesClicked()
    signal settingsClicked()

    property int activeTab: 0 // 0: Browse, 1: Downloads, 2: Library, 3: Updates
    // Series waiting for approval in the Updates view (badge).
    property int updatesCount: 0
    
    // Theme colors (mirroring Theme.qml for consistency)
    readonly property color bgDeep: Theme.bg
    readonly property color bgSurface: Theme.surface
    readonly property color accentPrimary: Theme.accent
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    
    width: 240
    color: bgDeep
    
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 32
        
        // LOGO / TITLE
        ColumnLayout {
            spacing: -4
            Text {
                text: "COMIX"
                font.family: "Segoe UI"
                font.pixelSize: 28
                font.weight: Font.Black
                color: accentPrimary
                font.letterSpacing: 2
            }
            Text {
                text: "DOWNLOADER"
                font.family: "Segoe UI"
                font.pixelSize: 10
                font.weight: Font.Bold
                color: textSecondary
                font.letterSpacing: 4
            }
        }
        
        // NAVIGATION ITEMS
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8
            
            NavButton {
                icon: "🔍"
                label: "Browse Manga"
                isActive: root.activeTab === 0
                onClicked: { root.activeTab = 0; root.browseClicked() }
            }
            
            NavButton {
                icon: "📥"
                label: "Downloads"
                isActive: root.activeTab === 1
                onClicked: { root.activeTab = 1; root.downloadsClicked() }
            }

            NavButton {
                icon: "📚"
                label: "Library"
                isActive: root.activeTab === 2
                onClicked: { root.activeTab = 2; root.libraryClicked() }
            }

            NavButton {
                icon: "🔔"
                label: "Updates"
                badge: root.updatesCount
                isActive: root.activeTab === 3
                onClicked: { root.activeTab = 3; root.updatesClicked() }
            }
        }
        
        Item { Layout.fillHeight: true }
        
        // SETTINGS BUTTON AT BOTTOM
        NavButton {
            icon: "⚙️"
            label: "Settings"
            onClicked: root.settingsClicked()
        }
    }
    
    // ═══════════════════════════════════════════════════════════════
    // NAVIGATION BUTTON COMPONENT
    // ═══════════════════════════════════════════════════════════════
    component NavButton: Rectangle {
        id: btn
        property string icon: ""
        property string label: ""
        property bool isActive: false
        property int badge: 0
        signal clicked()
        
        Layout.fillWidth: true
        Layout.preferredHeight: 48
        radius: 8
        color: isActive ? Theme.card : (mouseArea.containsMouse ? Theme.surface : "transparent")
        
        Behavior on color { ColorAnimation { duration: 150 } }
        
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            spacing: 12
            
            Text {
                text: btn.icon
                font.pixelSize: 18
                opacity: btn.isActive ? 1.0 : 0.7
            }
            
            Text {
                text: btn.label
                font.family: "Segoe UI"
                font.pixelSize: 14
                font.weight: btn.isActive ? Font.DemiBold : Font.Normal
                color: btn.isActive ? textPrimary : textSecondary
            }

            Item { Layout.fillWidth: true }

            Rectangle {
                visible: btn.badge > 0
                Layout.rightMargin: 12
                Layout.preferredHeight: 20
                Layout.preferredWidth: Math.max(20, badgeText.implicitWidth + 12)
                radius: 10
                color: accentPrimary
                Text {
                    id: badgeText
                    anchors.centerIn: parent
                    text: btn.badge
                    font.pixelSize: 11
                    font.weight: Font.Bold
                    color: Theme.surface
                }
            }
        }
        
        // Indicator for active tab
        Rectangle {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: 4; height: 24
            radius: 2
            color: accentPrimary
            visible: btn.isActive
        }
        
        MouseArea {
            id: mouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: btn.clicked()
        }
    }
}
