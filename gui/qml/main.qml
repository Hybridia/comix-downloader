import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"
import "views"
import "fx"
import Style
import "logic/badge.js" as Badge

ApplicationWindow {
    id: root
    
    readonly property color bgDeep: Theme.bg
    readonly property color bgSurface: Theme.surface
    
    width: 1320
    height: 820
    minimumWidth: 1100
    minimumHeight: 680
    visible: true
    title: "Comix Downloader"
    color: bgDeep
    
    flags: Qt.FramelessWindowHint | Qt.Window
    
    property point dragStart: Qt.point(0, 0)

    // Everything visible lives in windowRoot so ThemeWipe can snapshot it
    // (the window's own contentItem has no QML engine to grab with).
    Item {
        id: windowRoot
        anchors.fill: parent

        Rectangle { anchors.fill: parent; color: Theme.bg }

        // Drifting colour glow behind everything (Settings → Appearance).
        AmbientGlow {
            anchors.fill: parent
        }

        RowLayout {
            id: appContent
            anchors.fill: parent
            spacing: 0
        
            // SIDEBAR NAVIGATION
            SideBar {
                id: sideBar
                Layout.fillHeight: true
                Layout.preferredWidth: 240
            
                onBrowseClicked: viewStack.currentIndex = 0
                onDownloadsClicked: viewStack.currentIndex = 1
                onLibraryClicked: { viewStack.currentIndex = 2; libraryView.refresh(true) }
                onUpdatesClicked: { viewStack.currentIndex = 3; updatesView.refresh() }
                onSettingsClicked: settingsDrawer.isOpen = true
            }
        
            // MAIN CONTENT AREA
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0
            
                // TITLE BAR (Modified for the new layout)
                TitleBar {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                
                    onMinimizeClicked: root.showMinimized()
                    onMaximizeClicked: root.visibility === Window.Maximized ? root.showNormal() : root.showMaximized()
                    onCloseClicked: Qt.quit()
                    onDragStarted: (pos) => root.dragStart = pos
                    onDragMoved: (pos) => { root.x += pos.x - root.dragStart.x; root.y += pos.y - root.dragStart.y }
                }
            
                // VIEW STACK — animated page switcher (pages stay alive)
                Item {
                    id: viewStack
                    property int currentIndex: 0
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ViewPane {
                        id: browsePane
                        anchors.fill: parent
                        index: 0; currentIndex: viewStack.currentIndex
                        BrowseView {
                            id: browseView
                            anchors.fill: parent
                        }
                    }

                    ViewPane {
                        anchors.fill: parent
                        index: 1; currentIndex: viewStack.currentIndex
                        DownloadsView {
                            id: downloadsView
                            anchors.fill: parent
                        }
                    }

                    ViewPane {
                        anchors.fill: parent
                        index: 2; currentIndex: viewStack.currentIndex
                        LibraryView {
                            id: libraryView
                            anchors.fill: parent
                            onUpdatesRequested: {
                                sideBar.activeTab = 3
                                viewStack.currentIndex = 3
                                updatesView.refresh()
                            }
                        }
                    }

                    ViewPane {
                        anchors.fill: parent
                        index: 3; currentIndex: viewStack.currentIndex
                        UpdatesView {
                            id: updatesView
                            anchors.fill: parent
                        }
                    }
                }
            }
        }
    
        // SETTINGS DRAWER (Global overlay)
        SettingsDrawer {
            id: settingsDrawer
            anchors.fill: parent
            isOpen: false
            backdropSource: appContent
        }

    
        // Toast notifications (Fx.toast) sit above everything, drawer included.
        ToastHost {
            id: toastHost
            objectName: "toastHost"
            anchors.fill: parent
            z: 100
        }

        // Fly-to-downloads bubbles (Fx.flyRequested) arc to the sidebar.
        Item {
            id: flyLayer
            anchors.fill: parent
            z: 90
        }
    }

    // Circular colour wipe when the theme changes (Settings → Appearance).
    ThemeWipe {
        anchors.fill: parent
        target: windowRoot
        z: 200
    }
    Component {
        id: flyBubble
        Rectangle {
            id: bubble
            property point from
            property point to
            property int count: 0
            width: 30; height: 30; radius: 15
            x: from.x - 15; y: from.y - 15
            color: Theme.accent
            border.color: Theme.highlight
            Text {
                anchors.centerIn: parent
                text: bubble.count
                font.pixelSize: 12; font.weight: Font.Black
                color: Theme.bg
            }
            ParallelAnimation {
                running: true
                NumberAnimation { target: bubble; property: "x"; to: bubble.to.x - 15; duration: Theme.dur(900); easing.type: Easing.InOutQuad }
                SequentialAnimation {
                    NumberAnimation { target: bubble; property: "y"; to: Math.min(bubble.from.y, bubble.to.y) - 160; duration: Theme.dur(420); easing.type: Easing.OutQuad }
                    NumberAnimation { target: bubble; property: "y"; to: bubble.to.y - 15; duration: Theme.dur(480); easing.type: Easing.InQuad }
                }
                SequentialAnimation {
                    NumberAnimation { target: bubble; property: "scale"; to: 1.4; duration: Theme.dur(420); easing.type: Easing.OutQuad }
                    NumberAnimation { target: bubble; property: "scale"; to: 0.4; duration: Theme.dur(480); easing.type: Easing.InQuad }
                }
                onFinished: { sideBar.bumpDownloads(); bubble.destroy() }
            }
        }
    }
    Connections {
        target: Fx
        function onFlyRequested(from, count) {
            var a = sideBar.downloadsAnchor
            var to = a.mapToItem(flyLayer, a.width - 40, a.height / 2)
            flyBubble.createObject(flyLayer, { from: from, to: to, count: count })
        }
    }

    // Downloads badge: chapters still queued or downloading.
    property var dlBadge: Badge.empty()
    property var jobTitles: ({})
    // Cancelled jobs still emit downloadFinished once their in-flight
    // chapters complete — that must not read as a success.
    property var cancelledJobs: ({})
    function _badge(next) { dlBadge = next; sideBar.downloadsCount = Badge.count(next) }

    // CONNECTIONS TO PYTHON BRIDGES
    Connections {
        target: LibraryBridge
        function onPendingUpdatesChanged() {
            sideBar.updatesCount = LibraryBridge.pendingUpdates().length
        }
        function onUpdateCheckFinished(withUpdates, upToDate, failed, skipped, noFiles) {
            Fx.toast(withUpdates > 0
                ? "Check finished — " + withUpdates + " series " + (withUpdates === 1 ? "has" : "have") + " new chapters"
                : "Check finished — everything is up to date", withUpdates > 0 ? "ok" : "info")
        }
    }
    Connections {
        target: MangaBridge
        function onMangaLoaded(info) { browseView.getMangaCard().manga = info }
        function onChaptersLoaded(chapters) { browseView.getChapterList().setChapters(chapters) }
        function onErrorOccurred(error) { console.log("Manga Error:", error) }
    }
    
    Connections {
        target: DownloadBridge
        function onDownloadStarted() {
            // Auto switch to downloads tab. Don't reset the panel —
            // multiple concurrent jobs share it now, and resetting
            // would clobber the others. The "Clear Finished" button
            // in DownloadsView is the explicit cleanup gesture.
            sideBar.activeTab = 1
            viewStack.currentIndex = 1
        }
        function onJobStarted(jobId, title, posterUrl, totalChapters) {
            root.jobTitles[jobId] = title
            root._badge(Badge.jobStarted(root.dlBadge, jobId, totalChapters))
            downloadsView.getProgressPanel().registerJob(jobId, title, posterUrl, totalChapters)
        }
        function onOverallProgress(jobId, current, total) {
            downloadsView.getProgressPanel().routeOverallProgress(jobId, current, total)
        }
        function onChapterStarted(jobId, name) {
            downloadsView.getProgressPanel().routeChapterStarted(jobId, name)
        }
        function onChapterProgress(jobId, name, current, total) {
            downloadsView.getProgressPanel().routeChapterProgress(jobId, name, current, total)
        }
        function onChapterComplete(jobId, name, success, message) {
            root._badge(Badge.chapterDone(root.dlBadge, jobId))
            downloadsView.getProgressPanel().routeChapterComplete(jobId, name, success, message)
        }
        function onDownloadFinished(jobId, successful, failed) {
            root._badge(Badge.jobEnded(root.dlBadge, jobId))
            var title = root.jobTitles[jobId] || "this series"
            delete root.jobTitles[jobId]
            if (root.cancelledJobs[jobId]) {
                delete root.cancelledJobs[jobId]
                Fx.toast("Cancelled " + title + " after " + successful + " chapter" + (successful === 1 ? "" : "s"), "info")
            } else if (failed > 0)
                Fx.toast("Downloaded " + successful + " of " + title + ", " + failed + " failed", "error")
            else
                Fx.toast("Downloaded " + successful + " chapter" + (successful === 1 ? "" : "s") + " of " + title, "ok")
            downloadsView.getProgressPanel().routeJobFinished(jobId, successful, failed)
        }
        function onJobPaused(jobId, paused) {
            downloadsView.getProgressPanel().routeJobPaused(jobId, paused)
        }
        function onJobError(jobId, message) {
            root._badge(Badge.jobEnded(root.dlBadge, jobId))
            var title = root.jobTitles[jobId] || "a series"
            delete root.jobTitles[jobId]
            Fx.toast("Download of " + title + " failed: " + message, "error")
        }
        function onJobCancelled(jobId) {
            root._badge(Badge.jobEnded(root.dlBadge, jobId))
            root.cancelledJobs[jobId] = true
            downloadsView.getProgressPanel().routeJobCancelled(jobId)
        }
    }
    
    // STARTUP ANIMATION
    Component.onCompleted: {
        sideBar.updatesCount = LibraryBridge.pendingUpdates().length
        opacity = 0
        startupAnimation.start()
    }
    
    PropertyAnimation {
        id: startupAnimation
        target: root
        property: "opacity"
        from: 0; to: 1
        duration: 300
        easing.type: Easing.OutCubic
    }
}
