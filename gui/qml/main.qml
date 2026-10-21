import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"
import "views"

ApplicationWindow {
    id: root
    
    readonly property color bgDeep: "#0A0A0C"
    readonly property color bgSurface: "#141419"
    
    width: 1320
    height: 820
    minimumWidth: 1100
    minimumHeight: 680
    visible: true
    title: "Comix Downloader"
    color: bgDeep
    
    flags: Qt.FramelessWindowHint | Qt.Window
    
    property point dragStart: Qt.point(0, 0)
    
    RowLayout {
        anchors.fill: parent
        spacing: 0
        
        // SIDEBAR NAVIGATION
        SideBar {
            id: sideBar
            Layout.fillHeight: true
            Layout.preferredWidth: 240
            
            onBrowseClicked: viewStack.currentIndex = 0
            onDownloadsClicked: viewStack.currentIndex = 1
            onLibraryClicked: { viewStack.currentIndex = 2; libraryView.refresh() }
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
            
            // VIEW STACK
            StackLayout {
                id: viewStack
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: 0
                
                BrowseView {
                    id: browseView
                }

                DownloadsView {
                    id: downloadsView
                }

                LibraryView {
                    id: libraryView
                    onUpdatesRequested: {
                        sideBar.activeTab = 3
                        viewStack.currentIndex = 3
                        updatesView.refresh()
                    }
                }

                UpdatesView {
                    id: updatesView
                }
            }
        }
    }
    
    // SETTINGS DRAWER (Global overlay)
    SettingsDrawer {
        id: settingsDrawer
        anchors.fill: parent
        isOpen: false
    }
    
    // CONNECTIONS TO PYTHON BRIDGES
    Connections {
        target: LibraryBridge
        function onPendingUpdatesChanged() {
            sideBar.updatesCount = LibraryBridge.pendingUpdates().length
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
            downloadsView.getProgressPanel().routeChapterComplete(jobId, name, success, message)
        }
        function onDownloadFinished(jobId, successful, failed) {
            downloadsView.getProgressPanel().routeJobFinished(jobId, successful, failed)
        }
        function onJobPaused(jobId, paused) {
            downloadsView.getProgressPanel().routeJobPaused(jobId, paused)
        }
        function onJobCancelled(jobId) {
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
