import QtQuick
import Style

// Click ripple: a circle grows ×4 from the press point and fades.
Item {
    id: root
    clip: true
    property color color: Qt.rgba(1, 1, 1, 0.45)

    function spawn(px, py) {
        if (!Theme.animations) return
        ripple.createObject(root, { cx: px, cy: py })
    }

    Component {
        id: ripple
        Rectangle {
            id: r
            property real cx: 0
            property real cy: 0
            readonly property real size: Math.max(root.width, root.height)
            width: size; height: size; radius: size / 2
            x: cx - size / 2; y: cy - size / 2
            color: root.color
            scale: 0
            ParallelAnimation {
                running: true
                NumberAnimation { target: r; property: "scale"; to: 4; duration: 600; easing.type: Easing.OutQuad }
                NumberAnimation { target: r; property: "opacity"; to: 0; duration: 600; easing.type: Easing.OutQuad }
                onFinished: r.destroy()
            }
        }
    }
}
