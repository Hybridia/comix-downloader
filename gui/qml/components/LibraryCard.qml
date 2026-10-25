import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../fx"
import "../logic/motion.js" as Motion

Rectangle {
    id: root

    property var entry: null
    property string statusMessage: ""
    property bool busy: false
    // Ticked for "Check selected" (Library toolbar → Updates view).
    property bool selected: false
    // Result of this card's "Check" (LibraryBridge.entryCheckFinished
    // summary) — drives the inline "N new … [Download]" row.
    property var checkInfo: null
    readonly property bool hasNewChapters: !!checkInfo && checkInfo.new_count > 0

    // ── Motion ─────────────────────────────────────────────────────
    // ≥0 → rise in with a stagger when created (set by LibraryView).
    property int entranceIndex: -1
    // Cover flipped to its info side (ⓘ button).
    property bool flipped: false
    // "Downloaded N new chapters" just landed → check draws + confetti.
    property bool celebrating: false
    property real tiltX: 0
    property real tiltY: 0
    function toggleFlip() { flipped = !flipped }
    function hoverLeft() { flipped = false; tiltX = 0; tiltY = 0 }
    function celebrate() {
        celebrating = true
        burst.burst()
        celebrateTimer.restart()
    }
    onStatusMessageChanged: if (statusMessage.indexOf("Downloaded ") === 0) celebrate()
    Timer { id: celebrateTimer; interval: 6000; onTriggered: root.celebrating = false }
    readonly property bool working: statusMessage.indexOf("Checking") === 0
                                    || statusMessage.indexOf("Downloading") === 0
                                    || statusMessage.indexOf("Packing") === 0

    Component.onCompleted: if (entranceIndex >= 0 && Theme.animations) rise.start()
    SequentialAnimation {
        id: rise
        PropertyAction { target: root; property: "opacity"; value: 0 }
        PropertyAction { target: riseShift; property: "y"; value: 28 }
        PropertyAction { target: root; property: "scale"; value: 0.94 }
        PauseAnimation { duration: Motion.staggerDelay(Math.max(0, root.entranceIndex)) }
        ParallelAnimation {
            NumberAnimation { target: root; property: "opacity"; to: 1; duration: Theme.dur(550); easing.type: Easing.OutQuint }
            NumberAnimation { target: riseShift; property: "y"; to: 0; duration: Theme.dur(650); easing.type: Easing.OutQuint }
            NumberAnimation { target: root; property: "scale"; to: 1; duration: Theme.dur(650); easing.type: Easing.OutQuint }
        }
    }

    // Gentle 3D tilt toward the cursor (cards are wide, so small angles).
    transform: [
        Translate { id: riseShift },
        Translate {
            y: cardHover.hovered ? -2 : 0
            Behavior on y { NumberAnimation { duration: Theme.dur(250); easing.type: Easing.OutQuint } }
        },
        Rotation {
            origin.x: root.width / 2; origin.y: root.height / 2
            axis { x: 0; y: 1; z: 0 }
            angle: root.tiltY
            Behavior on angle { NumberAnimation { duration: Theme.dur(200); easing.type: Easing.OutQuad } }
        },
        Rotation {
            origin.x: root.width / 2; origin.y: root.height / 2
            axis { x: 1; y: 0; z: 0 }
            angle: root.tiltX
            Behavior on angle { NumberAnimation { duration: Theme.dur(200); easing.type: Easing.OutQuad } }
        }
    ]
    HoverHandler {
        id: cardHover
        onPointChanged: {
            if (!hovered || !Theme.animations) return
            root.tiltY = (point.position.x / root.width - 0.5) * 3
            root.tiltX = -(point.position.y / root.height - 0.5) * 5
        }
        onHoveredChanged: if (!hovered) root.hoverLeft()
    }
    // Accent glow ring on hover
    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: root.radius + 3
        color: "transparent"
        border.width: 3
        border.color: Theme.glow
        opacity: cardHover.hovered ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.dur(300) } }
    }
    ParticleBurst {
        id: burst
        anchors.fill: parent
        z: 50
    }

    signal updateRequested()
    signal removeRequested()
    signal openFolderRequested()
    signal openWebsiteRequested()
    signal openAlternativeRequested(string url)
    signal convertToCbzRequested()
    signal selectToggled()
    signal downloadNewRequested()
    signal reviewRequested()
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
            case "completed": return Theme.success   // green
            case "cancelled": return "#9E9E9E"   // grey
            case "hiatus":    return Theme.accent   // amber
            case "ongoing":   return "#5DADE2"   // blue
            // Unknown: use the accent so the pill reads as a clear
            // call-to-action, not a "no data" indicator.
            default:          return Theme.accent
        }
    }

    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color success: Theme.success
    readonly property color danger: Theme.error

    color: bgCard
    radius: 10
    border.color: cardHover.hovered ? accentPrimary : selected ? Qt.darker(accentPrimary, 1.4) : Theme.border
    border.width: 1
    Behavior on border.color { ColorAnimation { duration: Theme.dur(250) } }

    Layout.fillWidth: true
    // Make room for the optional "Convert to CBZ" button when the
    // entry is image-format, plus a compact row of "also on…" chips
    // when the iCloud-import enricher found alternative sources for
    // this title on other sites.
    Layout.preferredHeight: {
        var h = showConvertButton ? 162 : 132
        if (hasAlternatives) h += 30
        if (hasNewChapters) h += 36
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

        // POSTER — flips to an info side via the ⓘ button
        Item {
            Layout.preferredWidth: 78
            Layout.preferredHeight: 104

            Flipable {
                id: flip
                anchors.fill: parent

                front: Rectangle {
                    anchors.fill: parent
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

                    // Selection checkbox — always visible (subtle when off) so
                    // it's discoverable; toggles inclusion in "Check selected".
                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.margins: 5
                        width: 22; height: 22; radius: 5
                        color: root.selected ? accentPrimary
                               : (selectMa.containsMouse ? Qt.rgba(Theme.card.r, Theme.card.g, Theme.card.b, 0.8) : Qt.rgba(Theme.card.r, Theme.card.g, Theme.card.b, 0.6))
                        border.width: 1
                        border.color: root.selected ? accentPrimary : Theme.textSecondary
                        Text {
                            anchors.centerIn: parent
                            visible: root.selected
                            text: "✓"
                            color: Theme.surface
                            font.pixelSize: 14
                            font.weight: Font.Bold
                        }
                        MouseArea {
                            id: selectMa
                    anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.selectToggled()
                        }
                        ToolTip.visible: selectMa.containsMouse
                        ToolTip.delay: 600
                        ToolTip.text: root.selected ? "Selected for “Check selected”"
                                                    : "Select to check this series for updates"
                    }
                }

                back: Rectangle {
                    anchors.fill: parent
                    radius: 6
                    color: bgElevated
                    border.color: accentPrimary
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 6
                        spacing: 2
                        Text { text: entry ? (entry.chapter_count || 0) + " ch" : ""; font.pixelSize: 13; font.weight: Font.Bold; color: accentPrimary }
                        Text { text: entry ? (entry.source || "") : ""; font.pixelSize: 9; color: textSecondary; elide: Text.ElideRight; Layout.fillWidth: true }
                        Text { text: _statusGlyph(root.statusKey) + " " + _statusLabel(root.statusKey); font.pixelSize: 9; color: _statusColor(root.statusKey) }
                        Item { Layout.fillHeight: true }
                        Text { text: "last"; font.pixelSize: 8; color: textTertiary }
                        Text { text: entry ? shortDate(entry.last_updated_at) : ""; font.pixelSize: 9; color: textSecondary }
                    }
                }

                transform: Rotation {
                    origin.x: flip.width / 2; origin.y: flip.height / 2
                    axis { x: 0; y: 1; z: 0 }
                    angle: root.flipped ? 180 : 0
                    Behavior on angle { NumberAnimation { duration: Theme.dur(800); easing.type: Easing.OutBack } }
                }
            }

            // Light sweep across the cover on hover
            Item {
                anchors.fill: parent
                clip: true
                visible: Theme.animations && !root.flipped
                Rectangle {
                    width: 30; height: parent.height * 1.6
                    y: -parent.height * 0.3
                    rotation: 18
                    x: cardHover.hovered ? parent.width + 30 : -60
                    Behavior on x { NumberAnimation { duration: cardHover.hovered ? Theme.dur(900) : 0; easing.type: Easing.OutQuint } }
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "transparent" }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.35) }
                        GradientStop { position: 1; color: "transparent" }
                    }
                }
            }

            // ⓘ — flip the cover
            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 5
                width: 20; height: 20; radius: 10
                color: infoMa.containsMouse || root.flipped ? accentPrimary : Qt.rgba(Theme.card.r, Theme.card.g, Theme.card.b, 0.75)
                border.color: root.flipped ? accentPrimary : Theme.textSecondary
                scale: infoMa.pressed ? 0.85 : 1
                Behavior on scale { NumberAnimation { duration: Theme.dur(250); easing.type: Easing.OutBack } }
                Text {
                    anchors.centerIn: parent
                    text: "i"
                    font.pixelSize: 11; font.weight: Font.Black; font.italic: true
                    color: infoMa.containsMouse || root.flipped ? Theme.bg : textPrimary
                }
                MouseArea {
                    id: infoMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleFlip()
                }
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
                        transformOrigin: Popup.TopLeft
                        palette.window: Theme.elevated
                        palette.base: Theme.elevated
                        palette.button: Theme.elevated
                        palette.windowText: Theme.textPrimary
                        palette.text: Theme.textPrimary
                        palette.buttonText: Theme.textPrimary
                        palette.highlight: Theme.accent
                        palette.highlightedText: Theme.bg
                        palette.mid: Theme.border
                        background: Rectangle {
                            implicitWidth: 220
                            color: Theme.elevated
                            border.color: Theme.border
                            radius: 10
                        }
                        enter: Transition {
                            ParallelAnimation {
                                NumberAnimation { property: "scale"; from: 0.6; to: 1; duration: Theme.dur(350); easing.type: Easing.OutBack }
                                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.dur(200) }
                            }
                        }
                        exit: Transition {
                            NumberAnimation { property: "opacity"; to: 0; duration: Theme.dur(150) }
                        }

                        // Header item showing what auto-tracking sees
                        // (greyed out, non-clickable).
                        StaggerItem {
                            order: 0
                            text: root.statusAuto
                                ? "From site: " + _statusLabel(root.statusAuto)
                                : "Site doesn't report status"
                            enabled: false
                        }
                        MenuSeparator {}
                        StaggerItem {
                            order: 1
                            text: "Mark as Completed"
                            onTriggered: root.statusChangeRequested("completed", true)
                        }
                        StaggerItem {
                            order: 2
                            text: "Mark as Ongoing"
                            onTriggered: root.statusChangeRequested("ongoing", true)
                        }
                        StaggerItem {
                            order: 3
                            text: "Mark as Hiatus"
                            onTriggered: root.statusChangeRequested("hiatus", true)
                        }
                        StaggerItem {
                            order: 4
                            text: "Mark as Cancelled"
                            onTriggered: root.statusChangeRequested("cancelled", true)
                        }
                        MenuSeparator {}
                        StaggerItem {
                            order: 5
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

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Spinner {
                    Layout.preferredWidth: 12; Layout.preferredHeight: 12
                    visible: root.working
                    color: accentPrimary
                }
                // ✓ that draws itself left → right when a download lands
                Item {
                    Layout.preferredWidth: root.celebrating ? 14 : 0
                    Layout.preferredHeight: 14
                    clip: true
                    Behavior on Layout.preferredWidth { NumberAnimation { duration: Theme.dur(450); easing.type: Easing.OutQuint } }
                    Text { text: "✓"; font.pixelSize: 13; font.weight: Font.Black; color: success; anchors.verticalCenter: parent.verticalCenter }
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
                    color: root.celebrating ? success : root.statusMessage ? accentPrimary : textTertiary
                    Behavior on color { ColorAnimation { duration: Theme.dur(300) } }
                    elide: Text.ElideRight
                }
            }

            // NEW CHAPTERS — shown after this card's Check found some.
            // "Download" takes every new chapter from the recommended
            // site; "Review" opens the Updates view to pick chapters or
            // a different site.
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 30
                visible: root.hasNewChapters
                onVisibleChanged: if (visible && Theme.animations) newPop.restart()
                transform: Scale { id: newRowScale; origin.x: 0; origin.y: 15 }
                SequentialAnimation {
                    id: newPop
                    NumberAnimation { target: newRowScale; properties: "xScale,yScale"; from: 0.4; to: 1; duration: 600; easing.type: Easing.OutBack }
                }
                spacing: 10

                Text {
                    text: root.hasNewChapters
                          ? ("✦ " + checkInfo.new_count + " new ("
                             + (checkInfo.new_count === 1 ? "ch " + checkInfo.first
                                : "ch " + checkInfo.first + "–" + checkInfo.last)
                             + ") on " + checkInfo.provider)
                          : ""
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    color: success
                }

                Button {
                    Layout.preferredHeight: 26
                    text: "⬇ Download " + (root.hasNewChapters ? checkInfo.new_count : 0) + " new"
                    onClicked: root.downloadNewRequested()
                    background: Rectangle {
                        radius: 6
                        color: parent.hovered ? Qt.lighter(success, 1.15) : success
                    }
                    contentItem: Text {
                        text: parent.text
                        color: Theme.surface
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 10
                        rightPadding: 10
                    }
                }

                Text {
                    text: "Review…"
                    font.pixelSize: 12
                    color: accentPrimary
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.reviewRequested()
                    }
                }

                Item { Layout.fillWidth: true }
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
                    border.color: Theme.border
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
                        transformOrigin: Popup.TopLeft
                        palette.window: Theme.elevated
                        palette.base: Theme.elevated
                        palette.button: Theme.elevated
                        palette.windowText: Theme.textPrimary
                        palette.text: Theme.textPrimary
                        palette.buttonText: Theme.textPrimary
                        palette.highlight: Theme.accent
                        palette.highlightedText: Theme.bg
                        palette.mid: Theme.border
                        background: Rectangle {
                            implicitWidth: 220
                            color: Theme.elevated
                            border.color: Theme.border
                            radius: 10
                        }
                        enter: Transition {
                            ParallelAnimation {
                                NumberAnimation { property: "scale"; from: 0.6; to: 1; duration: Theme.dur(350); easing.type: Easing.OutBack }
                                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.dur(200) }
                            }
                        }
                        exit: Transition {
                            NumberAnimation { property: "opacity"; to: 0; duration: Theme.dur(150) }
                        }
                        Repeater {
                            model: Math.max(0, root.alternativeSources.length - 3)
                            StaggerItem {
                                order: 6
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
            Layout.preferredWidth: 300
            Layout.maximumWidth: 300
            Layout.minimumWidth: 170
            Layout.fillHeight: true
            spacing: 6

            // "Check for new" squeezes into a spinner while checking.
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                FxButton {
                    id: checkBtn
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: parent.height
                    width: root.busy ? 32 : parent.width
                    radius: root.busy ? 16 : 7
                    text: root.busy ? "" : "Check for new"
                    fontSize: 12
                    enabled: !root.busy && !!entry
                    onClicked: root.updateRequested()
                    Behavior on width { NumberAnimation { duration: Theme.dur(450); easing.type: Easing.OutQuint } }
                    Behavior on radius { NumberAnimation { duration: Theme.dur(450) } }
                    ToolTip.visible: hovered && !root.busy
                    ToolTip.delay: 600
                    ToolTip.text: "Look for new chapters on this series now.\n" +
                                  "Shows what's new here — nothing downloads until you click Download."
                }
                Spinner {
                    anchors.centerIn: parent
                    width: 16; height: 16
                    visible: root.busy
                    color: Theme.bg
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
                    border.color: parent.hovered ? success : Theme.border
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
                        border.color: Theme.border
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
                        border.color: Theme.border
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
                    border.color: parent.hovered ? danger : Theme.border
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

    // Menu item that slides in after `order` × 40 ms when its menu opens.
    component StaggerItem: MenuItem {
        id: si
        property int order: 0
        transform: Translate { id: siShift }
        Connections {
            target: si.menu
            function onAboutToShow() { siIn.restart() }
        }
        SequentialAnimation {
            id: siIn
            PropertyAction { target: si; property: "opacity"; value: Theme.animations ? 0 : 1 }
            PropertyAction { target: siShift; property: "x"; value: Theme.animations ? -8 : 0 }
            PauseAnimation { duration: Theme.dur(si.order * 40) }
            ParallelAnimation {
                NumberAnimation { target: si; property: "opacity"; to: 1; duration: Theme.dur(250) }
                NumberAnimation { target: siShift; property: "x"; to: 0; duration: Theme.dur(300); easing.type: Easing.OutQuint }
            }
        }
    }
}
