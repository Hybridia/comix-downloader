import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property var entry: null
    property string statusMessage: ""
    property bool busy: false

    signal updateRequested()
    signal removeRequested()
    signal openFolderRequested()
    signal convertToCbzRequested()

    readonly property color bgCard: "#1C1C24"
    readonly property color bgElevated: "#252530"
    readonly property color accentPrimary: "#E8A54B"
    readonly property color textPrimary: "#F5F5F0"
    readonly property color textSecondary: "#8B8B99"
    readonly property color textTertiary: "#5C5C66"
    readonly property color success: "#7CB342"
    readonly property color danger: "#E57373"

    color: bgCard
    radius: 10
    border.color: "#2A2A33"
    border.width: 1

    Layout.fillWidth: true
    // Make room for the optional "Convert to CBZ" button when the
    // entry is image-format. Computed via the actions column below.
    Layout.preferredHeight: showConvertButton ? 162 : 132

    // Convert button visibility: shown only when the user originally
    // downloaded this manga as images. After a successful repack the
    // bridge stamps output_format=cbz on the entry, so this naturally
    // hides on the next refresh.
    readonly property bool showConvertButton:
        entry && (entry.output_format || "").toLowerCase() === "images"

    function shortDate(iso) {
        if (!iso) return "—"
        return iso.substring(0, 10)
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 14

        // POSTER
        Rectangle {
            Layout.preferredWidth: 78
            Layout.preferredHeight: 104
            color: bgElevated
            radius: 6
            clip: true

            Image {
                anchors.fill: parent
                source: entry && entry.poster_url ? entry.poster_url : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: true
            }

            Text {
                anchors.centerIn: parent
                text: "📕"
                font.pixelSize: 28
                color: textTertiary
                visible: !entry || !entry.poster_url
            }
        }

        // METADATA
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 4

            Text {
                Layout.fillWidth: true
                text: entry ? (entry.title || "Untitled") : ""
                font.family: "Segoe UI"
                font.pixelSize: 16
                font.weight: Font.DemiBold
                color: textPrimary
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: entry ? entry.source_url : ""
                font.pixelSize: 11
                color: textSecondary
                elide: Text.ElideMiddle
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Text {
                    text: entry
                          ? "📥 " + (entry.chapter_count || 0) + " ch"
                          : ""
                    font.pixelSize: 11
                    color: textSecondary
                }
                Text {
                    text: entry
                          ? "🗂 " + (entry.output_format || "—").toUpperCase()
                          : ""
                    font.pixelSize: 11
                    color: textSecondary
                }
                Text {
                    text: entry ? "🌐 " + (entry.source || "—") : ""
                    font.pixelSize: 11
                    color: textSecondary
                }
                Item { Layout.fillWidth: true }
            }

            Text {
                Layout.fillWidth: true
                text: {
                    if (root.statusMessage) return root.statusMessage
                    if (!entry) return ""
                    return "Updated " + shortDate(entry.last_updated_at)
                         + (entry.last_checked_at
                            ? "  •  Checked " + shortDate(entry.last_checked_at)
                            : "")
                }
                font.pixelSize: 11
                color: root.statusMessage ? accentPrimary : textTertiary
                elide: Text.ElideRight
            }
        }

        // ACTIONS
        ColumnLayout {
            Layout.preferredWidth: 130
            Layout.fillHeight: true
            spacing: 6

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                text: root.busy ? "Checking…" : "Update"
                enabled: !root.busy && entry
                onClicked: root.updateRequested()

                background: Rectangle {
                    radius: 6
                    color: parent.enabled
                           ? (parent.hovered ? Qt.lighter(accentPrimary, 1.1) : accentPrimary)
                           : "#3A3A45"
                    Behavior on color { ColorAnimation { duration: 120 } }
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.enabled ? "#1A1A1F" : textTertiary
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            // CONVERT TO CBZ — visible only for image-format downloads.
            // Calls the LibraryBridge.convertToCbz slot, which packs
            // every Chapter_N folder into a sibling .cbz. Idempotent;
            // already-CBZ chapters are skipped without re-writing.
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                visible: root.showConvertButton
                enabled: !root.busy
                text: root.busy ? "Working…" : "Convert to CBZ"
                onClicked: root.convertToCbzRequested()

                background: Rectangle {
                    radius: 6
                    color: parent.hovered ? Qt.darker(success, 1.2) : "transparent"
                    border.width: 1
                    border.color: parent.hovered ? success : "#3A3A45"
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.hovered ? "#FFFFFF" : success
                    font.pixelSize: 11
                    font.weight: Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                text: "Open Folder"
                onClicked: root.openFolderRequested()

                background: Rectangle {
                    radius: 6
                    color: parent.hovered ? bgElevated : "transparent"
                    border.width: 1
                    border.color: "#3A3A45"
                }
                contentItem: Text {
                    text: parent.text
                    color: textSecondary
                    font.pixelSize: 11
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                text: "Remove"
                onClicked: root.removeRequested()

                background: Rectangle {
                    radius: 6
                    color: parent.hovered ? Qt.darker(danger, 1.4) : "transparent"
                    border.width: 1
                    border.color: parent.hovered ? danger : "#3A3A45"
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.hovered ? "#FFFFFF" : textSecondary
                    font.pixelSize: 11
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
