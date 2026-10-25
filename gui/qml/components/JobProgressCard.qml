import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../fx"

// One card per active download. Owns its own ListModel of active
// chapter rows. The parent ProgressPanel creates one per `jobStarted`
// signal and routes per-job updates here via the slots below.
Rectangle {
    id: card

    // ── public API ────────────────────────────────────────────────
    property string jobId: ""
    property string title: ""
    property string posterUrl: ""
    property int totalChapters: 0
    property int completedChapters: 0
    property int successCount: 0
    property int failCount: 0
    property bool isFinished: false
    property bool isPaused: false
    property bool isCancelled: false
    property string currentChapter: ""
    // One glow flash + confetti when the job finishes.
    property bool flashing: false
    onIsFinishedChanged: if (isFinished) {
        flashing = true
        flashAnim.restart()
        burst.burst()
    }

    // Rise in when the card is created.
    transform: Translate { id: riseShift }
    Component.onCompleted: if (Theme.animations) riseAnim.start()
    SequentialAnimation {
        id: riseAnim
        PropertyAction { target: card; property: "opacity"; value: 0 }
        PropertyAction { target: riseShift; property: "y"; value: 24 }
        ParallelAnimation {
            NumberAnimation { target: card; property: "opacity"; to: 1; duration: Theme.dur(450); easing.type: Easing.OutQuint }
            NumberAnimation { target: riseShift; property: "y"; to: 0; duration: Theme.dur(550); easing.type: Easing.OutBack }
        }
    }
    Rectangle {
        id: flashRing
        anchors.fill: parent
        anchors.margins: -4
        radius: card.radius + 4
        color: "transparent"
        border.width: 4
        border.color: Theme.success
        opacity: 0
    }
    SequentialAnimation {
        id: flashAnim
        NumberAnimation { target: flashRing; property: "opacity"; to: 0.8; duration: Theme.dur(250) }
        NumberAnimation { target: flashRing; property: "opacity"; to: 0; duration: Theme.dur(750); easing.type: Easing.OutQuad }
        ScriptAction { script: card.flashing = false }
    }
    ParticleBurst { id: burst; anchors.fill: parent; z: 20 }

    // Theme — kept inline so the component is drop-in self-contained.
    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color accentHighlight: Theme.highlight
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color success: Theme.success

    color: bgCard
    radius: 10
    border.color: isFinished ? success : Theme.border
    border.width: 1
    implicitHeight: cardLayout.implicitHeight + 24

    ListModel { id: taskModel }

    // ── slots called by ProgressPanel router ──────────────────────
    function updateProgress(completed, total) {
        completedChapters = completed
        totalChapters = total
    }

    function registerChapter(name) {
        for (var i = 0; i < taskModel.count; i++) {
            if (taskModel.get(i).name === name) return
        }
        taskModel.append({
            "name": name,
            "progress": 0,
            "details": "Preparing…",
            "status": "Preparing"
        })
    }

    function updateChapterProgress(name, current, total) {
        var found = false
        for (var i = 0; i < taskModel.count; i++) {
            if (taskModel.get(i).name === name) {
                taskModel.setProperty(i, "progress", (current / total) * 100)
                taskModel.setProperty(i, "details", current + " / " + total + " images")
                taskModel.setProperty(i, "status", "Downloading")
                found = true
                break
            }
        }
        if (!found) {
            taskModel.append({
                "name": name,
                "progress": (current / total) * 100,
                "details": current + " / " + total + " images",
                "status": "Downloading"
            })
        }
    }

    function setChapterStatus(name, ok, message) {
        currentChapter = name
        if (ok) successCount++; else failCount++
        for (var i = 0; i < taskModel.count; i++) {
            if (taskModel.get(i).name === name) {
                taskModel.setProperty(i, "status", ok ? "Complete" : "Failed")
                taskModel.setProperty(i, "progress", 100)
                break
            }
        }
    }

    function setFinished(successful, failed) {
        isFinished = true
        // A finished job is no longer "paused" or "cancellable" — clear
        // those so the UI shows the final state cleanly.
        isPaused = false
        successCount = successful
        failCount = failed
    }

    function setPaused(paused) {
        if (!isFinished && !isCancelled) isPaused = paused
    }

    function setCancelled() {
        isCancelled = true
        isPaused = false
    }

    ColumnLayout {
        id: cardLayout
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // HEADER: cover thumbnail + title + chapter counter
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            // Cover thumbnail. Falls back to a coloured placeholder
            // when the URL is missing or fails to load.
            Rectangle {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 48
                radius: 4
                color: bgElevated
                clip: true
                Image {
                    anchors.fill: parent
                    source: card.posterUrl
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    visible: status === Image.Ready
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: card.title || "Unknown"
                    font.family: "Segoe UI"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    color: textPrimary
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    text: card.isFinished
                        ? "✓ " + card.successCount + " succeeded"
                          + (card.failCount > 0 ? ", " + card.failCount + " failed" : "")
                        : card.completedChapters + " / " + card.totalChapters + " chapters"
                    font.pixelSize: 11
                    color: card.isFinished ? success : textSecondary
                }
            }

            // Status pill — DOWNLOADING / PAUSED / CANCELLED / DONE.
            Text {
                text: card.isFinished ? "DONE"
                    : card.isCancelled ? "CANCELLED"
                    : card.isPaused ? "PAUSED"
                    : "DOWNLOADING"
                font.pixelSize: 10
                font.weight: Font.DemiBold
                color: card.isFinished ? success
                    : card.isCancelled ? Theme.error
                    : card.isPaused ? textSecondary
                    : accentPrimary
            }

            // Per-job pause/resume + cancel icon buttons. Hidden once
            // the job has finished (DONE / CANCELLED) — there's
            // nothing to control then.
            Row {
                spacing: 4
                visible: !card.isFinished && !card.isCancelled

                // Pause / Resume toggle. Single button that flips icon
                // and signal depending on isPaused.
                Rectangle {
                    width: 24; height: 24; radius: 12
                    color: pauseHover.containsMouse ? bgElevated : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: card.isPaused ? "▶" : "❚❚"
                        font.pixelSize: card.isPaused ? 12 : 9
                        color: textSecondary
                    }
                    MouseArea {
                        id: pauseHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (card.isPaused)
                                DownloadBridge.resumeJob(card.jobId)
                            else
                                DownloadBridge.pauseJob(card.jobId)
                        }
                    }
                }

                // Cancel. Stops scheduling further chapters; in-flight
                // ones finish normally so we don't leave half-written
                // CBZs on disk.
                Rectangle {
                    width: 24; height: 24; radius: 12
                    color: cancelHover.containsMouse ? "#3A1F1F" : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.pixelSize: 12
                        color: cancelHover.containsMouse ? Theme.error : textSecondary
                    }
                    MouseArea {
                        id: cancelHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: DownloadBridge.cancelJob(card.jobId)
                    }
                }
            }
        }

        // PER-JOB OVERALL PROGRESS BAR
        Rectangle {
            id: barTrack
            Layout.fillWidth: true
            Layout.preferredHeight: 8
            color: bgElevated
            radius: 4
            // soft glow under the fill
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                height: parent.height + 6
                width: barFill.width
                radius: height / 2
                color: card.isFinished ? Qt.rgba(card.success.r, card.success.g, card.success.b, 0.35) : Theme.glow
                opacity: barFill.width > 0 ? 0.6 : 0
            }
            Item {
                id: barFill
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: card.totalChapters > 0
                    ? parent.width * (card.completedChapters / card.totalChapters)
                    : 0
                clip: true
                Behavior on width { NumberAnimation { duration: Theme.dur(350); easing.type: Easing.OutQuint } }
                // Flowing gradient: twice the track width, sliding left.
                Rectangle {
                    width: barTrack.width * 2
                    height: parent.height
                    radius: 4
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: card.isFinished ? card.success : Theme.accent2 }
                        GradientStop { position: 0.25; color: card.isFinished ? "#8BC34A" : Theme.accent }
                        GradientStop { position: 0.5; color: card.isFinished ? card.success : Theme.highlight }
                        GradientStop { position: 0.75; color: card.isFinished ? "#8BC34A" : Theme.accent }
                        GradientStop { position: 1.0; color: card.isFinished ? card.success : Theme.accent2 }
                    }
                    NumberAnimation on x {
                        from: 0; to: -barTrack.width
                        duration: 1600; loops: Animation.Infinite
                        running: Theme.animations && !card.isFinished && !card.isPaused && barTrack.visible
                    }
                }
                // Moving shimmer
                Rectangle {
                    width: 50; height: parent.height
                    visible: Theme.animations && !card.isFinished && !card.isPaused
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "transparent" }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.55) }
                        GradientStop { position: 1; color: "transparent" }
                    }
                    NumberAnimation on x {
                        from: -50; to: barTrack.width
                        duration: 1300; loops: Animation.Infinite
                        running: Theme.animations && !card.isFinished && !card.isPaused && barTrack.visible
                    }
                }
            }
        }

        // ACTIVE CHAPTERS — only visible while the job is in flight.
        // Repeater (not a ListView) so the card grows with content
        // and the *outer* panel does the scrolling.
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: !card.isFinished && taskModel.count > 0

            Repeater {
                model: taskModel
                delegate: ColumnLayout {
                    id: chRow
                    Layout.fillWidth: true
                    spacing: 2
                    transform: Translate { id: chShift }
                    Component.onCompleted: if (Theme.animations) chIn.start()
                    SequentialAnimation {
                        id: chIn
                        PropertyAction { target: chRow; property: "opacity"; value: 0 }
                        PropertyAction { target: chShift; property: "y"; value: -8 }
                        ParallelAnimation {
                            NumberAnimation { target: chRow; property: "opacity"; to: 1; duration: Theme.dur(400) }
                            NumberAnimation { target: chShift; property: "y"; to: 0; duration: Theme.dur(450); easing.type: Easing.OutQuint }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        PulseRings {
                            Layout.preferredWidth: 8
                            Layout.preferredHeight: 8
                            running: model.status === "Preparing"
                            visible: running
                            color: accentPrimary
                        }
                        Text {
                            text: model.name
                            font.pixelSize: 11
                            font.weight: Font.Medium
                            color: textPrimary
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            text: model.details
                            font.pixelSize: 10
                            color: textSecondary
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 3
                        color: bgElevated
                        radius: 2
                        Rectangle {
                            height: parent.height
                            radius: 2
                            // Same "preparing" sliver semantics as the
                            // single-panel implementation that this
                            // component was factored out of.
                            width: model.status === "Preparing"
                                ? Math.max(8, parent.width * 0.04)
                                : parent.width * (model.progress / 100)
                            color: model.status === "Failed" ? Theme.error
                                : model.status === "Complete" ? success
                                : model.status === "Preparing" ? textSecondary
                                : accentPrimary
                            opacity: model.status === "Preparing" ? 0.4 : 1.0
                            Behavior on width { NumberAnimation { duration: Theme.dur(250); easing.type: Easing.OutQuint } }
                            Behavior on color { ColorAnimation { duration: Theme.dur(350) } }
                        }
                    }
                }
            }
        }
    }
}
