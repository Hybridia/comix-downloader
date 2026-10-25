import QtQuick
import Style

// CBZ / PDF / Images with a spring-sliding highlight. Bound two-way to
// the global output_format setting, so every copy stays in sync.
Rectangle {
    id: fsel
    readonly property var formats: ["cbz", "pdf", "images"]
    readonly property int idx: Math.max(0, formats.indexOf(SettingsBridge ? SettingsBridge.outputFormat : "cbz"))
    readonly property string label: ["CBZ", "PDF", "Images"][idx]
    function choose(i) { SettingsBridge.setValue("output_format", formats[i]) }

    implicitHeight: 40
    radius: 10
    color: Theme.elevated
    Rectangle {
        y: 4; height: parent.height - 8
        width: (parent.width - 8) / 3
        x: 4 + fsel.idx * width
        radius: 7
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Theme.accent }
            GradientStop { position: 1; color: Theme.accent2 }
        }
        Behavior on x { NumberAnimation { duration: Theme.dur(500); easing.type: Easing.OutBack } }
    }
    Row {
        anchors.fill: parent
        anchors.margins: 4
        Repeater {
            model: ["CBZ", "PDF", "Images"]
            Item {
                required property string modelData
                required property int index
                width: (fsel.width - 8) / 3; height: parent.height
                Text {
                    anchors.centerIn: parent
                    text: modelData
                    font.pixelSize: 12; font.weight: Font.DemiBold
                    color: fsel.idx === index ? Theme.bg : Theme.textSecondary
                    Behavior on color { ColorAnimation { duration: Theme.dur(250) } }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: fsel.choose(index)
                }
            }
        }
    }
}
