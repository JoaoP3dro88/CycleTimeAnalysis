/**
 * roiTracker.js
 *
 * Pure logic for ROI entry/exit detection — no React, no DOM.
 * Mirrors the legacy Python VideoProcessor confirmation/grace logic.
 *
 * Constants (same as legacy):
 *   CONFIRMATION_FRAMES = 3   consecutive frames to confirm entry
 *   GRACE_FRAMES        = 10  frames of hand absence before confirming exit
 */

export const CONFIRMATION_FRAMES = 3
export const GRACE_FRAMES = 10
// Grace period in ms — used when a video-time timestamp is provided.
// 333ms of video-time before confirming exit (≈10 frames at 30fps).
export const GRACE_MS = 333

/**
 * Point-in-polygon test (ray casting) for normalised [0,1] coords.
 * @param {number} px
 * @param {number} py
 * @param {{x:number,y:number}[]} polygon
 * @returns {boolean}
 */
export function pointInPolygon(px, py, polygon) {
  let inside = false
  const n = polygon.length
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = polygon[i].x, yi = polygon[i].y
    const xj = polygon[j].x, yj = polygon[j].y
    const intersect =
      yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

/**
 * Find which ROI (if any) contains the given normalised point.
 * Returns the ROI index or null.
 * @param {number} px
 * @param {number} py
 * @param {Array<{name:string, points:{x:number,y:number}[]}>} rois
 * @returns {number|null}
 */
export function detectRoi(px, py, rois) {
  for (let i = 0; i < rois.length; i++) {
    if (rois[i].points.length >= 3 && pointInPolygon(px, py, rois[i].points)) {
      return i
    }
  }
  return null
}

/**
 * Create a fresh per-hand buffer state object.
 */
function makeHandState() {
  return {
    currentRoi: null,      // confirmed ROI index the hand is currently in
    buffer: [],            // pending entry confirmation buffer
    lostFrames: 0,         // consecutive frames where hand was absent
    lostSince: null,       // timestamp (ms) when hand was first lost
    entryTime: null,       // timestamp (ms) when hand entered currentRoi
  }
}

/**
 * RoiTracker — stateful class mirroring VideoProcessor's confirmation logic.
 *
 * Usage:
 *   const tracker = new RoiTracker()
 *   // each frame:
 *   const events = tracker.processFrame(handsDetected, rois)
 *   // handsDetected: { Left: roiIndex|null, Right: roiIndex|null }
 *   //   (only include keys for hands that were actually detected this frame)
 */
export class RoiTracker {
  constructor() {
    this.state = {
      Left: makeHandState(),
      Right: makeHandState(),
    }
    this.eventLog = []
  }

  reset() {
    this.state = { Left: makeHandState(), Right: makeHandState() }
    this.eventLog = []
  }

  /**
   * @param {{ Left?: number|null, Right?: number|null }} handsDetected
   *   Keys present = hand was detected this frame. Missing key = hand absent.
   * @param {Array} rois  ROI definitions (needed for names)
   * @param {number} [nowOverride]  Optional timestamp in ms to use instead of Date.now().
   *   Pass video.currentTime * 1000 when processing video frames so duration
   *   is in video-time seconds (correct at any playback speed).
   * @returns {Array}  New events produced this frame
   */
  processFrame(handsDetected, rois, nowOverride) {
    const now = nowOverride ?? Date.now()
    const newEvents = []

    for (const handLabel of ['Left', 'Right']) {
      const buf = this.state[handLabel]
      const isDetected = handLabel in handsDetected
      const detectedRoi = handsDetected[handLabel] ?? null

      if (!isDetected) {
        // ── Hand absent ──────────────────────────────────────────────────────
        buf.lostFrames++
        if (buf.lostSince === null) buf.lostSince = now

        // Use time-based grace when nowOverride is provided (video mode),
        // frame-based grace otherwise (camera mode uses Date.now() ms too,
        // so we can use the same GRACE_MS branch always).
        const graceExpired = (now - buf.lostSince) > GRACE_MS

        if (graceExpired && buf.currentRoi !== null) {
          // Grace period expired → confirm exit
          const duration = (now - buf.entryTime) / 1000
          const ev = {
            type: 'EXIT',
            hand: handLabel,
            roiIndex: buf.currentRoi,
            roiName: rois[buf.currentRoi]?.name ?? `ROI ${buf.currentRoi}`,
            duration,
            timestamp: now,
          }
          newEvents.push(ev)
          this.eventLog.push(ev)
          buf.currentRoi = null
          buf.entryTime = null
          buf.lostSince = null
          buf.lostFrames = 0
          buf.buffer = []
        }
        continue
      }

      // ── Hand detected ────────────────────────────────────────────────────
      buf.lostFrames = 0
      buf.lostSince = null

      // Changed ROI (including moving to null = outside all ROIs)
      if (buf.currentRoi !== null && buf.currentRoi !== detectedRoi) {
        const duration = (now - buf.entryTime) / 1000
        if (duration >= 0.15) {
          const ev = {
            type: 'EXIT',
            hand: handLabel,
            roiIndex: buf.currentRoi,
            roiName: rois[buf.currentRoi]?.name ?? `ROI ${buf.currentRoi}`,
            duration,
            timestamp: now,
          }
          newEvents.push(ev)
          this.eventLog.push(ev)
        }
        buf.currentRoi = null
        buf.entryTime = null
        buf.lostSince = null
        buf.buffer = []
      }

      // Accumulate entry confirmation
      if (detectedRoi !== null && buf.currentRoi === null) {
        buf.buffer.push(detectedRoi)

        // Keep only the last N frames
        if (buf.buffer.length > CONFIRMATION_FRAMES * 3) {
          buf.buffer = buf.buffer.slice(-CONFIRMATION_FRAMES * 3)
        }

        // Count consecutive matching entries at the tail
        const tail = buf.buffer.slice(-CONFIRMATION_FRAMES)
        const confirmed = tail.length === CONFIRMATION_FRAMES && tail.every((v) => v === detectedRoi)

        if (confirmed) {
          buf.currentRoi = detectedRoi
          buf.entryTime = now
          buf.buffer = []

          const ev = {
            type: 'ENTRY',
            hand: handLabel,
            roiIndex: detectedRoi,
            roiName: rois[detectedRoi]?.name ?? `ROI ${detectedRoi}`,
            timestamp: now,
          }
          newEvents.push(ev)
          this.eventLog.push(ev)
        }
      }
    }

    return newEvents
  }
}
