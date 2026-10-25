import QtQuick
import Style

// Small rotating arc.
Item {
    id: sp
    property color color: Theme.accent
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.width: 2.5
        border.color: sp.color
        opacity: 0.25
    }
    Rectangle {
        width: parent.width / 2; height: parent.height / 2
        clip: true
        color: "transparent"
        Rectangle {
            width: sp.width; height: sp.height
            radius: width / 2
            color: "transparent"
            border.width: 2.5
            border.color: sp.color
        }
    }
    RotationAnimation on rotation { from: 0; to: 360; duration: 700; loops: Animation.Infinite; running: sp.visible }
}
