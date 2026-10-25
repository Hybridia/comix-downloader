import QtQuick
import QtQuick.Shapes
import Style

// Soft colour blobs drifting slowly behind the whole app. Radial
// gradients instead of blur, so it costs almost nothing per frame.
Item {
    id: root
    visible: Theme.ambient && Theme.animations && !Theme.software
    clip: true

    component Blob: Shape {
        id: blob
        property color tint: Theme.accent
        property real strength: 0.18
        property real size: 620
        property point from: Qt.point(0, 0)
        property point to: Qt.point(0, 0)
        property int period: 22000
        width: size; height: size
        x: from.x; y: from.y
        ShapePath {
            strokeWidth: -1
            fillGradient: RadialGradient {
                centerX: blob.size / 2; centerY: blob.size / 2
                centerRadius: blob.size / 2
                focalX: centerX; focalY: centerY
                GradientStop { position: 0; color: Qt.rgba(blob.tint.r, blob.tint.g, blob.tint.b, blob.strength) }
                GradientStop { position: 1; color: "transparent" }
            }
            PathRectangle { width: blob.size; height: blob.size }
        }
        SequentialAnimation on x {
            running: root.visible; loops: Animation.Infinite
            NumberAnimation { to: blob.to.x; duration: blob.period; easing.type: Easing.InOutSine }
            NumberAnimation { to: blob.from.x; duration: blob.period; easing.type: Easing.InOutSine }
        }
        SequentialAnimation on y {
            running: root.visible; loops: Animation.Infinite
            NumberAnimation { to: blob.to.y; duration: blob.period; easing.type: Easing.InOutSine }
            NumberAnimation { to: blob.from.y; duration: blob.period; easing.type: Easing.InOutSine }
        }
    }

    Blob {
        tint: Theme.accent
        from: Qt.point(-260, -240); to: Qt.point(root.width * 0.25, root.height * 0.15)
        period: 22000
    }
    Blob {
        tint: Theme.cool; strength: 0.12
        from: Qt.point(root.width - 360, root.height * 0.3); to: Qt.point(root.width - 620, root.height * 0.55)
        period: 28000
    }
    Blob {
        tint: Theme.accent2
        from: Qt.point(root.width * 0.3, root.height - 260); to: Qt.point(root.width * 0.55, root.height - 420)
        period: 34000
    }
}
