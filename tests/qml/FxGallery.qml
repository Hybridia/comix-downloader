import QtQuick
import QtQuick.Window
import Style
import "../../gui/qml/fx"

// Hosts every fx component once so tests can poke them headlessly.
Window {
    width: 900; height: 700; visible: true
    color: Theme.bg

    AmbientGlow { objectName: "ambient"; anchors.fill: parent }

    Column {
        spacing: 16; x: 20; y: 20
        FxButton { objectName: "fxButton"; text: "Primary" }
        FxButton { objectName: "fxGhost"; text: "Ghost"; primary: false }
        Skeleton { objectName: "skeleton"; width: 200; height: 14 }
        CountUpText { objectName: "count"; value: 0 }
        PulseRings { objectName: "pulse"; width: 40; height: 40; running: true }
        Item {
            width: 200; height: 120
            ParticleBurst { id: burst; objectName: "burst"; anchors.fill: parent }
        }
    }

    ToastHost { objectName: "toastHost"; anchors.fill: parent }
}
