.pragma library
// Motion helpers shared by views.

// Entrance stagger: the first 12 items cascade 45 ms apart; everything
// after waits the same capped delay, so a 260-card Library doesn't make
// the last card wait seconds.
var STAGGER_STEP = 45
var STAGGER_ITEMS = 12

function staggerDelay(index) {
    if (index < STAGGER_ITEMS) return index * STAGGER_STEP
    return STAGGER_ITEMS * STAGGER_STEP
}
