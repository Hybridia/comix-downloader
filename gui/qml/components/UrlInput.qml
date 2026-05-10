import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    // Theme colors
    readonly property color bgCard: "#1C1C24"
    readonly property color bgElevated: "#252530"
    readonly property color accentPrimary: "#E8A54B"
    readonly property color accentGradientEnd: "#D4873A"
    readonly property color textPrimary: "#F5F5F0"
    readonly property color textSecondary: "#8B8B99"
    readonly property color textTertiary: "#5C5C66"
    readonly property color bgDeep: "#0A0A0C"
    readonly property color success: "#7CB342"
    readonly property color danger: "#E57373"

    color: bgCard
    radius: 12

    signal fetchRequested(string url)

    property bool isLoading: false
    property var supportedSites: []
    // Provider name (e.g. "hentairead") that matches the current input,
    // or empty if the URL doesn't resolve to a registered provider.
    property string matchedProvider: ""
    // True once the user has typed at least one character — used to
    // suppress the red "unsupported" hint on a pristine input.
    property bool hasInput: false

    Component.onCompleted: {
        supportedSites = MangaBridge.supportedSites()
    }

    function classify(text) {
        hasInput = text.length > 0
        matchedProvider = text.length > 0 ? MangaBridge.classifyUrl(text) : ""
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

            // STATUS ICON — link / check / cross depending on validation.
            Text {
                Layout.preferredWidth: 22
                horizontalAlignment: Text.AlignHCenter
                text: {
                    if (root.matchedProvider) return "✓"
                    if (root.hasInput) return "✗"
                    return "🔗"
                }
                color: {
                    if (root.matchedProvider) return success
                    if (root.hasInput) return danger
                    return textSecondary
                }
                font.pixelSize: root.matchedProvider || root.hasInput ? 16 : 18
                font.weight: Font.Bold
                opacity: 0.9
            }

            // TEXT INPUT
            TextField {
                id: urlField
                Layout.fillWidth: true
                Layout.fillHeight: true

                placeholderText: "Paste a manga / gallery URL — supported sites listed below"
                // Both `color` and the palette overrides are needed:
                // `color` paints the text on the Basic style; the
                // Fusion style we apply at app startup uses palette
                // entries instead, so without these the URL would
                // render in Fusion's near-invisible default dark text
                // on our dark background.
                color: textPrimary
                placeholderTextColor: textTertiary
                palette.text: textPrimary
                palette.placeholderText: textTertiary
                palette.highlight: accentPrimary
                palette.highlightedText: bgDeep
                selectionColor: accentPrimary
                selectedTextColor: bgDeep
                font.family: "Segoe UI"
                font.pixelSize: 14
                font.weight: Font.Medium
                selectByMouse: true

                background: Rectangle {
                    color: "transparent"

                    Rectangle {
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: urlField.activeFocus ? parent.width : 0
                        height: 2
                        color: {
                            if (root.matchedProvider) return success
                            if (root.hasInput) return danger
                            return accentPrimary
                        }
                        radius: 1
                        Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }

                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: textTertiary
                        opacity: 0.3
                    }
                }

                onTextChanged: root.classify(text)
                Keys.onReturnPressed: {
                    if (text.length > 0 && !root.isLoading) {
                        root.fetchRequested(text)
                    }
                }
            }

            // FETCH BUTTON
            Rectangle {
                id: fetchButton

                Layout.preferredWidth: 100
                Layout.fillHeight: true
                radius: 6

                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: accentPrimary }
                    GradientStop { position: 1.0; color: accentGradientEnd }
                }

                opacity: (root.matchedProvider && !root.isLoading) ? 1.0 : 0.55
                Behavior on opacity { NumberAnimation { duration: 150 } }

                scale: fetchMouseArea.pressed ? 0.97 : (fetchMouseArea.containsMouse && root.matchedProvider ? 1.02 : 1.0)
                Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

                Text {
                    anchors.centerIn: parent
                    text: root.isLoading ? "..." : "FETCH"
                    font.family: "Segoe UI"
                    font.pixelSize: 12
                    font.weight: Font.Bold
                    color: bgDeep
                    font.letterSpacing: 1
                }

                MouseArea {
                    id: fetchMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: root.matchedProvider ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                    enabled: !root.isLoading && root.matchedProvider !== ""

                    onClicked: {
                        if (urlField.text.length > 0) {
                            root.fetchRequested(urlField.text)
                        }
                    }
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
                    width: chipText.implicitWidth + 18
                    color: isMatch ? Qt.darker(success, 1.6) : bgElevated
                    border.color: isMatch ? success : "#3A3A45"
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: 180 } }
                    Behavior on border.color { ColorAnimation { duration: 180 } }

                    Row {
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
                            color: isMatch ? "#FFFFFF" : textSecondary
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
