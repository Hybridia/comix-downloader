import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../fx"

Rectangle {
    id: root
    objectName: "downloadControls"
    
    property var scanlators: ["Any"]
    property string scanlatorPreference: "Any"
    property string scanlatorFilter: "Any"
    // Chapters ticked in the list (drives the hint + the shake).
    property int selectedCount: 0
    property bool shaking: false
    
    // `from` = Download button centre in window coordinates (fly-to).
    signal downloadClicked(point from)
    signal filterChanged(string filter)

    // Nothing selected → the button shakes instead of dispatching.
    function requestDownload() {
        if (selectedCount <= 0) { shake.restart(); return }
        root.downloadClicked(dlButton.mapToItem(null, dlButton.width / 2, dlButton.height / 2))
    }
    
    // Theme colors
    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color accentGradientEnd: Theme.accent2
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color bgDeep: Theme.bg
    
    color: bgCard
    radius: 12
    border.color: Theme.border
    
    RowLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 16
        
        // SCANLATOR PREFERENCE (for download priority)
        ColumnLayout {
            spacing: 4
            Text { text: "Scanlator Preference"; font.pixelSize: 11; color: textTertiary }
            ComboBox {
                id: preferenceCombo
                model: root.scanlators
                implicitWidth: 150; implicitHeight: 36
                palette.button: Theme.elevated
                palette.buttonText: Theme.textPrimary
                palette.window: Theme.elevated
                palette.windowText: Theme.textPrimary
                palette.base: Theme.elevated
                palette.text: Theme.textPrimary
                palette.highlight: Theme.accent
                palette.highlightedText: Theme.bg
                palette.mid: Theme.border
                palette.dark: Theme.border
                palette.light: Theme.elevated
                onCurrentTextChanged: root.scanlatorPreference = currentText
                background: Rectangle { color: bgElevated; radius: 6; border.color: Theme.border; border.width: 1 }
                contentItem: Text { 
                    text: preferenceCombo.currentText
                    font.pixelSize: 13
                    color: textPrimary
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 10
                    elide: Text.ElideRight 
                }
            }
        }
        
        // SCANLATOR FILTER (for filtering chapter list)
        ColumnLayout {
            spacing: 4
            Text { text: "Scanlator Filter"; font.pixelSize: 11; color: textTertiary }
            ComboBox {
                id: filterCombo
                model: root.scanlators
                implicitWidth: 150; implicitHeight: 36
                palette.button: Theme.elevated
                palette.buttonText: Theme.textPrimary
                palette.window: Theme.elevated
                palette.windowText: Theme.textPrimary
                palette.base: Theme.elevated
                palette.text: Theme.textPrimary
                palette.highlight: Theme.accent
                palette.highlightedText: Theme.bg
                palette.mid: Theme.border
                palette.dark: Theme.border
                palette.light: Theme.elevated
                onCurrentTextChanged: {
                    root.scanlatorFilter = currentText
                    root.filterChanged(currentText)
                }
                background: Rectangle { color: bgElevated; radius: 6; border.color: accentPrimary; border.width: 1 }
                contentItem: Text { 
                    text: filterCombo.currentText
                    font.pixelSize: 13
                    color: accentPrimary
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 10
                    elide: Text.ElideRight 
                }
            }
        }

        // FORMAT (same setting as Settings → Downloads)
        ColumnLayout {
            spacing: 4
            Text { text: "Format"; font.pixelSize: 11; color: textTertiary }
            FormatSelector {
                id: formatSel
                objectName: "browseFormat"
                Layout.preferredWidth: 230
                Layout.preferredHeight: 36
            }
        }
        
        Item { Layout.fillWidth: true }
        
        // DOWNLOAD BUTTON (+ hint) — sheen sweeps across every few seconds
        ColumnLayout {
            spacing: 4
            transform: Translate { id: shakeShift }
            Item {
                id: dlButton
                Layout.preferredWidth: 210
                Layout.preferredHeight: 48
                FxButton {
                    id: dlFx
                    anchors.fill: parent
                    text: "▶  DOWNLOAD"
                    radius: 12
                    letterSpacing: 1.5
                    onClicked: root.requestDownload()
                }
                Item {
                    anchors.fill: parent
                    clip: true
                    scale: dlFx.scale
                    Rectangle {
                        id: sheen
                        width: 60; height: parent.height * 2
                        y: -parent.height / 2
                        rotation: 20
                        x: -width * 2
                        visible: Theme.animations
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: "transparent" }
                            GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.35) }
                            GradientStop { position: 1; color: "transparent" }
                        }
                        SequentialAnimation on x {
                            running: Theme.animations && root.selectedCount > 0
                            loops: Animation.Infinite
                            NumberAnimation { from: -120; to: 260; duration: 1400; easing.type: Easing.InOutQuad }
                            PauseAnimation { duration: 1800 }
                        }
                    }
                }
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: root.selectedCount > 0
                      ? root.selectedCount + " chapter" + (root.selectedCount === 1 ? "" : "s") + " as " + formatSel.label
                      : "Select some chapters first"
                font.pixelSize: 11
                color: textTertiary
            }
        }
    }

    SequentialAnimation {
        id: shake
        onStarted: root.shaking = true
        onStopped: root.shaking = false
        NumberAnimation { target: shakeShift; property: "x"; to: -7; duration: 55 }
        NumberAnimation { target: shakeShift; property: "x"; to: 7; duration: 110 }
        NumberAnimation { target: shakeShift; property: "x"; to: -7; duration: 110 }
        NumberAnimation { target: shakeShift; property: "x"; to: 7; duration: 110 }
        NumberAnimation { target: shakeShift; property: "x"; to: 0; duration: 55 }
    }
}
