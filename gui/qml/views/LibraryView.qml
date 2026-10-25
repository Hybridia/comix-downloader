import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: libraryView

    // Ask main.qml to show the Updates view (after starting a check).
    signal updatesRequested()

    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color accentPrimary: Theme.accent
    readonly property color borderColor: Theme.border

    // Master list from the bridge.
    property var entries: []
    // Filtered + sorted view rendered by the Repeater.
    property var visibleEntries: []
    // Per-row state.
    property string busyUrl: ""
    property var statusByUrl: ({})  // source_url -> status string

    // Toolbar state.
    property string filterText: ""
    property string sortMode: "last_downloaded"
    // Three-state completion filter:
    //  ""                — show everything (default)
    //  "hide_completed"  — exclude completed / cancelled
    //  "only_completed"  — show ONLY completed / cancelled
    // The two toolbar chips are mutually exclusive (clicking one
    // clears the other).
    property string statusFilter: ""
    // Independent NSFW filter — hides entries where is_nsfw=true.
    // Useful if you want to focus on serial manhwa you're following
    // and not get distracted by doujinshi one-shots.
    property bool hideHentai: false

    // Per-card "Check" state: url → summary from entryCheckFinished,
    // and url → true while that card's check is running.
    property var checkInfoByUrl: ({})
    property var checkingUrls: ({})
    property int checkVersion: 0

    // Manual selection for "Check selected" — url → true. Bumping
    // selVersion re-evaluates bindings (JS object mutation doesn't).
    property var selectedUrls: ({})
    property int selVersion: 0
    readonly property int selectedCount:
        (selVersion, Object.keys(selectedUrls).length)

    function toggleSelected(url) {
        if (selectedUrls[url]) delete selectedUrls[url]
        else selectedUrls[url] = true
        selVersion++
    }
    function selectAllVisible() {
        for (var i = 0; i < visibleEntries.length; i++)
            selectedUrls[visibleEntries[i].source_url] = true
        selVersion++
    }
    function clearSelection() {
        selectedUrls = {}
        selVersion++
    }

    // Bulk "Update All" state.
    property bool bulkBusy: false
    property int bulkDone: 0
    property int bulkTotal: 0
    property int bulkSkippedCompleted: 0
    property string bulkCurrentTitle: ""
    property string bulkSummary: ""

    // Status-only check state (separate from Update All because it
    // never triggers downloads; visually shares the same banner slot).
    property bool statusBusy: false
    property int statusDone: 0
    property int statusTotal: 0
    property string statusCurrentTitle: ""
    property string statusSummary: ""

    function refresh() {
        entries = LibraryBridge.listEntries()
        applyFilterAndSort()
    }

    function applyFilterAndSort() {
        var filter = (filterText || "").trim().toLowerCase()
        var out = []
        for (var i = 0; i < entries.length; i++) {
            var e = entries[i]
            // Completion filter — three states. "Finished" means the
            // site says completed OR cancelled (both = no new chapters).
            if (statusFilter !== "") {
                var s = e.status || ""
                var finished = (s === "completed" || s === "cancelled")
                if (statusFilter === "hide_completed" && finished) continue
                if (statusFilter === "only_completed" && !finished) continue
            }
            // NSFW filter — independent of the completion filter.
            if (hideHentai && e.is_nsfw === true) continue
            if (filter.length > 0) {
                var hit = false
                var hay = (e.title || "").toLowerCase()
                if (hay.indexOf(filter) >= 0) hit = true
                if (!hit) {
                    var alts = e.alt_titles || []
                    for (var a = 0; a < alts.length; a++) {
                        if ((alts[a] || "").toLowerCase().indexOf(filter) >= 0) {
                            hit = true; break
                        }
                    }
                }
                if (!hit && (e.source || "").toLowerCase().indexOf(filter) >= 0) hit = true
                if (!hit) continue
            }
            out.push(e)
        }

        function cmpStr(a, b) {
            a = a || ""; b = b || ""
            return a.localeCompare(b)
        }
        function cmpNum(a, b) { return (a || 0) - (b || 0) }

        out.sort(function(a, b) {
            switch (sortMode) {
                case "last_downloaded":
                    // Desc: newest activity first.
                    return cmpStr(b.last_updated_at, a.last_updated_at)
                          || cmpStr(b.added_at, a.added_at)
                case "recently_added":
                    // Desc: most-recently-added first.
                    return cmpStr(b.added_at, a.added_at)
                          || cmpStr(b.last_updated_at, a.last_updated_at)
                case "name":
                    return cmpStr((a.title || "").toLowerCase(),
                                  (b.title || "").toLowerCase())
                case "chapter_count":
                    // Desc: biggest libraries first.
                    return cmpNum(b.chapter_count, a.chapter_count)
                          || cmpStr((a.title || "").toLowerCase(),
                                    (b.title || "").toLowerCase())
                case "site":
                    var s = cmpStr((a.source || "").toLowerCase(),
                                   (b.source || "").toLowerCase())
                    if (s !== 0) return s
                    return cmpStr((a.title || "").toLowerCase(),
                                  (b.title || "").toLowerCase())
            }
            return 0
        })

        visibleEntries = out

        entryModel.clear()
        for (var j = 0; j < out.length; j++) {
            entryModel.append({"source_url": out[j].source_url})
        }
    }

    function entryFor(url) {
        for (var i = 0; i < entries.length; i++) {
            if (entries[i].source_url === url) return entries[i]
        }
        return null
    }

    function setStatus(url, msg) {
        var copy = {}
        for (var k in statusByUrl) copy[k] = statusByUrl[k]
        if (msg) {
            copy[url] = msg
        } else {
            delete copy[url]
        }
        statusByUrl = copy
    }

    // Re-apply filter/sort whenever the toolbar changes. Cheap; we
    // hold the master list in memory either way.
    onFilterTextChanged: applyFilterAndSort()
    onSortModeChanged: applyFilterAndSort()
    onStatusFilterChanged: applyFilterAndSort()
    onHideHentaiChanged: applyFilterAndSort()

    Component.onCompleted: refresh()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        // -----------------------------------------------------------
        // HEADER: title + global actions
        // -----------------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                spacing: 4
                Text {
                    text: "LIBRARY"
                    font.family: "Segoe UI"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    color: textPrimary
                }
                Text {
                    text: "Everything you've downloaded — re-fetch any of them to grab new chapters"
                    font.pixelSize: 13
                    color: textSecondary
                }
            }

            Item { Layout.fillWidth: true }

            // CHECK STATUS — lightweight: refreshes the Completed /
            // Ongoing badges across the library without fetching
            // chapter lists or kicking off any downloads. Safe to
            // click any time; use this when you just want to know
            // which series are finished.
            Button {
                id: checkStatusBtn
                Layout.preferredHeight: 34
                text: libraryView.statusBusy
                      ? ("Cancel (" + libraryView.statusDone + " / "
                         + libraryView.statusTotal + ")")
                      : "◷ Check Status"
                enabled: (entries.length > 0 || libraryView.statusBusy)
                         && !libraryView.bulkBusy
                onClicked: {
                    if (libraryView.statusBusy) {
                        LibraryBridge.cancelCheckStatusAll()
                    } else {
                        LibraryBridge.checkStatusAll()
                    }
                }

                background: Rectangle {
                    radius: 6
                    color: parent.enabled
                           ? (libraryView.statusBusy
                              ? (parent.hovered ? "#C45050" : "#A03A3A")
                              : (parent.hovered ? bgElevated : "transparent"))
                           : "transparent"
                    border.width: 1
                    border.color: parent.enabled
                                  ? (libraryView.statusBusy
                                     ? "#A03A3A"
                                     : (parent.hovered ? accentPrimary : borderColor))
                                  : borderColor
                    Behavior on color { ColorAnimation { duration: 120 } }
                }
                contentItem: Text {
                    text: parent.text
                    color: libraryView.statusBusy
                           ? "#FFFFFF"
                           : (parent.enabled ? textPrimary : textTertiary)
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 14
                    rightPadding: 14
                }

                ToolTip.visible: hovered && !libraryView.statusBusy
                ToolTip.delay: 600
                ToolTip.text: "Refresh Completed / Ongoing badges for every entry.\n" +
                              "Does NOT download any chapters — safe to run any time."
            }

            // CHECK FOR UPDATES — probes series for new chapters and
            // lists them in the Updates view for approval. With cards
            // ticked it checks just those (completed ones included —
            // ticking is an explicit request); otherwise every ongoing
            // series. Replaces the old "Update All" button, which
            // downloaded everything it found without asking.
            Button {
                id: checkUpdatesBtn

                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: libraryView.selectedCount > 0
                    ? "Look for new chapters on the ticked series only.\n" +
                      "You review and approve them in Updates before anything downloads."
                    : "Look for new chapters on every ongoing series.\n" +
                      "Tick series (checkbox on the cover) to check only those.\n" +
                      "You review and approve them in Updates before anything downloads."
                Layout.preferredHeight: 34
                text: libraryView.selectedCount > 0
                      ? "🔔 Check " + libraryView.selectedCount + " selected"
                      : "🔔 Check for Updates"
                enabled: entries.length > 0 && !libraryView.statusBusy
                onClicked: {
                    if (!LibraryBridge.isCheckingForUpdates()) {
                        if (libraryView.selectedCount > 0) {
                            LibraryBridge.checkForUpdatesFor(Object.keys(libraryView.selectedUrls))
                            libraryView.clearSelection()
                        } else {
                            LibraryBridge.checkForUpdates()
                        }
                    }
                    libraryView.updatesRequested()
                }

                background: Rectangle {
                    radius: 6
                    color: parent.enabled
                           ? (parent.hovered ? Qt.lighter(accentPrimary, 1.1) : accentPrimary)
                           : Theme.border
                    Behavior on color { ColorAnimation { duration: 120 } }
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.enabled ? Theme.surface : textTertiary
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 14
                    rightPadding: 14
                }
            }

            Button {
                Layout.preferredHeight: 34
                text: "Refresh"
                onClicked: libraryView.refresh()

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
                    leftPadding: 14
                    rightPadding: 14
                }
            }
        }

        // -----------------------------------------------------------
        // TOOLBAR: search + sort + count
        // -----------------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            visible: entries.length > 0 || libraryView.filterText.length > 0

            // Search field
            Rectangle {
                Layout.preferredHeight: 36
                Layout.preferredWidth: 320
                color: bgCard
                radius: 8
                border.color: searchField.activeFocus ? accentPrimary : borderColor
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 8
                    spacing: 8

                    Text {
                        text: "🔍"
                        font.pixelSize: 13
                        color: textTertiary
                    }

                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        placeholderText: "Search by title, alt name, or site…"
                        text: libraryView.filterText
                        onTextChanged: libraryView.filterText = text
                        color: textPrimary
                        placeholderTextColor: textTertiary
                        font.pixelSize: 13
                        selectByMouse: true
                        // Fusion-friendly palette overrides — see the
                        // 2026-05-04 URL-field fix in CLAUDE.md.
                        palette.text: textPrimary
                        palette.placeholderText: textTertiary
                        palette.highlight: accentPrimary
                        palette.highlightedText: Theme.surface
                        selectionColor: accentPrimary
                        selectedTextColor: Theme.surface
                        background: Item {}
                    }

                    Button {
                        visible: libraryView.filterText.length > 0
                        Layout.preferredWidth: 22
                        Layout.preferredHeight: 22
                        flat: true
                        onClicked: {
                            libraryView.filterText = ""
                            searchField.text = ""
                        }
                        background: Rectangle {
                            color: parent.hovered ? bgElevated : "transparent"
                            radius: 4
                        }
                        contentItem: Text {
                            text: "✕"
                            color: textSecondary
                            font.pixelSize: 11
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
            }

            // Selection helpers for "Check selected".
            Text {
                text: libraryView.selectedCount > 0
                      ? libraryView.selectedCount + " selected · Clear"
                      : "Select all shown"
                font.pixelSize: 12
                color: accentPrimary
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: libraryView.selectedCount > 0
                               ? libraryView.clearSelection()
                               : libraryView.selectAllVisible()
                }
            }

            // Sort label
            Text {
                text: "Sort by"
                font.pixelSize: 12
                color: textSecondary
            }

            // Sort dropdown — uses a parallel array of (label, key)
            // pairs so we can drive sortMode by a stable key while
            // displaying friendly labels.
            ComboBox {
                id: sortCombo
                Layout.preferredHeight: 36
                Layout.preferredWidth: 200
                model: [
                    { label: "Last downloaded", key: "last_downloaded" },
                    { label: "Recently added",  key: "recently_added"  },
                    { label: "Name (A–Z)",      key: "name"            },
                    { label: "Chapter count",   key: "chapter_count"   },
                    { label: "Site",            key: "site"            }
                ]
                textRole: "label"
                valueRole: "key"
                currentIndex: 0
                onActivated: libraryView.sortMode = model[currentIndex].key
            }

            // Completion filter chips — mutually exclusive. Clicking
            // either toggles it; clicking the active one returns to
            // "Show all". Style mirrors the sort dropdown's accent
            // colour so the two filter controls feel related.
            Component {
                id: completionChip
                Rectangle {
                    id: chip
                    // -- Public --
                    property string label: ""
                    property string filterKey: ""        // "" | "hide_completed" | "only_completed"
                    property string tipText: ""
                    property color activeColor: Theme.success
                    readonly property bool active:
                        libraryView.statusFilter === chip.filterKey

                    Layout.preferredHeight: 36
                    implicitWidth: chipRow.implicitWidth + 24
                    radius: 18
                    color: active ? Qt.darker(activeColor, 2.2) : bgCard
                    border.color: active ? activeColor : borderColor
                    border.width: 1

                    RowLayout {
                        id: chipRow
                        anchors.centerIn: parent
                        spacing: 6

                        Text {
                            text: chip.active ? "✓" : "○"
                            font.pixelSize: 13
                            color: chip.active ? chip.activeColor : textTertiary
                        }
                        Text {
                            text: chip.label
                            font.pixelSize: 12
                            font.weight: chip.active ? Font.DemiBold : Font.Normal
                            color: chip.active ? chip.activeColor : textSecondary
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        // Clicking the active chip clears the filter;
                        // clicking an inactive one switches to it
                        // (auto-clearing the other since the QML
                        // property is single-valued).
                        onClicked: {
                            libraryView.statusFilter = chip.active ? "" : chip.filterKey
                        }
                        ToolTip.visible: containsMouse
                        ToolTip.delay: 600
                        ToolTip.text: chip.tipText
                    }
                }
            }

            Loader {
                Layout.preferredHeight: 36
                sourceComponent: completionChip
                onLoaded: {
                    item.label = "Hide completed"
                    item.filterKey = "hide_completed"
                    item.tipText = "Hide series the site says are completed or cancelled.\n" +
                                   "Check for Updates already skips these automatically."
                }
            }

            Loader {
                Layout.preferredHeight: 36
                sourceComponent: completionChip
                onLoaded: {
                    item.label = "Only completed"
                    item.filterKey = "only_completed"
                    item.tipText = "Show ONLY series the site says are completed.\n" +
                                   "Useful to skim what's done before archiving."
                }
            }

            // NSFW filter chip — independent of the completion filter
            // pair (you can combine them, e.g. "Hide completed AND
            // Hide hentai" to see the ongoing manhwa you follow).
            Rectangle {
                id: hentaiChip
                readonly property color activeColor: Theme.info

                Layout.preferredHeight: 36
                implicitWidth: hentaiRow.implicitWidth + 24
                radius: 18
                color: libraryView.hideHentai
                    ? Qt.darker(activeColor, 2.2)
                    : bgCard
                border.color: libraryView.hideHentai
                    ? activeColor
                    : borderColor
                border.width: 1

                RowLayout {
                    id: hentaiRow
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        text: libraryView.hideHentai ? "✓" : "○"
                        font.pixelSize: 13
                        color: libraryView.hideHentai
                            ? hentaiChip.activeColor : textTertiary
                    }
                    Text {
                        text: "Hide hentai"
                        font.pixelSize: 12
                        font.weight: libraryView.hideHentai
                            ? Font.DemiBold : Font.Normal
                        color: libraryView.hideHentai
                            ? hentaiChip.activeColor : textSecondary
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: libraryView.hideHentai = !libraryView.hideHentai
                    hoverEnabled: true
                    ToolTip.visible: containsMouse
                    ToolTip.delay: 600
                    ToolTip.text: "Hide entries flagged is_nsfw=true.\n" +
                                  "Useful to focus on serial manhwa you're following."
                }
            }

            Item { Layout.fillWidth: true }

            // Result counter — shows "showing N of M" when filtered
            // (by search OR hide-completed); just "N titles" otherwise.
            Text {
                font.pixelSize: 12
                color: textTertiary
                text: {
                    var n = libraryView.visibleEntries.length
                    var m = libraryView.entries.length
                    if (n !== m) {
                        return "Showing " + n + " of " + m
                    }
                    return n + (n === 1 ? " title" : " titles")
                }
            }
        }

        // -----------------------------------------------------------
        // BULK PROGRESS / SUMMARY BANNER
        // -----------------------------------------------------------
        Rectangle {
            id: bulkBanner
            Layout.fillWidth: true
            Layout.preferredHeight: bulkBanner.shown ? 48 : 0
            visible: bulkBanner.shown
            // The banner serves BOTH the Update All flow and the
            // Check Status flow. They're mutually exclusive (the
            // buttons disable each other) so we just toggle wording
            // and colours based on which one is active or last ran.
            color: bulkBanner.running ? bgCard : "#1F2E1A"
            radius: 8
            border.color: bulkBanner.running ? accentPrimary : "#4A7A3A"
            border.width: 1

            readonly property bool running:
                libraryView.bulkBusy || libraryView.statusBusy
            readonly property bool hasSummary:
                libraryView.bulkSummary.length > 0
                || libraryView.statusSummary.length > 0
            readonly property bool shown: running || hasSummary

            // Which flow is the banner currently representing? Update
            // mode wins when both bulkBusy and statusBusy are true
            // (impossible by gating, but defensive). When neither is
            // running we pick whichever summary is non-empty.
            readonly property string mode: {
                if (libraryView.bulkBusy) return "update"
                if (libraryView.statusBusy) return "status"
                if (libraryView.bulkSummary.length > 0) return "update"
                if (libraryView.statusSummary.length > 0) return "status"
                return "update"
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                spacing: 12

                Text {
                    text: bulkBanner.running ? "⟳" : "✓"
                    font.pixelSize: 16
                    color: bulkBanner.running ? accentPrimary : "#9CCB7F"

                    RotationAnimation on rotation {
                        running: bulkBanner.running
                        from: 0
                        to: 360
                        duration: 1400
                        loops: Animation.Infinite
                    }
                }

                Text {
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    color: textPrimary
                    font.pixelSize: 13
                    text: {
                        if (libraryView.bulkBusy) {
                            return "Updating " + libraryView.bulkDone
                                 + " of " + libraryView.bulkTotal
                                 + (libraryView.bulkCurrentTitle
                                    ? ": " + libraryView.bulkCurrentTitle
                                    : "…")
                        }
                        if (libraryView.statusBusy) {
                            return "Checking status " + libraryView.statusDone
                                 + " of " + libraryView.statusTotal
                                 + (libraryView.statusCurrentTitle
                                    ? ": " + libraryView.statusCurrentTitle
                                    : "…")
                        }
                        return bulkBanner.mode === "update"
                               ? libraryView.bulkSummary
                               : libraryView.statusSummary
                    }
                }

                // Progress bar — only while running. Uses whichever
                // counter is active.
                Rectangle {
                    visible: bulkBanner.running
                    Layout.preferredWidth: 180
                    Layout.preferredHeight: 4
                    color: bgElevated
                    radius: 2

                    Rectangle {
                        height: parent.height
                        radius: 2
                        color: accentPrimary

                        readonly property int done:
                            libraryView.bulkBusy
                            ? libraryView.bulkDone
                            : libraryView.statusDone
                        readonly property int total:
                            libraryView.bulkBusy
                            ? libraryView.bulkTotal
                            : libraryView.statusTotal

                        width: total > 0
                               ? parent.width * (done / total)
                               : 0
                        Behavior on width { NumberAnimation { duration: 250 } }
                    }
                }

                Button {
                    visible: !bulkBanner.running && bulkBanner.hasSummary
                    text: "✕"
                    flat: true
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    onClicked: {
                        libraryView.bulkSummary = ""
                        libraryView.statusSummary = ""
                    }

                    background: Rectangle {
                        radius: 4
                        color: parent.hovered ? bgElevated : "transparent"
                    }
                    contentItem: Text {
                        text: parent.text
                        color: textSecondary
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        // -----------------------------------------------------------
        // EMPTY STATES
        // -----------------------------------------------------------

        // Library is completely empty.
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgCard
            radius: 12
            visible: entries.length === 0

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 12

                Text {
                    text: "📚"
                    font.pixelSize: 48
                    color: textTertiary
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "Your library is empty"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    color: textPrimary
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "Download a manga from the Browse tab to add it here."
                    font.pixelSize: 13
                    color: textSecondary
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "The Browse tab lists every site you can paste a URL from."
                    font.pixelSize: 11
                    color: textTertiary
                    Layout.alignment: Qt.AlignHCenter
                }
            }
        }

        // Library has entries but the current filter matches none.
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgCard
            radius: 12
            visible: entries.length > 0 && entryModel.count === 0

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 8

                Text {
                    text: "🔍"
                    font.pixelSize: 32
                    color: textTertiary
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "No titles match \"" + libraryView.filterText + "\""
                    font.pixelSize: 14
                    color: textPrimary
                    Layout.alignment: Qt.AlignHCenter
                }
                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: "Clear search"
                    flat: true
                    onClicked: {
                        libraryView.filterText = ""
                        searchField.text = ""
                    }
                    contentItem: Text {
                        text: parent.text
                        color: accentPrimary
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle { color: "transparent" }
                }
            }
        }

        // -----------------------------------------------------------
        // ENTRY LIST
        // -----------------------------------------------------------
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: entryModel.count > 0
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                spacing: 10

                Repeater {
                    model: ListModel { id: entryModel }

                    LibraryCard {
                        entry: libraryView.entryFor(model.source_url)
                        statusMessage: libraryView.statusByUrl[model.source_url] || ""
                        busy: libraryView.busyUrl === model.source_url
                              || (libraryView.checkVersion, !!libraryView.checkingUrls[model.source_url])
                        checkInfo: (libraryView.checkVersion,
                                    libraryView.checkInfoByUrl[model.source_url] || null)
                        selected: (libraryView.selVersion,
                                   !!libraryView.selectedUrls[model.source_url])
                        onSelectToggled: libraryView.toggleSelected(model.source_url)

                        // "Check for new" — probe-only; the result shows
                        // inline and nothing downloads until approved.
                        onUpdateRequested: {
                            libraryView.checkingUrls[model.source_url] = true
                            delete libraryView.checkInfoByUrl[model.source_url]
                            libraryView.checkVersion++
                            libraryView.setStatus(model.source_url,
                                                  "Checking for new chapters…")
                            LibraryBridge.checkEntry(model.source_url)
                        }
                        onDownloadNewRequested: {
                            var n = LibraryBridge.downloadRecommended(model.source_url)
                            delete libraryView.checkInfoByUrl[model.source_url]
                            libraryView.checkVersion++
                            libraryView.setStatus(model.source_url, n > 0
                                ? "Downloading " + n + " new chapter" + (n === 1 ? "" : "s") + "…"
                                : "Nothing to download — already on disk")
                        }
                        onReviewRequested: libraryView.updatesRequested()
                        onRemoveRequested: {
                            LibraryBridge.removeEntry(model.source_url)
                        }
                        onOpenFolderRequested: {
                            LibraryBridge.openFolder(model.source_url)
                        }
                        onOpenWebsiteRequested: {
                            LibraryBridge.openWebsite(model.source_url)
                        }
                        onOpenAlternativeRequested: function(url) {
                            // Reuse the same bridge slot — it just
                            // calls webbrowser.open() so any http(s)
                            // URL works the same way.
                            LibraryBridge.openWebsite(url)
                        }
                        onConvertToCbzRequested: {
                            libraryView.busyUrl = model.source_url
                            libraryView.setStatus(model.source_url,
                                                  "Packing chapters into CBZ…")
                            LibraryBridge.convertToCbz(model.source_url)
                        }
                        onStatusChangeRequested: function(statusKey, manual) {
                            LibraryBridge.setStatus(model.source_url, statusKey, manual)
                        }
                    }
                }
            }
        }
    }

    // BRIDGE SIGNALS
    Connections {
        target: LibraryBridge

        function onEntriesChanged() {
            libraryView.refresh()
        }
        function onEntryCheckFinished(url, info) {
            delete libraryView.checkingUrls[url]
            if (info.new_count > 0) libraryView.checkInfoByUrl[url] = info
            libraryView.checkVersion++
            var msg
            if (info.error) msg = "Check failed: " + info.error
            else if (info.no_files) msg = "No chapter files found in this series' folder"
            else if (info.new_count > 0) msg = ""
            else msg = "Up to date"
            libraryView.setStatus(url, msg)
        }
        function onUpdateStarted(url, title, count) {
            libraryView.busyUrl = ""
            libraryView.setStatus(url,
                "Downloading " + count + " new chapter" + (count === 1 ? "" : "s") + "…")
        }
        function onNoUpdatesAvailable(url, title) {
            libraryView.busyUrl = ""
            libraryView.setStatus(url, "Up to date")
        }
        function onUpdateFailed(url, error) {
            libraryView.busyUrl = ""
            libraryView.setStatus(url, "Update failed: " + error)
        }
        function onRepackStarted(url, total) {
            libraryView.setStatus(url,
                "Packing " + total + " chapter" + (total === 1 ? "" : "s") + "…")
        }
        function onRepackProgress(url, done, total) {
            libraryView.setStatus(url,
                "Packing chapters… " + done + " / " + total)
        }
        function onRepackFinished(url, created, skipped, failed) {
            libraryView.busyUrl = ""
            var parts = []
            if (created > 0) parts.push(created + " CBZ" + (created === 1 ? "" : "s") + " created")
            if (skipped > 0) parts.push(skipped + " already packed")
            if (failed > 0)  parts.push(failed + " failed")
            libraryView.setStatus(url, parts.length ? parts.join(", ") : "Nothing to convert")
        }
        function onRepackFailed(url, error) {
            libraryView.busyUrl = ""
            libraryView.setStatus(url, "Convert failed: " + error)
        }

        // Bulk Update All — header banner + per-row busy follow the
        // sequentially-running probe.
        function onUpdateAllStarted(total, skippedCompleted) {
            libraryView.bulkBusy = total > 0
            libraryView.bulkDone = 0
            libraryView.bulkTotal = total
            libraryView.bulkSkippedCompleted = skippedCompleted
            libraryView.bulkCurrentTitle = ""
            libraryView.bulkSummary = ""
        }
        function onUpdateAllProgress(done, total, url, title) {
            // 'done' is the 1-based index of the entry being probed.
            // Don't increment beyond total.
            libraryView.bulkDone = Math.min(done, total)
            libraryView.bulkTotal = total
            libraryView.bulkCurrentTitle = title
            libraryView.busyUrl = url
            libraryView.setStatus(url, "Checking for new chapters…")
        }
        function onUpdateAllFinished(withUpdates, upToDate, failed, skippedCompleted) {
            libraryView.bulkBusy = false
            libraryView.busyUrl = ""
            libraryView.bulkCurrentTitle = ""
            var parts = []
            if (withUpdates > 0) parts.push(withUpdates
                + " with new chapter" + (withUpdates === 1 ? "" : "s"))
            if (upToDate > 0) parts.push(upToDate + " up to date")
            if (failed > 0) parts.push(failed + " failed")
            if (skippedCompleted > 0) parts.push(skippedCompleted + " skipped (completed)")
            libraryView.bulkSummary = parts.length
                ? ("Update All complete — " + parts.join(", "))
                : "Update All — nothing to check"
        }

        // Bulk Check Status — same shape as Update All but doesn't
        // trigger downloads. Per-row "Checking status…" is set on
        // each progress event so the row visibly updates.
        function onStatusCheckAllStarted(total) {
            libraryView.statusBusy = total > 0
            libraryView.statusDone = 0
            libraryView.statusTotal = total
            libraryView.statusCurrentTitle = ""
            libraryView.statusSummary = ""
        }
        function onStatusCheckAllProgress(done, total, url, title) {
            libraryView.statusDone = Math.min(done, total)
            libraryView.statusTotal = total
            libraryView.statusCurrentTitle = title
            libraryView.busyUrl = url
            libraryView.setStatus(url, "Checking status…")
        }
        function onStatusCheckAllFinished(completed, ongoing, unknown, failed) {
            libraryView.statusBusy = false
            libraryView.busyUrl = ""
            libraryView.statusCurrentTitle = ""
            var parts = []
            if (completed > 0) parts.push(completed + " completed")
            if (ongoing > 0)   parts.push(ongoing + " ongoing")
            if (unknown > 0)   parts.push(unknown + " unknown")
            if (failed > 0)    parts.push(failed + " failed")
            libraryView.statusSummary = parts.length
                ? ("Status check complete — " + parts.join(", "))
                : "Status check — nothing to do"
            // Clear any lingering per-row "Checking status…" labels.
            libraryView.statusByUrl = {}
        }
    }

    // Refresh whenever a download finishes — that's when the library
    // grows or its chapter count changes.
    Connections {
        target: DownloadBridge
        function onDownloadFinished(jobId, successful, failed) {
            libraryView.refresh()
        }
        // Replace the card's "Downloading N new chapters…" line once
        // a Library-dispatched job ends.
        function onLibraryJobFinished(url, successful, failed) {
            var msg
            if (failed < 0) msg = "Download failed — see the Downloads tab"
            else if (failed > 0) msg = "Downloaded " + successful + ", " + failed
                                       + " failed — see the Downloads tab"
            else msg = "Downloaded " + successful + " new chapter"
                       + (successful === 1 ? "" : "s")
            libraryView.setStatus(url, msg)
        }
    }
}
