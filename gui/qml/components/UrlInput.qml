import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../fx"

Rectangle {
    id: root
    objectName: "urlInput"

    // Theme colors
    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color accentGradientEnd: Theme.accent2
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color bgDeep: Theme.bg
    readonly property color success: Theme.success
    readonly property color danger: Theme.error

    color: bgCard
    radius: 12

    signal fetchRequested(string url)

    property bool isLoading: false
    property var supportedSites: []
    // Provider name (e.g. "hentairead") that matches the current input,
    // or empty if the URL doesn't resolve to a registered provider.
    property string matchedProvider: ""
    // True once the user has typed at least one character.
    property bool hasInput: false
    readonly property bool matched: matchedProvider !== ""
    // Long text that clearly isn't a link → red ✕.
    readonly property bool invalid: !matched && urlField.text.length >= 12
                                     && !urlField.text.trim().toLowerCase().startsWith("http")
    readonly property bool focused: urlField.activeFocus
    property bool shaking: false
    property bool dropHot: false

    Component.onCompleted: {
        supportedSites = MangaBridge.supportedSites()
    }

    function classify(text) {
        hasInput = text.length > 0
        matchedProvider = text.length > 0 ? MangaBridge.classifyUrl(text) : ""
    }

    // Enter / Fetch: fetch a recognised URL, shake on anything else.
    function submit() {
        if (root.isLoading) return
        if (root.matched) root.fetchRequested(urlField.text)
        else if (urlField.text.length > 0) shakeAnim.restart()
    }

    // Glow ring around the box: accent while focused, green on a match.
    Rectangle {
        anchors.fill: parent
        anchors.margins: -4
        radius: root.radius + 4
        color: "transparent"
        border.width: 4
        border.color: root.matched ? Qt.rgba(root.success.r, root.success.g, root.success.b, 0.22)
                                   : (root.focused || root.dropHot) ? Theme.glow : "transparent"
        Behavior on border.color { ColorAnimation { duration: Theme.dur(300) } }
    }
    border.width: 1
    border.color: root.matched ? success : (root.focused || root.dropHot) ? accentPrimary : Theme.border
    Behavior on border.color { ColorAnimation { duration: Theme.dur(300) } }

    scale: dropHot ? 1.02 : 1
    Behavior on scale { NumberAnimation { duration: Theme.dur(350); easing.type: Easing.OutBack } }

    transform: Translate { id: shakeShift }
    SequentialAnimation {
        id: shakeAnim
        onStarted: root.shaking = true
        onStopped: root.shaking = false
        loops: 1
        NumberAnimation { target: shakeShift; property: "x"; to: -7; duration: 55 }
        NumberAnimation { target: shakeShift; property: "x"; to: 7; duration: 110 }
        NumberAnimation { target: shakeShift; property: "x"; to: -7; duration: 110 }
        NumberAnimation { target: shakeShift; property: "x"; to: 7; duration: 110 }
        NumberAnimation { target: shakeShift; property: "x"; to: 0; duration: 55 }
    }

    // Drag a link onto the box to fill it in (no auto-fetch).
    DropArea {
        anchors.fill: parent
        onEntered: (drag) => { root.dropHot = drag.hasUrls || drag.hasText }
        onExited: root.dropHot = false
        onDropped: (drop) => {
            root.dropHot = false
            var t = drop.hasUrls && drop.urls.length > 0 ? drop.urls[0].toString() : drop.text
            if (t) { urlField.text = t.trim(); urlField.forceActiveFocus() }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 8

        // INPUT ROW
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            spacing: 8

            // STATUS — link icon, or a ✓ / ✕ disc that pops in.
            Item {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                Text {
                    anchors.centerIn: parent
                    text: "🔗"
                    font.pixelSize: 18
                    opacity: root.matched || root.invalid ? 0 : 0.9
                    Behavior on opacity { NumberAnimation { duration: Theme.dur(200) } }
                }
                Rectangle {
                    anchors.centerIn: parent
                    width: 22; height: 22; radius: 11
                    color: root.matched ? success : danger
                    scale: root.matched || root.invalid ? 1 : 0
                    visible: scale > 0.01
                    Behavior on scale { NumberAnimation { duration: Theme.dur(450); easing.type: Easing.OutBack; easing.overshoot: 2 } }
                    Behavior on color { ColorAnimation { duration: Theme.dur(200) } }
                    Text {
                        anchors.centerIn: parent
                        text: root.matched ? "✓" : "✕"
                        font.pixelSize: 13; font.weight: Font.Black
                        color: Theme.bg
                    }
                }
            }

            // TEXT INPUT
            TextField {
                id: urlField
                objectName: "urlField"
                Layout.fillWidth: true
                Layout.fillHeight: true

                placeholderText: "Paste a manga / gallery URL — or drag a link here"
                // Both `color` and the palette overrides are needed: the
                // Fusion style reads palette entries, so without them the
                // URL renders in near-invisible dark text.
                color: textPrimary
                placeholderTextColor: textTertiary
                palette.text: textPrimary
                palette.placeholderText: textTertiary
                palette.highlight: accentPrimary
                palette.highlightedText: bgDeep
                selectionColor: accentPrimary
                selectedTextColor: bgDeep
                font.family: "Menlo"
                font.pixelSize: 14
                selectByMouse: true
                background: Item {}

                onTextChanged: root.classify(text)
                Keys.onReturnPressed: root.submit()
                Keys.onEnterPressed: root.submit()
            }

            // FETCH BUTTON — pulses once a URL is recognised.
            Item {
                id: fetchButton
                objectName: "fetchButton"
                readonly property bool ready: root.matched && !root.isLoading
                Layout.preferredWidth: 100
                Layout.fillHeight: true

                Rectangle {
                    id: pulseRing
                    anchors.fill: parent
                    radius: 8
                    color: "transparent"
                    border.width: 0
                    border.color: Theme.glow
                    SequentialAnimation on border.width {
                        running: fetchButton.ready && Theme.animations && fetchButton.visible
                        loops: Animation.Infinite
                        NumberAnimation { from: 0; to: 6; duration: 900; easing.type: Easing.InOutSine }
                        NumberAnimation { from: 6; to: 0; duration: 900; easing.type: Easing.InOutSine }
                        onRunningChanged: if (!running) pulseRing.border.width = 0
                    }
                    anchors.margins: -border.width
                }
                FxButton {
                    anchors.fill: parent
                    text: root.isLoading ? "…" : "FETCH"
                    radius: 8
                    letterSpacing: 1
                    enabled: fetchButton.ready
                    onClicked: root.submit()
                }
            }
        }

        // SUPPORTED-SITES CHIP ROW
        Flow {
            Layout.fillWidth: true
            spacing: 6

            Text {
                text: "Supported:"
                font.pixelSize: 11
                color: textTertiary
                font.weight: Font.DemiBold
                height: 22
                verticalAlignment: Text.AlignVCenter
            }

            Repeater {
                model: root.supportedSites

                Rectangle {
                    property bool isMatch: root.matchedProvider === modelData.name
                    radius: 10
                    height: 22
                    width: chipRow.implicitWidth + 18
                    color: isMatch ? Qt.rgba(root.success.r, root.success.g, root.success.b, 0.16) : bgElevated
                    border.color: isMatch ? success : Theme.border
                    border.width: 1
                    opacity: root.matched && !isMatch ? 0.35 : 1
                    scale: isMatch ? 1.12 : 1
                    z: isMatch ? 1 : 0
                    Behavior on color { ColorAnimation { duration: Theme.dur(250) } }
                    Behavior on border.color { ColorAnimation { duration: Theme.dur(250) } }
                    Behavior on opacity { NumberAnimation { duration: Theme.dur(300) } }
                    Behavior on scale { NumberAnimation { duration: Theme.dur(450); easing.type: Easing.OutBack } }

                    Row {
                        id: chipRow
                        anchors.centerIn: parent
                        spacing: 4

                        Text {
                            text: modelData.auth_required ? "🔒" : ""
                            color: textSecondary
                            font.pixelSize: 10
                            visible: modelData.auth_required
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            id: chipText
                            text: (modelData.domains && modelData.domains.length > 0)
                                  ? modelData.domains[0]
                                  : modelData.label
                            font.family: "Segoe UI"
                            font.pixelSize: 11
                            font.weight: isMatch ? Font.DemiBold : Font.Normal
                            color: isMatch ? success : textSecondary
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    HoverHandler {
                        id: hover
                        cursorShape: Qt.IBeamCursor
                    }
                    ToolTip.visible: hover.hovered && modelData.example_url !== ""
                    ToolTip.delay: 350
                    ToolTip.text: modelData.example_url
                                  + (modelData.auth_required
                                     ? "\n(requires login — see Settings)"
                                     : "")
                }
            }
        }
    }

    Connections {
        target: MangaBridge
        function onLoadingChanged(loading) {
            root.isLoading = loading
        }
    }
}
