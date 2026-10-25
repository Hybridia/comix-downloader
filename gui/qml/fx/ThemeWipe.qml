import QtQuick
import QtQuick.Effects
import Style

// Theme switch with a circular colour wipe. A snapshot of the old theme
// covers the window, the new theme is applied underneath, then a circle
// grows from the click point and reveals it. Software rendering (or
// animations off) falls back to a crossfade (or an instant switch).
Item {
    id: wipe
    objectName: "themeWipe"
    property Item target: null          // what to snapshot (window content)
    property bool active: false
    property real radius: 0
    property point origin: Qt.point(0, 0)
    property int _seq: 0
    readonly property real _maxRadius: Math.hypot(Math.max(origin.x, width - origin.x),
                                                  Math.max(origin.y, height - origin.y))

    function start(name, at) {
        finishNow()
        var seq = ++_seq
        if (!Theme.animations || !target) {
            SettingsBridge.theme = name
            return
        }
        active = true
        origin = at
        target.grabToImage(function (result) {
            if (seq !== wipe._seq) return          // a newer switch won
            snapshot.source = result.url
            snapshot.visible = true
            SettingsBridge.theme = name
            wipe.radius = 0
            snapshot.opacity = 1
            reveal.restart()
        })
    }

    function finishNow() {
        reveal.stop()
        snapshot.visible = false
        snapshot.source = ""
        active = false
    }

    Connections {
        target: Fx
        function onThemeWipeRequested(name, at) { wipe.start(name, at) }
    }

    Image {
        id: snapshot
        objectName: "themeWipeSnapshot"
        anchors.fill: parent
        visible: false
        cache: false
        // With masks available the effect below draws the snapshot.
        layer.enabled: visible && !Theme.software
        layer.effect: MultiEffect {
            maskEnabled: true
            maskInverted: true
            maskSource: maskItem
            maskThresholdMin: 0.5
            maskSpreadAtMin: 0.2
        }
    }

    Item {
        id: maskItem
        anchors.fill: parent
        layer.enabled: true
        visible: false
        Rectangle {
            width: wipe.radius * 2; height: width; radius: width / 2
            x: wipe.origin.x - wipe.radius
            y: wipe.origin.y - wipe.radius
            color: "black"
        }
    }

    SequentialAnimation {
        id: reveal
        ParallelAnimation {
            NumberAnimation {
                target: wipe; property: "radius"; to: wipe._maxRadius
                duration: Theme.software ? 0 : 750; easing.type: Easing.OutQuint
            }
            NumberAnimation {
                target: snapshot; property: "opacity"; to: Theme.software ? 0 : 1
                duration: Theme.software ? 300 : 0
            }
        }
        ScriptAction { script: wipe.finishNow() }
    }
}
