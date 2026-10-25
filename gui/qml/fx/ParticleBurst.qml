import QtQuick
import QtQuick.Particles
import Style

// Confetti that pops out of the item's centre. burst() is a no-op when
// animations are off (the particle system isn't even created).
Item {
    id: root
    property int amount: 34
    function burst() { if (loader.item) loader.item.fire() }

    Loader {
        id: loader
        objectName: "burstLoader"
        anchors.fill: parent
        active: Theme.animations
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
