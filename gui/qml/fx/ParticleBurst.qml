import QtQuick
import QtQuick.Particles
import Style

// Confetti that pops out of the item's centre. The particle system only
// exists while a burst plays (a ParticleSystem ticks every frame for as
// long as it lives — one per Library card made the app lag). burst() is
// a no-op when animations are off.
Item {
    id: root
    property int amount: 34
    function burst() {
        if (!Theme.animations) return
        if (loader.item) loader.item.fire()
        else loader.active = true          // fires in onLoaded
        teardown.restart()
    }

    Timer { id: teardown; interval: 1700; onTriggered: loader.active = false }

    Loader {
        id: loader
        objectName: "burstLoader"
        anchors.fill: parent
        active: false
        onLoaded: item.fire()
        sourceComponent: Item {
            function fire() { emitter.burst(root.amount) }
            ParticleSystem { id: sys }
            ItemParticle {
                system: sys
                fade: true
                delegate: Rectangle {
                    width: 7; height: 7; radius: 2
                    rotation: Math.random() * 360
                    color: [Theme.accent, Theme.highlight, Theme.cool, Theme.accent2][Math.floor(Math.random() * 4)]
                }
            }
            Emitter {
                id: emitter
                system: sys
                anchors.centerIn: parent
                width: 2; height: 2
                emitRate: 0
                lifeSpan: 1100
                lifeSpanVariation: 300
                velocity: AngleDirection { angleVariation: 180; magnitude: 170; magnitudeVariation: 90 }
                acceleration: PointDirection { y: 240 }
            }
        }
    }
}
