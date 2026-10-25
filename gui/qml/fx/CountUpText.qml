import QtQuick
import Style

// A number that rolls to its new value (ease-out), with thousands
// separators: 48210 → "48,210".
Text {
    id: root
    property real value: 0
    property int decimals: 0
    property int duration: 1200
    property real shown: value
    Behavior on shown { NumberAnimation { duration: Theme.dur(root.duration); easing.type: Easing.OutCubic } }

    text: Number(shown).toLocaleString(Qt.locale("en_US"), "f", decimals)
    color: Theme.textPrimary
    font.features: { "tnum": 1 }
}
