import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Container that hosts one JobProgressCard per active download.
//
// All slots take a ``jobId`` first argument so updates from concurrent
// workers are routed to the right card. Cards are created lazily on
// the first ``jobStarted`` signal and stay around (in their finished
// state) until the user clicks "Clear Finished".
Rectangle {
    id: root

    // Aggregated status the parent view (or summary widgets) might
    // care about. When a single download is active these match its
    // values; when several are active, ``isFinished`` only flips true
    // after every job has finished. ``hasFinishedJob`` is the looser
    // signal — true as soon as ONE card is done — so the "Clear
    // Finished" button can light up even while other downloads run.
    property bool isFinished: false
    property bool hasFinishedJob: false

    readonly property color bgCard: "#1C1C24"
    readonly property color textPrimary: "#F5F5F0"
    readonly property color textSecondary: "#8B8B99"
    readonly property color success: "#7CB342"

    color: bgCard
    radius: 12

    // ── job state ──────────────────────────────────────────────────
    // ListModel rows are { jobId } only — they exist so the Repeater
    // re-renders when we add/remove jobs. The actual card instance is
    // looked up in ``cardsByJobId`` so we can call its slots from
    // the routers below.
    ListModel { id: jobsModel }
    property var cardsByJobId: ({})

    // Helpers for the section showing aggregated state when one or
    // more jobs are still running.
    function _activeJobCount() {
        var n = 0
        for (var i = 0; i < jobsModel.count; i++) {
            var c = cardsByJobId[jobsModel.get(i).jobId]
            if (c && !c.isFinished) n++
        }
        return n
    }
    function _refreshAggregateState() {
        if (jobsModel.count === 0) {
            isFinished = false
            hasFinishedJob = false
            return
        }
        var anyDone = false
        var allDone = true
        for (var i = 0; i < jobsModel.count; i++) {
            var c = cardsByJobId[jobsModel.get(i).jobId]
            if (!c) continue
            if (c.isFinished) anyDone = true
            else allDone = false
        }
        isFinished = allDone
        hasFinishedJob = anyDone
    }

    // ── public API: routers from the bridge signals ───────────────

    function reset() {
        // Only clear FINISHED cards. Active downloads stay so the user
        // can see them; "Clear Finished" is the natural mental model
        // when several jobs share the panel.
        for (var i = jobsModel.count - 1; i >= 0; i--) {
            var jid = jobsModel.get(i).jobId
            var c = cardsByJobId[jid]
            if (c && c.isFinished) {
                c.destroy()
                delete cardsByJobId[jid]
                jobsModel.remove(i)
            }
        }
        _refreshAggregateState()
    }

    function registerJob(jobId, title, posterUrl, totalChapters) {
        if (cardsByJobId[jobId]) return  // dedupe: signal can re-fire on resume
        var card = jobCardComponent.createObject(cardsContainer, {
            "jobId": jobId,
            "title": title,
            "posterUrl": posterUrl,
            "totalChapters": totalChapters,
        })
        cardsByJobId[jobId] = card
        jobsModel.append({ "jobId": jobId })
        _refreshAggregateState()
    }

    function routeOverallProgress(jobId, current, total) {
        var c = cardsByJobId[jobId]
        if (c) c.updateProgress(current, total)
    }
    function routeChapterStarted(jobId, name) {
        var c = cardsByJobId[jobId]
        if (c) c.registerChapter(name)
    }
    function routeChapterProgress(jobId, name, current, total) {
        var c = cardsByJobId[jobId]
        if (c) c.updateChapterProgress(name, current, total)
    }
    function routeChapterComplete(jobId, name, ok, message) {
        var c = cardsByJobId[jobId]
        if (c) c.setChapterStatus(name, ok, message)
    }
    function routeJobFinished(jobId, successful, failed) {
        var c = cardsByJobId[jobId]
        if (c) {
            c.setFinished(successful, failed)
            _refreshAggregateState()
        }
    }

    // Card factory — one Component instantiated per job.
    Component {
        id: jobCardComponent
        JobProgressCard {
            Layout.fillWidth: true
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        // HEADER — summarises across jobs while any are active.
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: {
                    if (jobsModel.count === 0) return "DOWNLOADS"
                    if (root.isFinished) return "ALL DOWNLOADS COMPLETE"
                    var active = root._activeJobCount()
                    return active === 1 ? "DOWNLOADING" : active + " DOWNLOADS RUNNING"
                }
                font.family: "Segoe UI"
                font.pixelSize: 18
                font.weight: Font.DemiBold
                color: root.isFinished ? success : textPrimary
            }
            Item { Layout.fillWidth: true }
            Text {
                text: jobsModel.count === 0
                    ? ""
                    : jobsModel.count + (jobsModel.count === 1 ? " job" : " jobs")
                font.pixelSize: 12
                color: textSecondary
                visible: jobsModel.count > 0
            }
        }

        // EMPTY STATE
        Text {
            visible: jobsModel.count === 0
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 40
            text: "No active downloads — start one from the Browse tab."
            color: textSecondary
            font.pixelSize: 13
        }

        // JOB CARDS — vertical scrolling. The cards themselves
        // size-to-content; the ScrollView handles overflow when you
        // have many concurrent jobs.
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: jobsModel.count > 0
            clip: true

            ColumnLayout {
                id: cardsContainer
                width: parent ? parent.width : 0
                spacing: 10
                // Cards are appended programmatically by registerJob;
                // this layout just gives them a place to live in
                // creation order.
            }
        }
    }
}
