import QtQuick
import QtQuick.Effects
import Style

// Springy button: lifts on hover, squishes on press, ripples from the
// press point. Primary = accent gradient; otherwise a ghost button.
Item {
    id: root
    property string text: ""
    property bool primary: true
    property int fontSize: 13
    property int fontWeight: Font.Bold
    property real radius: 10
    property real letterSpacing: 0.5
    readonly property bool hovered: mouse.containsMouse
    readonly property bool pressed: mouse.pressed
    signal clicked()

    implicitWidth: label.implicitWidth + 36
    implicitHeight: 38
    opacity: enabled ? 1 : 0.4
    Behavior on opacity { NumberAnimation { duration: Theme.dur(250) } }

    scale: !enabled ? 1 : pressed ? 0.94 : hovered ? 1.03 : 1
    Behavior on scale { NumberAnimation { duration: Theme.dur(320); easing.type: Easing.OutBack; easing.overshoot: 2.2 } }

    transform: Translate {
        y: root.enabled && root.hovered && !root.pressed ? -2 : 0
        Behavior on y { NumberAnimation { duration: Theme.dur(250); easing.type: Easing.OutQuint } }
    }

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: root.radius
        color: root.primary ? Theme.accent : Theme.card
        border.width: root.primary ? 0 : 1
        border.color: root.hovered ? Theme.accent : Theme.border
        gradient: root.primary ? grad : null
        Behavior on border.color { ColorAnimation { duration: Theme.dur(200) } }

        layer.enabled: root.primary && root.hovered && root.enabled && !Theme.software && Theme.animations
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.glow
            shadowBlur: 0.8
            shadowVerticalOffset: 6
        }
    }
    Gradient {
        id: grad
        orientation: Gradient.Horizontal
        GradientStop { position: 0; color: Theme.accent }
        GradientStop { position: 1; color: Theme.accent2 }
    }

    Ripple { id: ripple; anchors.fill: parent }

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        font.pixelSize: root.fontSize
        font.weight: root.fontWeight
        font.letterSpacing: root.letterSpacing
        color: root.primary ? Theme.bg : Theme.textPrimary
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
        onPressed: (m) => ripple.spawn(m.x, m.y)
        onClicked: root.clicked()
    }
}
