import QtQuick
import Style
import QtQuick.Layouts
import QtQuick.Controls

Rectangle {
    id: root
    objectName: "sideBar"
    
    signal browseClicked()
    signal downloadsClicked()
    signal libraryClicked()
    signal updatesClicked()
    signal settingsClicked()

    property int activeTab: 0 // 0: Browse, 1: Downloads, 2: Library, 3: Updates
    // Series waiting for approval in the Updates view (badge).
    property int updatesCount: 0
    // Chapters still queued or downloading (Downloads badge).
    property int downloadsCount: 0
    // The Downloads button — the fly-to-downloads bubble lands here.
    readonly property Item downloadsAnchor: downloadsBtn
    // y of the active nav button inside the nav area (indicator target).
    readonly property real activeButtonY: navButtons.children[activeTab] ? navButtons.children[activeTab].y : 0

    function bumpDownloads() { downloadsBtn.bump() }
    
    // Theme colors
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
        
        // NAVIGATION ITEMS — a sliding indicator sits behind the buttons
        // and springs to the active one.
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: navButtons.implicitHeight

            Rectangle {
                id: indicator
                objectName: "navIndicator"
                width: parent.width
                height: 48
                radius: 8
                color: Theme.card
                y: root.activeButtonY
                Behavior on y { NumberAnimation { duration: Theme.dur(550); easing.type: Easing.OutBack; easing.overshoot: 1.3 } }

                Rectangle {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: 4; height: 24
                    radius: 2
                    color: accentPrimary
                }
                // soft glow next to the bar
                Rectangle {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: 14; height: 28
                    radius: 7
                    color: Theme.glow
                    opacity: 0.35
                }
            }

            ColumnLayout {
                id: navButtons
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 8
                
                NavButton {
                    icon: "🔍"
                    label: "Browse Manga"
                    isActive: root.activeTab === 0
                    onClicked: { root.activeTab = 0; root.browseClicked() }
                }
                
                NavButton {
                    id: downloadsBtn
                    icon: "📥"
                    label: "Downloads"
                    badge: root.downloadsCount
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
        }
        
        Item { Layout.fillHeight: true }
        
        // SETTINGS BUTTON AT BOTTOM
        NavButton {
            icon: "⚙️"
            label: "Settings"
            spinIcon: true
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
        property bool spinIcon: false
        property int _lastBadge: 0
        signal clicked()

        function bump() { bumpAnim.restart() }
        onBadgeChanged: {
            if (badge > _lastBadge) bump()
            _lastBadge = badge
        }
        
        Layout.fillWidth: true
        Layout.preferredHeight: 48
        radius: 8
        // The active background is the sliding indicator behind us.
        color: !isActive && mouseArea.containsMouse ? Theme.surface : "transparent"
        
        Behavior on color { ColorAnimation { duration: Theme.dur(150) } }
        
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            spacing: 12
            
            Text {
                text: btn.icon
                font.pixelSize: 18
                opacity: btn.isActive ? 1.0 : 0.7
                rotation: btn.spinIcon && mouseArea.containsMouse ? 120 : 0
                Behavior on rotation { NumberAnimation { duration: Theme.dur(800); easing.type: Easing.OutBack } }
            }
            
            Text {
                text: btn.label
                font.family: "Segoe UI"
                font.pixelSize: 14
                font.weight: btn.isActive ? Font.DemiBold : Font.Normal
                color: btn.isActive ? textPrimary : textSecondary
                Behavior on color { ColorAnimation { duration: Theme.dur(200) } }
            }

            Item { Layout.fillWidth: true }

            Rectangle {
                id: badgePill
                visible: scale > 0.01
                scale: btn.badge > 0 ? 1 : 0
                Behavior on scale { NumberAnimation { duration: Theme.dur(450); easing.type: Easing.OutBack } }
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
                transform: [
                    Scale { id: bumpScale; origin.x: badgePill.width / 2; origin.y: badgePill.height / 2 },
                    Rotation { id: bumpRot; origin.x: badgePill.width / 2; origin.y: badgePill.height / 2 }
                ]
                SequentialAnimation {
                    id: bumpAnim
                    ParallelAnimation {
                        NumberAnimation { target: bumpScale; properties: "xScale,yScale"; to: 1.7; duration: Theme.dur(180); easing.type: Easing.OutQuad }
                        NumberAnimation { target: bumpRot; property: "angle"; to: -10; duration: Theme.dur(180) }
                    }
                    ParallelAnimation {
                        NumberAnimation { target: bumpScale; properties: "xScale,yScale"; to: 1; duration: Theme.dur(420); easing.type: Easing.OutBack }
                        NumberAnimation { target: bumpRot; property: "angle"; to: 0; duration: Theme.dur(420); easing.type: Easing.OutBack }
                    }
                }
            }
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
