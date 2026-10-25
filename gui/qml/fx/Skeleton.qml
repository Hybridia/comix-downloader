import QtQuick
import Style

// Placeholder block with a moving shimmer while content loads.
Rectangle {
    id: root
    radius: 7
    color: Theme.elevated
    clip: true

    Loader {
        anchors.fill: parent
        // Loops keep running while hidden, so stop when not on screen.
        active: Theme.animations && root.visible
        sourceComponent: Item {
            Rectangle {
                id: band
                width: root.width * 0.6
                height: parent.height
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 0.5; color: Theme.border }
                    GradientStop { position: 1; color: "transparent" }
                }
                NumberAnimation on x {
                    from: -band.width; to: root.width
                    duration: 1200; loops: Animation.Infinite
                }
            }
        }
    }
}
