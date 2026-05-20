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
    signal openWebsiteRequested()
    signal openAlternativeRequested(string url)
    signal convertToCbzRequested()
    // statusKey is one of: "completed" | "cancelled" | "ongoing" |
    // "hiatus" | "" (clear/auto). manual=true flags as user override
    // so the next probe won't overwrite it.
    signal statusChangeRequested(string statusKey, bool manual)

    // Compute the badge label/color from the entry. Falls back to
    // sensible defaults when status is unknown or the entry isn't
    // loaded yet.
    readonly property string statusKey: entry ? (entry.status || "") : ""
    readonly property bool statusManual: entry ? !!entry.status_manual : false
    readonly property string statusAuto: entry ? (entry.status_auto || "") : ""

    function _statusLabel(key) {
        switch (key) {
            case "completed": return "Completed"
            case "cancelled": return "Cancelled"
            case "hiatus":    return "Hiatus"
            case "ongoing":   return "Ongoing"
            default:          return "Set status"
        }
    }
    function _statusGlyph(key) {
        switch (key) {
            case "completed": return "✓"
            case "cancelled": return "✕"
            case "hiatus":    return "⏸"
            case "ongoing":   return "●"
            default:          return "+"
        }
    }
    function _statusColor(key) {
        switch (key) {
            case "completed": return "#7CB342"   // green
            case "cancelled": return "#9E9E9E"   // grey
            case "hiatus":    return "#E8A54B"   // amber
            case "ongoing":   return "#5DADE2"   // blue
            // Unknown: use the accent so the pill reads as a clear
            // call-to-action, not a "no data" indicator.
            default:          return "#E8A54B"
        }
    }

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
    // entry is image-format, plus a compact row of "also on…" chips
    // when the iCloud-import enricher found alternative sources for
    // this title on other sites.
    Layout.preferredHeight: {
        var h = showConvertButton ? 162 : 132
        if (hasAlternatives) h += 30
        return h
    }

    // Convert button visibility: shown only when the user originally
    // downloaded this manga as images. After a successful repack the
    // bridge stamps output_format=cbz on the entry, so this naturally
    // hides on the next refresh.
    readonly property bool showConvertButton:
        entry && (entry.output_format || "").toLowerCase() === "images"

    // The enrich_alternatives.py script populates this with confident
    // matches from other providers, sorted by chapter count desc. The
    // primary source is NOT included.
    readonly property var alternativeSources:
        entry ? (entry.alternative_sources || []) : []
    readonly property bool hasAlternatives: alternativeSources.length > 0

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

                // STATUS PILL — clickable. Tooltip explains the auto
                // vs manual relationship; menu lets the user override.
                Rectangle {
                    id: statusPill
                    visible: entry
                    Layout.preferredHeight: 22
                    implicitWidth: pillRow.implicitWidth + 14
                    radius: 11
                    color: Qt.darker(_statusColor(root.statusKey), 2.2)
                    border.color: _statusColor(root.statusKey)
                    border.width: 1

                    RowLayout {
                        id: pillRow
                        anchors.centerIn: parent
                        spacing: 5

                        Text {
                            text: _statusGlyph(root.statusKey)
                            font.pixelSize: 11
                            color: _statusColor(root.statusKey)
                        }
                        Text {
                            text: _statusLabel(root.statusKey)
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            color: _statusColor(root.statusKey)
                        }
                        // Small lock glyph when the user has set a
                        // manual override — makes it obvious why a
                        // probe didn't change the badge.
                        Text {
                            text: "✋"
                            font.pixelSize: 9
                            color: _statusColor(root.statusKey)
                            visible: root.statusManual
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: statusMenu.popup()
                        ToolTip.visible: containsMouse
                        ToolTip.delay: 600
                        ToolTip.text: {
                            if (root.statusManual) {
                                var msg = "Manually set to " + _statusLabel(root.statusKey)
                                if (root.statusAuto && root.statusAuto !== root.statusKey) {
                                    msg += " — site reports " + _statusLabel(root.statusAuto)
                                }
                                return msg + ".\nClick to change."
                            }
                            if (root.statusKey === "") {
                                return "Status unknown — click Update to fetch from the site,\n"
                                     + "or click here to mark it manually."
                            }
                            return "From the site (auto).\nClick to override."
                        }
                    }

                    Menu {
                        id: statusMenu

                        // Header item showing what auto-tracking sees
                        // (greyed out, non-clickable).
                        MenuItem {
                            text: root.statusAuto
                                ? "From site: " + _statusLabel(root.statusAuto)
                                : "Site doesn't report status"
                            enabled: false
                        }
                        MenuSeparator {}
                        MenuItem {
                            text: "Mark as Completed"
                            onTriggered: root.statusChangeRequested("completed", true)
                        }
                        MenuItem {
                            text: "Mark as Ongoing"
                            onTriggered: root.statusChangeRequested("ongoing", true)
                        }
                        MenuItem {
                            text: "Mark as Hiatus"
                            onTriggered: root.statusChangeRequested("hiatus", true)
                        }
                        MenuItem {
                            text: "Mark as Cancelled"
                            onTriggered: root.statusChangeRequested("cancelled", true)
                        }
                        MenuSeparator {}
                        MenuItem {
                            text: root.statusManual
                                ? "Use site status (clear override)"
                                : "Clear status"
                            // Pass manual=false so the next probe
                            // re-syncs from the provider. If there's
                            // no auto status, the badge will show "?".
                            onTriggered: root.statusChangeRequested("", false)
                        }
                    }
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

            // ALSO ON — alternative sources discovered via the iCloud
            // cross-site matcher. Each chip shows the provider name +
            // chapter count + status glyph; clicking opens the URL in
            // the browser. Hidden when there are no alternatives.
            RowLayout {
                Layout.fillWidth: true
                visible: root.hasAlternatives
                spacing: 6

                Text {
                    text: "Also on:"
                    font.pixelSize: 10
                    font.weight: Font.Medium
                    color: textTertiary
                }

                Repeater {
                    // Render at most 3 chips inline; the rest fall
                    // into a "+ N more" overflow chip that opens a
                    // menu listing them all.
                    model: Math.min(3, root.alternativeSources.length)

                    Rectangle {
                        readonly property var alt: root.alternativeSources[index]
                        readonly property color baseColor: _statusColor(alt.status || "")

                        Layout.preferredHeight: 22
                        implicitWidth: altRow.implicitWidth + 12
                        radius: 11
                        color: ma.containsMouse
                            ? Qt.darker(baseColor, 1.8)
                            : Qt.darker(baseColor, 2.5)
                        border.color: baseColor
                        border.width: 1

                        Behavior on color { ColorAnimation { duration: 100 } }

                        RowLayout {
                            id: altRow
                            anchors.centerIn: parent
                            spacing: 4

                            Text {
                                text: _statusGlyph(alt.status || "")
                                font.pixelSize: 9
                                color: baseColor
                            }
                            Text {
                                text: alt.provider
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                                color: baseColor
                            }
                            Text {
                                text: (alt.chapter_count || 0) > 0
                                    ? alt.chapter_count + "ch"
                                    : ""
                                visible: text.length > 0
                                font.pixelSize: 10
                                color: textSecondary
                            }
                        }

                        MouseArea {
                            id: ma
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            hoverEnabled: true
                            onClicked: root.openAlternativeRequested(alt.url)

                            ToolTip.visible: containsMouse
                            ToolTip.delay: 500
                            ToolTip.text: alt.title_on_site
                                ? alt.title_on_site + "\n" + alt.url
                                : alt.url
                        }
                    }
                }

                // Overflow chip — "+ N more" → opens a menu with
                // every additional alternative listed.
                Rectangle {
                    visible: root.alternativeSources.length > 3
                    Layout.preferredHeight: 22
                    implicitWidth: overflowText.implicitWidth + 14
                    radius: 11
                    color: overflowMa.containsMouse ? bgElevated : "transparent"
                    border.color: "#3A3A45"
                    border.width: 1

                    Text {
                        id: overflowText
                        anchors.centerIn: parent
                        text: "+ " + (root.alternativeSources.length - 3) + " more"
                        font.pixelSize: 10
                        color: textSecondary
                    }

                    MouseArea {
                        id: overflowMa
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: overflowMenu.popup()
                    }

                    Menu {
                        id: overflowMenu
                        Repeater {
                            model: Math.max(0, root.alternativeSources.length - 3)
                            MenuItem {
                                required property int index
                                readonly property var alt:
                                    root.alternativeSources[index + 3]
                                text: alt
                                    ? (alt.provider + " · " + (alt.chapter_count || 0)
                                       + "ch · " + _statusLabel(alt.status || ""))
                                    : ""
                                onTriggered: alt ? root.openAlternativeRequested(alt.url) : null
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }
            }
        }

        // ACTIONS
        ColumnLayout {
            // minimumWidth must be set or the layout will shrink this
            // column to a sliver when the metadata column's implicit
            // width grows (lots of "Also on:" chips, long titles, etc.)
            // — leaving only the left edge of every button visible.
            // 170px fits the Folder+Website side-by-side row without
            // text truncation; below ~150 they degrade to "Fol…".
            Layout.preferredWidth: 170
            Layout.minimumWidth: 170
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

            // Open-row: side-by-side Folder + Website. Keeps the
            // card height unchanged (still one 28px row) while
            // doubling the action coverage.
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                spacing: 4

                Button {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: "📂 Folder"
                    onClicked: root.openFolderRequested()

                    ToolTip.visible: hovered
                    ToolTip.delay: 600
                    ToolTip.text: "Reveal the download folder in your file manager."

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
                    Layout.fillHeight: true
                    text: "🔗 Website"
                    enabled: entry && (entry.source_url || "").length > 0
                    onClicked: root.openWebsiteRequested()

                    ToolTip.visible: hovered && enabled
                    ToolTip.delay: 600
                    ToolTip.text: entry
                        ? "Open " + (entry.source_url || "") + "\nin your default browser."
                        : ""

                    background: Rectangle {
                        radius: 6
                        color: parent.hovered ? bgElevated : "transparent"
                        border.width: 1
                        border.color: "#3A3A45"
                    }
                    contentItem: Text {
                        text: parent.text
                        color: parent.enabled ? textSecondary : textTertiary
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
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
