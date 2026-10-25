import QtQuick
import Style

// Bottom-right toast stack. Anything can call Fx.toast(text, kind);
// kind is "info" | "ok" | "error". Max 4 visible, 3.2 s each.
Item {
    id: root
    readonly property int count: toasts.count
    readonly property int maxToasts: 4
    readonly property int lifetime: 3200
    property int _seq: 0
    // Most recent toast (handy for tests / debugging).
    property string lastText: ""
    property string lastKind: ""

    ListModel { id: toasts }

    function _remove(uid) {
        for (var i = 0; i < toasts.count; i++)
            if (toasts.get(i).uid === uid) { toasts.remove(i); return }
    }

    Connections {
        target: Fx
        function onToastRequested(text, kind) {
            root.lastText = text
            root.lastKind = kind || "info"
            toasts.append({ uid: ++root._seq, text: text, kind: kind || "info" })
            while (toasts.count > root.maxToasts) toasts.remove(0)
        }
    }

    ListView {
        id: list
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 18
        width: 360
        height: Math.min(contentHeight, parent.height - 36)
        interactive: false
        spacing: 8
        verticalLayoutDirection: ListView.BottomToTop
        model: toasts

        add: Transition {
            ParallelAnimation {
                NumberAnimation { property: "x"; from: 80; duration: Theme.dur(450); easing.type: Easing.OutBack }
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.dur(300) }
            }
        }
        remove: Transition {
            ParallelAnimation {
                NumberAnimation { property: "x"; to: 80; duration: Theme.dur(350); easing.type: Easing.InQuad }
                NumberAnimation { property: "opacity"; to: 0; duration: Theme.dur(350) }
            }
        }
        displaced: Transition {
            NumberAnimation { properties: "x,y"; duration: Theme.dur(300); easing.type: Easing.OutQuint }
        }

        delegate: Rectangle {
            id: toast
            required property int uid
            required property string text
            required property string kind
            anchors.right: parent ? parent.right : undefined
            width: Math.min(list.width, label.implicitWidth + 34)
            height: label.implicitHeight + 20
            radius: 9
            color: Theme.elevated
            border.color: Theme.border

            Rectangle {
                width: 3; radius: 2
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: 4 }
                color: toast.kind === "ok" ? Theme.success : toast.kind === "error" ? Theme.error : Theme.accent
            }
            Text {
                id: label
                anchors.verticalCenter: parent.verticalCenter
                x: 16
                width: Math.min(implicitWidth, list.width - 34)
                text: toast.text
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                color: Theme.textPrimary
            }
            Timer { interval: root.lifetime; running: true; onTriggered: root._remove(toast.uid) }
        }
    }
}
