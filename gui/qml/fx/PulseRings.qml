import QtQuick
import Style

// Rings pulsing outward while something is working.
Item {
    id: root
    property color color: Theme.accent
    property bool running: true

    Loader {
        objectName: "pulseLoader"
        anchors.fill: parent
        active: Theme.animations && root.running && root.visible
        sourceComponent: Item {
            Repeater {
                model: 2
                Rectangle {
                    id: ring
                    required property int index
                    anchors.centerIn: parent
                    width: root.width; height: root.height
                    radius: width / 2
                    color: "transparent"
                    border.color: root.color
                    border.width: 2
                    opacity: 0
                    SequentialAnimation {
                        running: true
                        PauseAnimation { duration: ring.index * 1000 }
                        ParallelAnimation {
                            loops: Animation.Infinite
                            NumberAnimation { target: ring; property: "scale"; from: 1; to: 2.4; duration: 2000; easing.type: Easing.OutQuint }
                            NumberAnimation { target: ring; property: "opacity"; from: 0.9; to: 0; duration: 2000; easing.type: Easing.OutQuint }
                        }
                    }
                }
            }
        }
    }
}
