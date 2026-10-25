import QtQuick
import QtQuick.Effects
import Style

// One page of the main view switcher. The incoming page slides in from
// the right, fades and un-blurs; the outgoing one slides left and
// fades. Pages stay instantiated, so their state survives switching.
Item {
    id: pane
    property int index: 0
    property int currentIndex: 0
    readonly property bool active: index === currentIndex
    default property alias content: holder.data
    property real blurAmount: 0

    visible: opacity > 0.001
    enabled: active

    Component.onCompleted: {
        opacity = active ? 1 : 0
        shift.x = 0
    }
    onActiveChanged: active ? enter.restart() : exit.restart()

    transform: Translate { id: shift }

    ParallelAnimation {
        id: enter
        onStarted: exit.stop()
        NumberAnimation { target: pane; property: "opacity"; from: 0; to: 1; duration: Theme.dur(420); easing.type: Easing.OutQuint }
        NumberAnimation { target: shift; property: "x"; from: 40; to: 0; duration: Theme.dur(520); easing.type: Easing.OutQuint }
        NumberAnimation { target: pane; property: "scale"; from: 0.98; to: 1; duration: Theme.dur(520); easing.type: Easing.OutQuint }
        NumberAnimation { target: pane; property: "blurAmount"; from: 0.5; to: 0; duration: Theme.dur(420); easing.type: Easing.OutQuint }
    }
    ParallelAnimation {
        id: exit
        onStarted: enter.stop()
        NumberAnimation { target: pane; property: "opacity"; to: 0; duration: Theme.dur(300); easing.type: Easing.OutQuint }
        NumberAnimation { target: shift; property: "x"; to: -40; duration: Theme.dur(400); easing.type: Easing.OutQuint }
        NumberAnimation { target: pane; property: "scale"; to: 0.98; duration: Theme.dur(400); easing.type: Easing.OutQuint }
    }

    Item {
        id: holder
        anchors.fill: parent
        // Blur only while it's visible on screen, and never in software.
        layer.enabled: pane.blurAmount > 0.01 && !Theme.software
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: pane.blurAmount
            blurMax: 24
        }
    }
}
