import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../fx"
import "../logic/motion.js" as Motion

// Review-before-download for library updates.
//
// "Check for Updates" probes every followed series (LibraryBridge
// .checkForUpdates) and lists the ones with new chapters here. Nothing
// downloads until the user ticks what they want and clicks "Download
// selected" — the explicit-approval counterpart to Update All.
//
// Selection lives in `sel` (library_url → {include, source, picked})
// and is kept in JS; `selVersion` is bumped on every mutation because
// QML bindings don't notice changes inside a plain JS object.
Item {
    id: updatesView

    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color accentPrimary: Theme.accent
    readonly property color borderColor: Theme.border
    readonly property color okColor: Qt.lighter(Theme.success, 1.25)

    property var items: []
    property var sel: ({})
    property int selVersion: 0
    property var expandedGaps: ({})

    property bool checking: false
    // Chapters currently ticked across all series (Download button).
    readonly property int applyCount: (selVersion, totals().chapters)
    property int checkDone: 0
    property int checkTotal: 0
    property string checkTitle: ""
    property string summary: ""
    property string checkedAt: ""

    function refresh() {
        items = LibraryBridge.pendingUpdates()
        checkedAt = LibraryBridge.pendingCheckedAt()
        checking = LibraryBridge.isCheckingForUpdates()
        var next = {}
        for (var i = 0; i < items.length; i++) {
            var it = items[i]
            next[it.library_url] = sel[it.library_url] || defaultSel(it)
        }
        sel = next
        selVersion++
    }

    function newerOf(item, idx) {
        var s = (item.sources || [])[idx]
        return s ? (s.newer || []) : []
    }

    function defaultSel(item) {
        var picked = {}
        var newer = newerOf(item, item.recommended)
        for (var i = 0; i < newer.length; i++) picked[newer[i].norm] = true
        return { include: true, source: item.recommended, picked: picked }
    }

    function setSource(item, idx) {
        var picked = {}
        var newer = newerOf(item, idx)
        for (var i = 0; i < newer.length; i++) picked[newer[i].norm] = true
        sel[item.library_url] = { include: true, source: idx, picked: picked }
        selVersion++
    }

    function toggleChapter(url, norm) {
        var s = sel[url]
        if (!s) return
        if (s.picked[norm]) delete s.picked[norm]
        else s.picked[norm] = true
        s.include = Object.keys(s.picked).length > 0
        selVersion++
    }

    function toggleInclude(url) {
        var s = sel[url]
        if (!s) return
        s.include = !s.include
        selVersion++
    }

    function setAll(on) {
        for (var url in sel) sel[url].include = on
        selVersion++
    }

    function pickedCount(url) {
        var s = sel[url]
        return (s && s.include) ? Object.keys(s.picked).length : 0
    }

    function totals() {
        var _ = selVersion
        var series = 0, chapters = 0
        for (var url in sel) {
            var n = pickedCount(url)
            if (n > 0) { series++; chapters += n }
        }
        return { series: series, chapters: chapters }
    }

    function applySelected() {
        var out = []
        for (var url in sel) {
            var s = sel[url]
            if (!s.include) continue
            var numbers = Object.keys(s.picked)
            if (numbers.length === 0) continue
            out.push({ library_url: url, source_index: s.source, numbers: numbers })
        }
        if (out.length === 0) return
        var queued = LibraryBridge.applyUpdates(out)
        summary = queued > 0
            ? ("Queued " + queued + " chapter" + (queued === 1 ? "" : "s")
               + " — see Downloads. New files go to your download folder, not iCloud.")
            : "Nothing to download — those chapters are already on disk."
        refresh()
    }

    function rangeText(list) {
        if (!list || list.length === 0) return ""
        if (list.length === 1) return "ch " + list[0].number
        return "ch " + list[0].number + "–" + list[list.length - 1].number
    }

    function sourceLabel(src) {
        if (!src) return ""
        var name = src.provider || "?"
        if (src.error) {
            var e = src.error
            if (e.indexOf("Cloudflare human-verification") >= 0)
                return name + " — blocked by Cloudflare's human check (start FlareSolverr)"
            if (e.indexOf("blocked on this network") >= 0)
                return name + " — blocked on this network (try a VPN)"
            return name + " — failed: " + e.substring(0, 60)
        }
        var parts = [name + " — up to ch " + (src.latest || "?")]
        parts.push(src.newer.length > 0 ? ("+" + src.newer.length + " new") : "nothing new")
        if (src.is_detected) parts.push("★ your files came from here")
        else if (src.is_primary) parts.push("main site")
        return parts.join(" · ")
    }

    function fmtCheckedAt(iso) {
        if (!iso) return ""
        var d = new Date(iso)
        return isNaN(d.getTime()) ? iso : d.toLocaleString(Qt.locale(), Locale.ShortFormat)
    }

    Component.onCompleted: refresh()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 32
        spacing: 16

        // ── Header ───────────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                spacing: 4
                Text {
                    text: "Updates"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    color: textPrimary
                }
                Text {
                    text: "New chapters for the series in your library. Nothing downloads until you approve it."
                    font.pixelSize: 13
                    color: textSecondary
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                id: checkBtn
                Layout.preferredHeight: 34
                text: updatesView.checking
                      ? ("Cancel (" + updatesView.checkDone + " / " + updatesView.checkTotal + ")")
                      : "🔔 Check for Updates"
                onClicked: {
                    if (updatesView.checking) LibraryBridge.cancelCheckForUpdates()
                    else LibraryBridge.checkForUpdates()
                }
                ToolTip.visible: hovered && !updatesView.checking
                ToolTip.delay: 600
                ToolTip.text: "Look for new chapters on every ongoing series.\n" +
                              "Checks the site your files came from first.\n" +
                              "Does NOT download anything."
                background: Rectangle {
                    radius: 6
                    color: updatesView.checking
                           ? (parent.hovered ? "#C45050" : "#A03A3A")
                           : (parent.hovered ? bgElevated : "transparent")
                    border.width: 1
                    border.color: updatesView.checking ? "#A03A3A"
                                  : (parent.hovered ? accentPrimary : borderColor)
                }
                contentItem: Text {
                    text: parent.text
                    color: updatesView.checking ? "#FFFFFF" : textPrimary
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 14
                    rightPadding: 14
                }
            }

            FxButton {
                id: applyBtn
                readonly property var t: updatesView.totals()
                Layout.preferredHeight: 34
                Layout.preferredWidth: applyRow.implicitWidth + 30
                enabled: t.chapters > 0
                fontSize: 12
                text: ""
                onClicked: updatesView.applySelected()
                Row {
                    id: applyRow
                    anchors.centerIn: parent
                    spacing: 0
                    Text { text: "⬇ Download "; font.pixelSize: 12; font.weight: Font.DemiBold; color: applyBtn.enabled ? Theme.bg : Theme.textTertiary }
                    CountUpText {
                        objectName: "applyCountText"
                        visible: applyBtn.t.chapters > 0
                        value: updatesView.applyCount
                        duration: 400
                        font.pixelSize: 12; font.weight: Font.Black
                        color: applyBtn.enabled ? Theme.bg : Theme.textTertiary
                    }
                    Text {
                        text: applyBtn.t.chapters > 0
                              ? " chapter" + (applyBtn.t.chapters === 1 ? "" : "s") + " (" + applyBtn.t.series + " series)"
                              : "selected"
                        font.pixelSize: 12; font.weight: Font.DemiBold; color: applyBtn.enabled ? Theme.bg : Theme.textTertiary
                    }
                }
            }
        }

        // ── Progress / summary banner ────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            visible: updatesView.checking || updatesView.summary.length > 0
            radius: 8
            color: updatesView.checking ? bgCard : "#1F2E1A"
            border.width: 1
            border.color: updatesView.checking ? accentPrimary : "#4A7A3A"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 10
                spacing: 10
                BusyIndicator {
                    visible: updatesView.checking
                    running: updatesView.checking
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    palette.dark: accentPrimary
                }
                Text {
                    visible: !updatesView.checking
                    text: "✓"
                    font.pixelSize: 16
                    color: okColor
                }
                Text {
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    font.pixelSize: 13
                    color: textPrimary
                    text: updatesView.checking
                          ? ("Checking " + updatesView.checkDone + " of " + updatesView.checkTotal
                             + (updatesView.checkTitle ? ": " + updatesView.checkTitle : "")
                             + " — results appear below as they come in")
                          : updatesView.summary
                }
                Text {
                    visible: !updatesView.checking
                    text: "✕"
                    color: textSecondary
                    font.pixelSize: 14
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: updatesView.summary = ""
                    }
                }
            }
        }

        // ── List toolbar ─────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            visible: updatesView.items.length > 0
            spacing: 16
            Text {
                text: updatesView.items.length + " series with new chapters"
                font.pixelSize: 12
                color: textSecondary
            }
            Text {
                text: "Select all"
                font.pixelSize: 12
                color: accentPrimary
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: updatesView.setAll(true) }
            }
            Text {
                text: "Select none"
                font.pixelSize: 12
                color: accentPrimary
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: updatesView.setAll(false) }
            }
            Item { Layout.fillWidth: true }
            Text {
                visible: updatesView.checkedAt.length > 0
                text: "Last checked " + updatesView.fmtCheckedAt(updatesView.checkedAt)
                font.pixelSize: 12
                color: textTertiary
            }
        }

        // ── Empty state ──────────────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: updatesView.items.length === 0
            spacing: 8
            // fillWidth spacer: lets this column stretch so the text centres
            Item { Layout.fillHeight: true; Layout.fillWidth: true }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "🔔"
                font.pixelSize: 40
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: updatesView.checking ? "Checking your library…"
                      : (updatesView.checkedAt ? "You're up to date" : "No check yet")
                font.pixelSize: 16
                font.weight: Font.DemiBold
                color: textPrimary
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: updatesView.checking
                      ? "Series with new chapters show up here as they're found."
                      : "Click “Check for Updates” to look for new chapters on every ongoing series,\n"
                        + "or tick series in the Library and use “Check selected”."
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: 13
                color: textSecondary
            }
            Item { Layout.fillHeight: true }
        }

        // ── Series list ──────────────────────────────────────────────
        // Shimmering placeholders while a check runs and nothing is listed yet.
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 10
            visible: updatesView.checking && updatesView.items.length === 0
            Repeater {
                model: 3
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 92
                    radius: 10
                    color: bgCard
                    border.color: borderColor
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10
                        Skeleton { Layout.preferredWidth: 220; Layout.preferredHeight: 16 }
                        Skeleton { Layout.preferredWidth: 140; Layout.preferredHeight: 10 }
                        Row {
                            spacing: 6
                            Repeater { model: 4; Skeleton { width: 58; height: 22; radius: 11 } }
                        }
                    }
                }
            }
        }

        ScrollView {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: updatesView.items.length > 0
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: scroller.availableWidth
                spacing: 10

                Repeater {
                    model: updatesView.items

                    delegate: Rectangle {
                        id: card
                        required property var modelData
                        required property int index
                        transform: Translate { id: cardShift }
                        Component.onCompleted: if (Theme.animations && index < 16) cardIn.start()
                        SequentialAnimation {
                            id: cardIn
                            PropertyAction { target: cardShift; property: "y"; value: 24 }
                            PropertyAction { target: card; property: "scale"; value: 0.96 }
                            PauseAnimation { duration: Motion.staggerDelay(card.index) }
                            ParallelAnimation {
                                NumberAnimation { target: cardShift; property: "y"; to: 0; duration: Theme.dur(550); easing.type: Easing.OutQuint }
                                NumberAnimation { target: card; property: "scale"; to: 1; duration: Theme.dur(550); easing.type: Easing.OutQuint }
                            }
                        }
                        readonly property var item: modelData
                        readonly property string url: item.library_url
                        readonly property var s: (updatesView.selVersion, updatesView.sel[url] || { include: false, source: -1, picked: {} })
                        readonly property var src: (item.sources || [])[s.source] || null
                        readonly property bool showGaps: (updatesView.selVersion, !!updatesView.expandedGaps[url])

                        Layout.fillWidth: true
                        implicitHeight: body.implicitHeight + 28
                        radius: 10
                        color: bgCard
                        border.width: 1
                        border.color: s.include ? Qt.darker(accentPrimary, 1.6) : borderColor
                        opacity: s.include ? 1.0 : 0.6

                        RowLayout {
                            id: body
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 14
                            spacing: 14

                            // Include checkbox
                            Rectangle {
                                Layout.alignment: Qt.AlignTop
                                Layout.topMargin: 2
                                width: 20; height: 20; radius: 4
                                color: card.s.include ? accentPrimary : "transparent"
                                border.width: 1
                                border.color: card.s.include ? accentPrimary : textTertiary
                                Text {
                                    anchors.centerIn: parent
                                    visible: card.s.include
                                    text: "✓"
                                    color: Theme.surface
                                    font.pixelSize: 13
                                    font.weight: Font.Bold
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: updatesView.toggleInclude(card.url)
                                }
                            }

                            // Poster
                            Rectangle {
                                Layout.alignment: Qt.AlignTop
                                width: 52; height: 74; radius: 6
                                color: bgElevated
                                clip: true
                                Image {
                                    anchors.fill: parent
                                    source: card.item.poster_url || ""
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    cache: true
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text {
                                    Layout.fillWidth: true
                                    text: card.item.title
                                    elide: Text.ElideRight
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                    color: textPrimary
                                }
                                Text {
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 12
                                    color: textSecondary
                                    text: "You have " + card.item.on_disk_count + " chapters (up to ch "
                                          + card.item.on_disk_max + ")"
                                          + (card.src && card.src.newer.length
                                             ? "  ·  " + card.src.newer.length + " new: "
                                               + updatesView.rangeText(card.src.newer)
                                             : "")
                                }

                                // Source picker
                                RowLayout {
                                    spacing: 8
                                    Text {
                                        text: "From"
                                        font.pixelSize: 12
                                        color: textSecondary
                                    }
                                    ComboBox {
                                        id: sourceCombo
                                        Layout.preferredWidth: 460
                                        Layout.preferredHeight: 30
                                        model: (card.item.sources || []).map(updatesView.sourceLabel)
                                        currentIndex: card.s.source
                                        // Fusion reads colours from the palette, not
                                        // from `color` (see the 2026-05-04 changelog).
                                        palette.button: bgElevated
                                        palette.buttonText: textPrimary
                                        palette.window: bgElevated
                                        palette.windowText: textPrimary
                                        palette.base: bgElevated
                                        palette.text: textPrimary
                                        palette.highlight: accentPrimary
                                        palette.highlightedText: Theme.surface
                                        palette.mid: borderColor
                                        palette.dark: borderColor
                                        palette.light: bgElevated
                                        onActivated: (index) => updatesView.setSource(card.item, index)
                                    }
                                }

                                // New chapters
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    visible: !!card.src && card.src.newer.length > 0
                                    Repeater {
                                        model: card.src ? card.src.newer : []
                                        delegate: chapterChip
                                    }
                                }

                                // Gaps (older missing chapters) — opt-in
                                Text {
                                    visible: !!card.src && card.src.gaps.length > 0
                                    text: (card.showGaps ? "− " : "+ ")
                                          + (card.src ? card.src.gaps.length : 0)
                                          + " older chapter" + (card.src && card.src.gaps.length === 1 ? "" : "s")
                                          + " missing from your folder (gaps — not selected by default)"
                                    font.pixelSize: 12
                                    color: textTertiary
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            updatesView.expandedGaps[card.url] = !card.showGaps
                                            updatesView.selVersion++
                                        }
                                    }
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    visible: card.showGaps && !!card.src && card.src.gaps.length > 0
                                    Repeater {
                                        model: card.showGaps && card.src ? card.src.gaps : []
                                        delegate: chapterChip
                                    }
                                }

                                Text {
                                    visible: card.item.cloud_only > 0 && !(card.item.detected || []).length
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    text: "Couldn't tell which site your files came from — "
                                          + card.item.cloud_only + " of them are only in iCloud. "
                                          + "Use “Download Now” on the folder in Finder to let the app read them."
                                    font.pixelSize: 11
                                    color: textTertiary
                                }
                            }

                            Button {
                                Layout.alignment: Qt.AlignTop
                                Layout.preferredHeight: 28
                                text: "Skip"
                                onClicked: LibraryBridge.dismissUpdate(card.url)
                                ToolTip.visible: hovered
                                ToolTip.delay: 600
                                ToolTip.text: "Hide this series until the next check"
                                background: Rectangle {
                                    radius: 6
                                    color: parent.hovered ? bgElevated : "transparent"
                                    border.width: 1
                                    border.color: borderColor
                                }
                                contentItem: Text {
                                    text: parent.text
                                    color: textSecondary
                                    font.pixelSize: 12
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: 10
                                    rightPadding: 10
                                }
                            }
                        }

                        Component {
                            id: chapterChip
                            Rectangle {
                                id: chip
                                required property var modelData
                                readonly property bool picked:
                                    (updatesView.selVersion, !!card.s.picked[modelData.norm])
                                onPickedChanged: if (picked && Theme.animations) chipPop.restart()
                                SequentialAnimation {
                                    id: chipPop
                                    NumberAnimation { target: chip; property: "scale"; from: 0.8; to: 1.15; duration: Theme.dur(150); easing.type: Easing.OutQuad }
                                    NumberAnimation { target: chip; property: "scale"; to: 1; duration: Theme.dur(250); easing.type: Easing.OutBack }
                                }
                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: -3
                                    radius: parent.radius + 3
                                    color: "transparent"
                                    border.width: 3
                                    border.color: Theme.glow
                                    opacity: chip.picked ? 0.7 : 0
                                    Behavior on opacity { NumberAnimation { duration: Theme.dur(250) } }
                                }
                                height: 24
                                width: chipText.implicitWidth + 18
                                radius: 12
                                color: picked ? Qt.darker(accentPrimary, 2.2) : "transparent"
                                border.width: 1
                                border.color: picked ? accentPrimary : borderColor
                                Text {
                                    id: chipText
                                    anchors.centerIn: parent
                                    text: (chip.picked ? "✓ " : "") + "Ch " + chip.modelData.number
                                    font.pixelSize: 11
                                    color: chip.picked ? accentPrimary : textSecondary
                                }
                                MouseArea {
                                    id: chipMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: updatesView.toggleChapter(card.url, chip.modelData.norm)
                                }
                                ToolTip.visible: chipMouse.containsMouse && (chip.modelData.title || "").length > 0
                                ToolTip.delay: 500
                                ToolTip.text: chip.modelData.title || ""
                            }
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: LibraryBridge
        function onUpdateCheckStarted(total, skippedCompleted) {
            updatesView.checking = total > 0
            updatesView.checkDone = 0
            updatesView.checkTotal = total
            updatesView.checkTitle = ""
            updatesView.summary = ""
        }
        function onUpdateCheckProgress(done, total, url, title) {
            updatesView.checkDone = Math.min(done, total)
            updatesView.checkTotal = total
            updatesView.checkTitle = title
        }
        function onUpdateCheckFinished(withUpdates, upToDate, failed, skippedCompleted, noFiles) {
            updatesView.checking = false
            updatesView.checkTitle = ""
            var parts = []
            parts.push(withUpdates + " with new chapters")
            if (upToDate > 0) parts.push(upToDate + " up to date")
            if (failed > 0) parts.push(failed + " couldn't be checked")
            if (noFiles > 0) parts.push(noFiles + " skipped (no chapter files found in their folder)")
            if (skippedCompleted > 0) parts.push(skippedCompleted + " skipped (completed)")
            updatesView.summary = "Check complete — " + parts.join(", ")
            updatesView.refresh()
        }
        function onPendingUpdatesChanged() { updatesView.refresh() }
    }
}
