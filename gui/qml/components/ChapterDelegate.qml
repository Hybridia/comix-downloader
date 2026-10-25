import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    
    property var chapter: null
    property bool shown: true
    property int waveDelay: 0      // ms before the visual change (range / select-all cascade)
    property int wave: 0           // bumps when a cascade should nudge this row
    property int entranceDelay: -1 // ≥0 → slide in after this many ms
    signal toggled(bool shift)

    readonly property bool selected: chapter ? !!chapter.selected : false
    // What the row *shows*; follows `selected` after waveDelay.
    property bool visualSelected: selected
    onSelectedChanged: {
        if (waveDelay > 0 && Theme.animations) { visualTimer.interval = waveDelay; visualTimer.restart() }
        else visualSelected = selected
    }
    onWaveChanged: if (Theme.animations) waveAnim.restart()
    Timer { id: visualTimer; onTriggered: { root.visualSelected = root.selected; waveAnim.restart() } }
    
    // Theme colors
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color bgDeep: Theme.bg
    
    // Collapses to 0 when filtered out.
    height: shown ? 48 : 0
    opacity: shown ? 1 : 0
    visible: height > 0.5
    clip: true
    Behavior on height { NumberAnimation { duration: Theme.dur(350); easing.type: Easing.OutQuint } }
    Behavior on opacity { NumberAnimation { duration: Theme.dur(300) } }

    Component.onCompleted: if (entranceDelay >= 0 && Theme.animations) entrance.restart()
    SequentialAnimation {
        id: entrance
        PropertyAction { target: row; property: "opacity"; value: 0 }
        PropertyAction { target: slide; property: "x"; value: -16 }
        PauseAnimation { duration: Math.max(0, root.entranceDelay) }
        ParallelAnimation {
            NumberAnimation { target: row; property: "opacity"; to: 1; duration: Theme.dur(450); easing.type: Easing.OutQuint }
            NumberAnimation { target: slide; property: "x"; to: 0; duration: Theme.dur(450); easing.type: Easing.OutQuint }
        }
    }
    SequentialAnimation {
        id: waveAnim
        NumberAnimation { target: nudge; property: "x"; to: 8; duration: Theme.dur(180); easing.type: Easing.OutQuad }
        NumberAnimation { target: nudge; property: "x"; to: 0; duration: Theme.dur(320); easing.type: Easing.OutBack }
    }

    Rectangle {
        id: row
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 44
        radius: 8
        color: mouseArea.containsMouse ? bgElevated : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.dur(150) } }
        transform: [
            Translate { id: slide },
            Translate { id: nudge },
            Translate {
                x: mouseArea.containsMouse ? 4 : 0
                Behavior on x { NumberAnimation { duration: Theme.dur(150); easing.type: Easing.OutCubic } }
            }
        ]

        // Selected rows: accent → transparent wash
        Rectangle {
            anchors.fill: parent
            radius: 8
            opacity: root.visualSelected ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.dur(250) } }
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.glow }
                GradientStop { position: 0.7; color: "transparent" }
            }
        }
        
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 8
            spacing: 14
            
            // CHECKBOX — fills with a spring, tick draws left → right
            Rectangle {
                width: 20; height: 20; radius: 6
                color: root.visualSelected ? accentPrimary : "transparent"
                border.color: root.visualSelected ? accentPrimary : textTertiary
                border.width: 2
                scale: root.visualSelected ? 1.1 : 1
                Behavior on color { ColorAnimation { duration: Theme.dur(200) } }
                Behavior on scale { NumberAnimation { duration: Theme.dur(350); easing.type: Easing.OutBack; easing.overshoot: 2.5 } }
                Item {
                    anchors.left: parent.left
                    anchors.leftMargin: 3
                    anchors.verticalCenter: parent.verticalCenter
                    height: 16
                    width: root.visualSelected ? 14 : 0
                    clip: true
                    Behavior on width { NumberAnimation { duration: Theme.dur(280); easing.type: Easing.OutQuint } }
                    Text {
                        text: "✓"
                        font.pixelSize: 13
                        font.weight: Font.Black
                        color: bgDeep
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
            
            // CHAPTER INFO
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                
                Text {
                    text: chapter ? ("Ch. " + chapter.number + (chapter.title ? " — " + chapter.title : "")) : ""
                    font.family: "Segoe UI"
                    font.pixelSize: 14
                    font.weight: root.visualSelected ? Font.DemiBold : Font.Normal
                    color: root.visualSelected ? textPrimary : textSecondary
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                
                Text {
                    text: chapter ? chapter.group_name : ""
                    font.pixelSize: 10
                    color: textTertiary
                    visible: chapter && chapter.group_name
                }
            }
        }
        
        MouseArea {
            id: mouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: (mouse) => root.toggled((mouse.modifiers & Qt.ShiftModifier) !== 0)
        }
    }
}
